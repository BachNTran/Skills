#!/usr/bin/env python3
"""wiki — browse any repo's docs as a file tree, reader and 2D/3D graph on localhost; collect feedback for the agent.

Standard library only (Python >= 3.10).
  build    <repo> [--data-dir D]                      scan the repo, write D/wiki.json
  serve    <repo> [--port 7790] [--data-dir D] [--open]
  feedback <repo> [--all] [--json] [--data-dir D]     list open (or all) feedback
  resolve  <repo> <F-id> --note "..." [--data-dir D]  append a resolution record
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import posixpath
import re
import secrets
import subprocess
import sys
import threading
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ASSETS = (Path(__file__).resolve().parent.parent / "assets").resolve()
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "build", "dist", "__pycache__", ".wiki"}
CLAUDE_KEEP = {"agents", "skills"}
MAX_FILE = 5 * 1024 * 1024
MAX_BODY = 64 * 1024
KINDS = ("wrong", "outdated", "unclear", "question", "idea", "answer", "praise")
ID_RE = re.compile(r"\b(?:FEAT|REQ|TC|IDEA|BUG|DEC|Q)-[A-Z0-9]+-\d{3}\b")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$", re.M | re.S)
MDLINK_RE = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)[^\]]*\]\]")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".md": "text/plain; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
IMG_EXT = {".svg", ".png", ".gif", ".webp"}
# An SVG may carry script: no script, no network, no framing of anything else; CSS/SMIL still animate.
SVG_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
UI_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
          "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; "
          "object-src 'none'; base-uri 'none'; form-action 'none'")
LOCK = threading.Lock()


# ---------- scanning ----------

def keep_dir(name: str, parent_is_claude: bool) -> bool:
    if parent_is_claude:
        return name in CLAUDE_KEEP
    if name in SKIP_DIRS or name.endswith(".nosync"):
        return False
    return not name.startswith(".") or name == ".claude"


def scan(root: Path):
    """Yield (repo-relative posix path, raw bytes) for every .md / .html / .svg file worth showing."""
    for dirpath, dirnames, filenames in os.walk(root):
        in_claude = Path(dirpath).name == ".claude"
        dirnames[:] = sorted(n for n in dirnames if keep_dir(n, in_claude))
        if in_claude:
            continue
        for name in sorted(filenames):
            if Path(name).suffix.lower() not in (".md", ".html", ".svg"):
                continue
            p = Path(dirpath, name)
            real = p.resolve()
            if not real.is_relative_to(root) or not real.is_file() or real.stat().st_size > MAX_FILE:
                continue
            yield p.relative_to(root).as_posix(), real.read_bytes()


def frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return {}, text
    fm, key = {}, None
    for line in m.group(1).splitlines():
        item = re.match(r"\s+-\s+(.*)", line)
        if item and key and fm.get(key) in ("", []):
            fm[key] = [*(fm[key] or []), item.group(1).strip().strip("'\"")]
            continue
        k, sep, v = line.partition(":")
        if not sep or line[:1] in " \t#-":
            continue
        key, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            fm[key] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            fm[key] = v.strip("'\"")
    return fm, text[m.end():]


def first_heading(body: str) -> str | None:
    m = re.search(r"^#[ \t]+(.+?)[ \t#]*$", FENCE_RE.sub("", body), re.M)
    return m.group(1).strip() if m else None


def summary(body: str) -> str:
    for block in re.split(r"\n[ \t]*\n", FENCE_RE.sub("", body)):
        b = block.strip()
        if not b or b[0] in "#>|<!-*+=`~" or re.match(r"\d+[.)]\s", b):
            continue
        s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", " ".join(b.split()))
        s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s).replace("**", "").replace("`", "")
        return s if len(s) <= 240 else s[:239].rstrip() + "…"
    return ""


def graphify_clusters(root: Path) -> dict[str, str]:
    """Optional enrichment: repo-relative file -> community label from graphify-out/graph.json."""
    try:
        g = json.loads((root / "graphify-out" / "graph.json").read_text("utf-8"))
        labels = g.get("community_labels") or g.get("communities") or {}
        if isinstance(labels, list):
            labels = {str(c.get("id")): c.get("label") or c.get("name") for c in labels if isinstance(c, dict)}
        votes: dict[str, Counter] = {}
        for n in g.get("nodes", []):
            f = n.get("source_file") or n.get("file") or n.get("path")
            c = n.get("community", n.get("cluster"))
            if not f or c is None:
                continue
            f = Path(f).resolve().relative_to(root).as_posix() if os.path.isabs(f) else posixpath.normpath(f)
            label = n.get("community_label") or n.get("community_name") or labels.get(str(c)) or f"cluster {c}"
            votes.setdefault(f, Counter())[str(label)] += 1
        return {f: c.most_common(1)[0][0] for f, c in votes.items()}
    except Exception:  # absent or malformed: skip silently
        return {}


def nearest_module(parts: list[str], modules: dict[str, str]) -> str | None:
    """Dir key of the closest module at or above the folder `parts` ("" is the repo root)."""
    return next((k for i in range(len(parts), -1, -1) if (k := "/".join(parts[:i])) in modules), None)


def group_hub(rels: list[str]) -> str:
    """A non-module group's centre: its top-level README/index page, else its shortest-path page."""
    depth = lambda r: r.count("/")
    pages = [r for r in rels if r.lower().endswith(".md")] or rels
    top = min(map(depth, pages))
    readme = sorted(r for r in pages if depth(r) == top and Path(r).stem.lower() in ("readme", "index"))
    return readme[0] if readme else min(pages, key=lambda r: (depth(r), len(r), r))


def graph_links(items: dict, owner: dict, modules: dict[str, str]) -> list[dict]:
    """Undirected edges for the map. tree = structure (module hub-and-spoke, module -> parent module,
    group hub -> member); ref = content (Markdown links, wikilinks, deps). A ref wins over a tree edge."""
    hub_of = {d: posixpath.join(d, f"{name}.md") for d, name in modules.items()}
    edges: dict[frozenset, tuple] = {}
    tree, free = set(), {}
    for rel, d in owner.items():
        if d is None:
            free.setdefault(items[rel]["group"], []).append(rel)
        elif rel != hub_of[d]:
            tree.add((hub_of[d], rel))
    for d, mid in hub_of.items():
        if d and (up := nearest_module(d.split("/")[:-1], modules)) is not None:
            tree.add((hub_of[up], mid))
    for rels in free.values():
        hub = group_hub(rels)
        tree |= {(hub, r) for r in rels if r != hub}
    for a, b in sorted(tree):
        edges[frozenset((a, b))] = ("tree", a, b)
    for rel, it in items.items():
        for t in it["links"]:
            k = frozenset((rel, t))
            if edges.get(k, ("tree",))[0] == "tree":
                edges[k] = ("ref", rel, t)
    return [{"source": a, "target": b, "kind": k} for k, a, b in sorted(edges.values())]


def build(repo, data_dir=None) -> dict:
    root = Path(repo).resolve()
    data = Path(data_dir) if data_dir else root / ".wiki"
    files = dict(scan(root))
    items, modules, bodies = {}, {}, {}
    for rel, raw in files.items():
        text = raw.decode("utf-8", "replace")
        p = posixpath.split(rel)
        stem, is_md = Path(rel).stem, rel.lower().endswith(".md")
        fm, body = frontmatter(text) if is_md else ({}, text)
        is_svg = rel.lower().endswith(".svg")
        kind = "page" if is_md else "figure" if is_svg else "exhibit"
        dir_name = posixpath.basename(p[0]) or root.name
        if is_md and "kind" in fm and stem.lower() == dir_name.lower():
            kind, modules[p[0]] = "module", stem
        if is_md:
            title = fm.get("title") or first_heading(body) or p[1]
        else:
            t = TITLE_RE.search(text)
            title = " ".join(html.unescape(t.group(1)).split()) if t and t.group(1).strip() else p[1]
        items[rel] = {"id": rel, "title": str(title), "kind": kind, "group": "", "path": rel,
                      "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                      "summary": summary(body) if is_md else "", "links": [],
                      "ids": sorted(set(ID_RE.findall(text)))}
        bodies[rel] = (fm, body if is_md else "")
    clusters = graphify_clusters(root)
    by_stem: dict[str, list[str]] = {}
    for rel in sorted(items, key=lambda r: (r.count("/"), r)):
        if rel.lower().endswith(".md"):
            by_stem.setdefault(Path(rel).stem.lower(), []).append(rel)
    module_ids = {name.lower(): (f"{d}/{name}.md" if d else f"{name}.md") for d, name in modules.items()}
    owner: dict[str, str | None] = {}  # item -> dir of its nearest enclosing module
    for rel, it in items.items():
        parts = rel.split("/")[:-1]
        owner[rel] = nearest_module(parts, modules)
        mod = modules[owner[rel]] if owner[rel] is not None else None
        it["group"] = mod or clusters.get(rel) or (parts[0] if parts else "root")
        if rel in clusters:
            it["cluster"] = clusters[rel]
        fm, body = bodies[rel]
        prose, links = FENCE_RE.sub("", body), set()
        for target in MDLINK_RE.findall(prose):
            if re.match(r"[a-z][a-z0-9+.-]*:|#", target, re.I):
                continue
            t = unquote(target.split("#")[0].split("?")[0])
            t = t.lstrip("/") if t.startswith("/") else posixpath.join(posixpath.dirname(rel), t)
            links.add(posixpath.normpath(t))
        for name in WIKILINK_RE.findall(prose):
            stem = posixpath.basename(name.strip())
            stem = stem[:-3] if stem.lower().endswith(".md") else stem
            if hits := by_stem.get(stem.lower()):
                links.add(hits[0])
        if it["kind"] == "module":
            deps = fm.get("deps") or []
            it["deps"] = [d for d in ([deps] if isinstance(deps, str) else deps) if d.lower() in module_ids]
            links |= {module_ids[d.lower()] for d in it["deps"]}
        it["links"] = sorted(t for t in links if t in items and t != rel)
    wiki = {"repo": root.name, "built": datetime.now().astimezone().isoformat(timespec="seconds"),
            "items": list(items.values()), "links": graph_links(items, owner, modules),
            "groups": dict(Counter(i["group"] for i in items.values()).most_common())}
    data.mkdir(parents=True, exist_ok=True)
    (data / "wiki.json").write_text(json.dumps(wiki, indent=1, ensure_ascii=False), "utf-8")
    return wiki


def build_line(wiki: dict, data: Path) -> str:
    k = Counter(i["kind"] for i in wiki["items"])
    e = Counter(link["kind"] for link in wiki["links"])
    return (f"wiki: {wiki['repo']} · {len(wiki['items'])} items ({k['page']} pages, {k['module']} modules, "
            f"{k['exhibit']} exhibits, {k['figure']} figures) · {len(wiki['groups'])} groups · {len(wiki['links'])} links "
            f"({e['tree']} tree, {e['ref']} ref) → {data / 'wiki.json'}")


# ---------- feedback (append-only JSONL) ----------

def append(data: Path, rec: dict) -> None:
    data.mkdir(parents=True, exist_ok=True)
    with LOCK, open(data / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_feedback(data: Path) -> list[dict]:
    """All feedback records with their latest status (resolution lines folded in)."""
    path, recs = data / "feedback.jsonl", {}
    if not path.exists():
        return []
    for line in path.read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("resolves") in recs:
            recs[r["resolves"]].update(status="resolved", note=r.get("note", ""), resolved=r.get("ts"))
        elif "id" in r and "resolves" not in r:
            recs[r["id"]] = r
    return list(recs.values())


def add_feedback(data: Path, items: dict, p) -> dict:
    if not isinstance(p, dict):
        raise ValueError("body must be a JSON object")
    item, kind, text, quote = p.get("item"), p.get("kind"), p.get("text"), p.get("quote")
    if not isinstance(item, str) or item not in items:
        raise ValueError("unknown item")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {'|'.join(KINDS)}")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError("text must be 1-4000 chars")
    if quote is not None and (not isinstance(quote, str) or len(quote) > 4000):
        raise ValueError("quote must be a string of at most 4000 chars")
    sha = p.get("sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{12,64}", sha):
        sha = items[item]["sha256"]
    now = datetime.now().astimezone()
    rec = {"id": f"F-{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "ts": now.isoformat(timespec="seconds"),
           "status": "open", "item": item, "sha256": sha, "kind": kind, "text": text}
    if quote:
        rec["quote"] = quote
    append(data, rec)
    return rec


def resolve(data: Path, fid: str, note: str) -> dict:
    if fid not in {r["id"] for r in load_feedback(data)}:
        raise KeyError(f"no feedback {fid}")
    rec = {"resolves": fid, "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "status": "resolved", "note": note}
    append(data, rec)
    return rec


# ---------- server ----------

def make_server(repo, data_dir=None, port=7790) -> ThreadingHTTPServer:
    root = Path(repo).resolve()
    data = Path(data_dir) if data_dir else root / ".wiki"
    state = {"wiki": build(root, data)}

    class Handler(BaseHTTPRequestHandler):
        server_version = "wiki"
        sys_version = ""

        def log_message(self, *args):
            pass

        def send(self, code, body=b"", ctype="text/plain; charset=utf-8", headers=()):
            if isinstance(body, str):
                body = body.encode()
            elif not isinstance(body, bytes):
                body, ctype = json.dumps(body, ensure_ascii=False).encode(), "application/json"
            self.send_response(code)
            for k, v in (("Content-Type", ctype), ("Content-Length", str(len(body))),
                         ("X-Content-Type-Options", "nosniff"), ("Cache-Control", "no-store"), *headers):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def items(self) -> dict:
            return {i["id"]: i for i in state["wiki"]["items"]}

        def item_file(self, query: dict, kind=None) -> Path | None:
            it = self.items().get(query.get("id", [""])[0])  # the id must be a scanned item: traversal guard
            if not it or (kind and it["kind"] != kind):
                return None
            p = (root / it["path"]).resolve()
            return p if p.is_relative_to(root) and p.is_file() else None

        def image(self, query: dict):
            """An image a page references, by repo-relative path; only inside the repo root."""
            rel = query.get("path", [""])[0]
            p = (root / rel).resolve()
            if (p.suffix.lower() not in IMG_EXT or not p.is_relative_to(root) or not p.is_file()
                    or p.stat().st_size > MAX_FILE):
                return self.send(404, "not found")
            self.send(200, p.read_bytes(), TYPES[p.suffix.lower()], (("Content-Security-Policy", SVG_CSP),))

        def static(self, rel: str):
            p = (ASSETS / rel).resolve()
            if not p.is_relative_to(ASSETS) or not p.is_file():
                return self.send(404, "not found")
            csp = (("Content-Security-Policy", UI_CSP),) if p.suffix == ".html" else ()
            self.send(200, p.read_bytes(), TYPES.get(p.suffix, "application/octet-stream"), csp)

        def guard(self) -> bool:
            host = self.headers.get("Host", "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost", "[::1]"):  # DNS-rebinding guard
                self.send(403, "forbidden host")
                return False
            return True

        def do_GET(self):
            if not self.guard():
                return
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/":
                return self.static("index.html")
            if u.path.startswith("/assets/"):
                return self.static(unquote(u.path[len("/assets/"):]))
            if u.path == "/api/wiki":
                state["wiki"] = build(root, data)  # rebuild on each load so edits show up on refresh
                return self.send(200, state["wiki"])
            if u.path == "/api/feedback":
                return self.send(200, load_feedback(data))
            if u.path == "/api/item":
                p = self.item_file(q)
                return self.send(200, p.read_bytes()) if p else self.send(404, "not found")
            if u.path == "/exhibit":
                p = self.item_file(q, "exhibit")
                if not p:
                    return self.send(404, "not found")
                return self.send(200, p.read_bytes(), TYPES[".html"],
                                 (("Content-Security-Policy", "sandbox allow-scripts"),))
            if u.path == "/img":
                return self.image(q)
            if u.path == "/figure":
                p = self.item_file(q, "figure")
                if not p:
                    return self.send(404, "not found")
                return self.send(200, p.read_bytes(), TYPES[".svg"], (("Content-Security-Policy", SVG_CSP),))
            self.send(404, "not found")

        def do_POST(self):
            if not self.guard():
                return
            if urlparse(self.path).path != "/api/feedback":
                return self.send(404, "not found")
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self.send(411, "length required")
            if n < 0 or n > MAX_BODY:
                self.close_connection = True
                if 0 < n <= 1 << 20:  # drain a bounded amount so the client reads the 413 cleanly
                    self.rfile.read(n)
                return self.send(413, {"error": f"body over {MAX_BODY} bytes"})
            body = self.rfile.read(n)
            if self.headers.get_content_type() != "application/json":
                return self.send(415, {"error": "expected application/json"})
            try:
                rec = add_feedback(data, self.items(), json.loads(body))
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            self.send(201, rec)

        def refuse(self):
            self.send(405, "method not allowed", headers=(("Allow", "GET, POST"),))

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = refuse

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.state = state
    return srv


# ---------- CLI ----------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wiki", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "serve", "feedback", "resolve"):
        s = sub.add_parser(name)
        s.add_argument("repo")
        s.add_argument("--data-dir")
        if name == "serve":
            s.add_argument("--port", type=int, default=7790)
            s.add_argument("--open", action="store_true")
        if name == "feedback":
            s.add_argument("--all", action="store_true")
            s.add_argument("--json", action="store_true")
        if name == "resolve":
            s.add_argument("fid")
            s.add_argument("--note", required=True)
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    if not repo.is_dir():
        ap.error(f"not a directory: {repo}")
    data = Path(a.data_dir).resolve() if a.data_dir else repo / ".wiki"

    if a.cmd == "build":
        print(build_line(build(repo, data), data))
    elif a.cmd == "serve":
        try:
            srv = make_server(repo, data, a.port)
        except OSError as e:
            sys.exit(f"wiki: cannot bind 127.0.0.1:{a.port}: {e}")
        url = f"http://localhost:{srv.server_address[1]}/"
        print(build_line(srv.state["wiki"], data))
        print(f"wiki: serving {url}  (Ctrl-C to stop)", flush=True)
        if a.open:
            subprocess.run(["open", url], check=False)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    elif a.cmd == "feedback":
        recs = [r for r in load_feedback(data) if a.all or r["status"] == "open"]
        if a.json:
            print(json.dumps(recs, indent=1, ensure_ascii=False))
        for r in [] if a.json else recs:
            quote = f'  > "{" ".join(r["quote"].split())[:120]}"' if r.get("quote") else ""
            state = "" if r["status"] == "open" else "[resolved] "
            print(f'{r["id"]}  {r["kind"]}  {r["item"]}@{r["sha256"][:12]}  {state}{" ".join(r["text"].split())}{quote}')
        if not recs and not a.json:
            print("wiki: no open feedback" if not a.all else "wiki: no feedback")
    elif a.cmd == "resolve":
        try:
            resolve(data, a.fid, a.note)
        except KeyError as e:
            sys.exit(f"wiki: {e.args[0]}")
        print(f"wiki: resolved {a.fid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

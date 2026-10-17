"""Hierarchy of a repo for the wiki map: root, modules, groups, dirs and files, plus per-module docs and diagrams.

modgate mode copies the discovery rules of `src/modgate/project.py` (not imported); plain mode infers units from
build manifests. Repo text is data: files are read, never executed or imported. Stdlib only.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path

from . import mdparse

__all__ = ["find_root", "load_config", "load_tree", "resolve_ref", "resolve_diagram", "is_test", "lang_of",
           "ConfigError", "DEFAULT_CONFIG", "LANG_BY_EXT", "TEXT_EXT", "BUCKET_OVER", "BUCKET_SIZE"]

CONFIG = "modgate.yaml"
CONFIG_JSON = (".wikimap", "config.json")
SKIP_NAMES = {"__pycache__", "node_modules", "build", "dist", "venv", ".venv", ".git", ".wiki"}
SKIP_SUFFIX = (".egg-info", ".pyc", ".nosync")
GENERATED = (".trace.md", ".changelog.md", ".activity.md")
TEXT_EXT = {".yaml", ".yml", ".toml", ".json", ".ini", ".cfg", ".env", ".rules", ".csv", ".txt"}
MANIFESTS = [("pyproject.toml", "python"), ("setup.py", "python"), ("package.json", "node"),
             ("CMakeLists.txt", "cmake"), ("Cargo.toml", "cargo"), ("go.mod", "go"), ("pom.xml", "maven"),
             ("build.gradle", "gradle"), ("build.gradle.kts", "gradle")]
PLAIN_OVERVIEW = ("README.md", "readme.md", "ARCHITECTURE.md", "index.md")
DOC_ROLES = ("brief", "req", "icd", "tests")
BUCKET_OVER, BUCKET_SIZE = 150, 100
MAX_DOC = 2 * 1024 * 1024
DEFAULT_CONFIG = {"ignore": [], "undoc": "public", "violations": [], "max_hook_lines": 12, "macros": {}}
MODULE_SHAPE = re.compile(r"^[a-z][a-z0-9_\-/]*$")
REQ_HEAD = re.compile(r"^(REQ|FEAT)-[A-Z0-9]+-\d+")

_FALLBACK_LANG = {
    ".py": "python", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".hxx": "cpp", ".ino": "cpp", ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js", ".ts": "ts", ".tsx": "ts",
    ".mts": "ts", ".go": "go", ".rs": "rust", ".java": "clike", ".kt": "clike", ".cs": "clike", ".swift": "clike",
    ".proto": "proto", ".sql": "sql", ".sh": "shell", ".bash": "shell",
}
try:  # the extractor package owns the table; fall back to the same table while it is absent
    from .lang.extract import LANG_BY_EXT as _EXT  # type: ignore
    LANG_BY_EXT: dict[str, str] = dict(_EXT) if isinstance(_EXT, dict) and _EXT else dict(_FALLBACK_LANG)
except Exception:  # noqa: BLE001 - any import failure means "use the fallback"
    LANG_BY_EXT = dict(_FALLBACK_LANG)


class ConfigError(ValueError):
    """`.wikimap/config.json` is unreadable (reported as E:ERROR by the CLI)."""


# ---------- root and config ----------

def find_root(start: Path) -> tuple[Path, bool]:
    """Nearest ancestor with modgate.yaml → (dir, True); else nearest `.git` ancestor → (dir, False); else (start, False)."""
    p = Path(start).resolve()
    if p.is_file() or not p.exists():
        p = p.parent
    for cand in (p, *p.parents):
        if (cand / CONFIG).is_file():
            return cand, True
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand, False
    return p, False


def load_config(root: Path) -> dict:
    """`.wikimap/config.json` merged over defaults. Missing → defaults. Invalid → ConfigError."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = Path(root).joinpath(*CONFIG_JSON)
    if not path.is_file():
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise ConfigError(f"{'/'.join(CONFIG_JSON)}: invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{'/'.join(CONFIG_JSON)}: must be a JSON object")
    types = {"ignore": list, "undoc": str, "violations": list, "max_hook_lines": int, "macros": dict, "systems": dict}
    for key, val in data.items():
        want = types.get(key)
        if want is not None and (not isinstance(val, want) or isinstance(val, bool)):
            raise ConfigError(f"{'/'.join(CONFIG_JSON)}: {key} must be {want.__name__}")
        cfg[key] = val
    if cfg["undoc"] not in ("public", "off"):
        raise ConfigError(f"{'/'.join(CONFIG_JSON)}: undoc must be \"public\" or \"off\"")
    cfg["ignore"] = [str(x) for x in cfg["ignore"]]
    cfg["violations"] = [str(x) for x in cfg["violations"]]
    return cfg


# ---------- helpers ----------

def lang_of(name: str) -> str | None:
    return LANG_BY_EXT.get(os.path.splitext(name)[1].lower())


def _indexable(dirname: str, name: str) -> str | None:
    """lang of a file that gets a node: a known language or a text file; module bind.yaml and .md are docs."""
    low = name.lower()
    if low.endswith(".md"):
        return None
    if dirname == "docs" and low.endswith(".bind.yaml"):
        return None
    lang = lang_of(name)
    if lang:
        return lang
    return "text" if os.path.splitext(low)[1] in TEXT_EXT else None


def is_test(rel_in_module: str) -> bool:
    parts = rel_in_module.split("/")
    if any(p in ("test", "tests", "__tests__") for p in parts[:-1]):
        return True
    name = parts[-1]
    return any(fnmatch.fnmatchcase(name, pat) for pat in ("test_*", "*_test.*", "*.test.*", "*.spec.*"))


def _join(base: str, rel: str) -> str:
    rel = rel.strip("/")
    if base in ("", "."):
        return rel or "."
    return f"{base}/{rel}" if rel and rel != "." else base


def _under(rel: str, base: str) -> bool:
    return base in ("", ".") or rel == base or rel.startswith(base + "/")


def _read(path: Path) -> str:
    try:
        if not path.is_file() or path.stat().st_size > MAX_DOC:
            return ""
        return path.read_bytes().decode("utf-8", errors="replace").lstrip("﻿")
    except OSError:
        return ""


def _vendored(rel: str, vendor: list[str]) -> bool:
    return any(rel == v or rel.startswith(v + "/") or fnmatch.fnmatchcase(rel, v) for v in vendor)


class _Dir:
    __slots__ = ("name", "rel", "path", "files", "dirs", "project", "card", "manifest", "has_unit", "n_idx", "has_code")

    def __init__(self, name: str, rel: str, path: Path):
        self.name, self.rel, self.path = name, rel, path
        self.files: list[str] = []
        self.dirs: list[_Dir] = []
        self.project = False
        self.card: tuple[str, dict, str] | None = None  # (module name, frontmatter, repo-rel overview)
        self.manifest: str | None = None
        self.has_unit = False
        self.n_idx = 0
        self.has_code = False


# ---------- tree builder ----------

class _Builder:
    def __init__(self, root: Path, modgate: bool, config: dict):
        self.root = root
        self.modgate = modgate
        self.config = config
        self.mg = mdparse.yaml_lite(_read(root / CONFIG)) if modgate else {}
        self.project = str(self.mg.get("project") or root.name)
        self.ignore = [str(x) for x in (self.mg.get("ignore") or [])] + [str(x) for x in config.get("ignore") or []]
        self.vendor = [str(v).rstrip("/") for v in (self.mg.get("vendor") or []) if str(v).strip()]
        self.nodes: dict[str, dict] = {}
        self.children: dict[str, list[str]] = {}
        self.files: dict[str, dict] = {}
        self.modules: dict[str, dict] = {}
        self.diagrams: dict[str, dict] = {}
        self.read: set[str] = set()
        self.minfo: dict[str, dict] = {}  # module name -> {"rel","sources","crit"}

    # --- scanning ---
    def skipped(self, name: str, rel: str) -> bool:
        if name.startswith(".") or name in SKIP_NAMES or name.endswith(SKIP_SUFFIX):
            return True
        return any(fnmatch.fnmatchcase(rel, p) or fnmatch.fnmatchcase(name, p) for p in self.ignore)

    def skipped_path(self, real: Path) -> bool:
        """A link target inside the root that the walk would skip (`.env`, `.git/config`, ignored globs)."""
        try:
            parts = real.relative_to(self.root.resolve()).parts
        except ValueError:
            return True
        return any(self.skipped(parts[i], "/".join(parts[:i + 1])) for i in range(len(parts)))

    def scan(self, path: Path, rel: str, name: str) -> _Dir:
        d = _Dir(name, rel, path)
        if rel != "." and (path / CONFIG).is_file():
            d.project = d.has_unit = True
            return d
        try:
            with os.scandir(path) as it:
                ents = sorted(it, key=lambda e: e.name)
        except OSError:
            return d
        for e in ents:
            erel = _join(rel, e.name)
            if self.skipped(e.name, erel):
                continue
            try:
                if e.is_symlink():
                    if e.is_dir():
                        continue  # never follow directory links (loops, links out of the root)
                    real = Path(e.path).resolve()
                    if not real.is_relative_to(self.root) or not real.is_file() or self.skipped_path(real):
                        continue
                    d.files.append(e.name)
                elif e.is_dir():
                    d.dirs.append(self.scan(Path(e.path), erel, e.name))
                elif e.is_file():
                    d.files.append(e.name)
            except OSError:
                continue
        self.classify(d)
        for sub in d.dirs:
            d.has_unit = d.has_unit or sub.has_unit or bool(sub.card) or bool(sub.manifest)
            d.n_idx += sub.n_idx
            d.has_code = d.has_code or sub.has_code
        for f in d.files:
            lang = _indexable(d.name, f)
            if lang:
                d.n_idx += 1
                d.has_code = d.has_code or lang != "text"
        return d

    def classify(self, d: _Dir) -> None:
        if self.modgate:
            wants = {d.name.lower() + ".md"}
            if d.rel == ".":
                wants.add(self.project.lower() + ".md")
            for f in d.files:
                if f.lower() in wants:
                    fm, _ = mdparse.frontmatter(_read(d.path / f))
                    if "kind" in fm:
                        d.card = (f[:-3], fm, _join(d.rel, f))
                        break
        else:
            names = set(d.files)
            for fname, kind in MANIFESTS:
                if fname in names:
                    d.manifest = kind
                    break
            if d.manifest is None and any(f.endswith(".csproj") for f in d.files):
                d.manifest = "dotnet"

    # --- nodes ---
    def add(self, node: dict) -> dict:
        nid = node["id"]
        self.nodes[nid] = node
        self.children.setdefault(nid, [])
        if node.get("parent") is not None:
            self.children.setdefault(node["parent"], []).append(nid)
        return node

    def rel_name(self, rel: str, parent: str) -> str:
        if parent in (None, "."):
            return rel
        p = self.nodes[parent]["path"]
        return rel[len(p) + 1:] if rel.startswith(p + "/") else rel.rsplit("/", 1)[-1]

    def file_node(self, d: _Dir, fname: str, parent: str, owner: str | None) -> None:
        lang = _indexable(d.name, fname)
        if not lang:
            return
        rel = _join(d.rel, fname)
        info = self.minfo.get(owner) if owner else None
        mrel = info["rel"] if info else "."
        inmod = rel[len(mrel) + 1:] if mrel != "." and rel.startswith(mrel + "/") else rel
        test = is_test(inmod)
        if self.modgate and info is not None:
            insrc = any(_under(rel, s) for s in info["sources"])
        else:
            insrc = not test
        vend = _vendored(rel, self.vendor)
        self.add({"id": rel, "parent": parent, "type": "file", "tier": "code", "kind": lang, "name": fname,
                  "title": fname, "path": rel, "mod": owner, "item": None, "lang": lang, "insrc": insrc,
                  "test": test, "vendor": vend})
        self.files[rel] = {"node": rel, "mod": owner, "lang": lang, "insrc": insrc, "test": test, "vendor": vend}

    def vendor_node(self, sub: _Dir, parent: str, owner: str | None) -> None:
        self.add({"id": sub.rel, "parent": parent, "type": "dir", "tier": "code", "kind": "vendor",
                  "name": self.rel_name(sub.rel, parent), "title": sub.rel, "path": sub.rel, "mod": owner,
                  "item": None, "vendor": True})

    def fill(self, d: _Dir, cid: str, owner: str | None, ctx: str) -> None:
        """Own files of container `cid` plus its child dirs. ctx: 'module' | 'group' (plain mode differs)."""
        for f in d.files:
            self.file_node(d, f, cid, owner)
        for sub in d.dirs:
            self.place(sub, cid, owner, ctx)

    def place(self, sub: _Dir, parent: str, owner: str | None, ctx: str) -> None:
        if _vendored(sub.rel, self.vendor):
            self.vendor_node(sub, parent, owner)
        elif sub.project:
            self.project_node(sub, parent, owner)
        elif self.modgate and sub.card:
            self.module_node(sub, parent, owner)
        elif not self.modgate and sub.manifest:
            self.module_node(sub, parent, owner)
        elif sub.has_unit:
            self.group_node(sub, parent, owner)
        elif not self.modgate and ctx == "group":
            if sub.has_code:
                self.module_node(sub, parent, owner)
        else:
            self.interior(sub, parent, owner)

    def interior(self, sub: _Dir, parent: str, owner: str | None) -> None:
        names = [sub.name]
        d = sub
        while True:
            own = [f for f in d.files if _indexable(d.name, f)]
            subs = [x for x in d.dirs if x.n_idx > 0 or _vendored(x.rel, self.vendor)]
            if not own and len(subs) == 1 and not _vendored(subs[0].rel, self.vendor):
                d = subs[0]
                names.append(d.name)
                continue
            break
        if d.n_idx == 0 and not any(_vendored(x.rel, self.vendor) for x in d.dirs):
            return
        self.add({"id": d.rel, "parent": parent, "type": "dir", "tier": "code", "kind": "dir",
                  "name": "/".join(names), "title": d.rel, "path": d.rel, "mod": owner, "item": None,
                  "vendor": False})
        for f in d.files:
            self.file_node(d, f, d.rel, owner)
        for x in d.dirs:
            if _vendored(x.rel, self.vendor):
                self.vendor_node(x, d.rel, owner)
            elif x.n_idx > 0:
                self.interior(x, d.rel, owner)

    def project_node(self, sub: _Dir, parent: str, owner: str | None) -> None:
        card = sub.path / f"{sub.name}.md"
        name = self.rel_name(sub.rel, parent)
        self.add({"id": sub.rel, "parent": parent, "type": "group", "tier": "sys", "kind": "project",
                  "name": name, "title": name, "summary": "", "path": sub.rel, "mod": owner,
                  "item": _join(sub.rel, card.name) if card.is_file() else None, "docs": []})

    def group_node(self, sub: _Dir, parent: str, owner: str | None) -> None:
        name = self.rel_name(sub.rel, parent)
        node = self.add({"id": sub.rel, "parent": parent, "type": "group", "tier": "sys", "kind": "group",
                         "name": name, "title": name, "summary": "", "path": sub.rel, "mod": owner, "item": None,
                         "docs": []})
        if not self.modgate:
            self.plain_overview(sub, node)
        self.fill(sub, sub.rel, owner, "group")

    def plain_overview(self, d: _Dir, node: dict) -> dict:
        names = set(d.files)
        pick = next((n for n in (*PLAIN_OVERVIEW, d.name + ".md") if n in names), None)
        if pick is None:
            return {}
        item = _join(d.rel, pick)
        text = _read(d.path / pick)
        self.read.add(item)
        fm, _ = mdparse.frontmatter(text)
        node["item"] = item
        node["title"] = mdparse.doc_title(text, node["name"])
        node["summary"] = mdparse.summary(text)
        node["docs"] = [{"item": item, "role": "overview", "title": node["title"]}]
        self.diagram(node["id"], item, text)
        return fm

    def diagram(self, cid: str, item: str, text: str) -> None:
        flow, line = mdparse.pick_diagram(text)
        if flow is not None:
            self.diagrams[cid] = {"doc": item, "flow": flow, "line": line}

    def module_node(self, d: _Dir, parent: str | None, owner: str | None, *, root_node: bool = False) -> str:
        if self.modgate:
            if d.card:
                name, fm, item = d.card
            else:
                name, fm, item = self.project, {"kind": "system"}, None
            kind = str(fm.get("kind") or "system")
        else:
            name = self.project if root_node else d.name
            fm, item, kind = {}, None, d.manifest or "dir"
        if name in self.modules:
            name = d.rel if d.rel != "." else f"{name}(root)"
        rel = d.rel
        nid = "." if root_node else rel
        node = {"id": nid, "parent": parent, "type": "root" if root_node else "module", "tier": "sys",
                "kind": kind, "name": name, "title": name, "summary": "", "path": rel, "mod": name,
                "item": item, "docs": []}
        self.add(node)
        if self.modgate:
            text = _read(self.root / item) if item else ""
            if item:
                self.read.add(item)
                node["title"] = mdparse.doc_title(text, name)
                node["summary"] = mdparse.summary(text)
                self.diagram(nid, item, text)
        else:
            fm = self.plain_overview(d, node)
        srcs = fm.get("sources")
        if self.modgate:
            if isinstance(srcs, (str, int)) and str(srcs).strip():
                srcs = [srcs]
            srcs = [str(s).rstrip("/") for s in (srcs if isinstance(srcs, list) else ["src", "include"]) if s is not None]
            sources = [_join(rel, s) for s in srcs if str(s).strip()]
        else:
            sources = [rel]
        deps = fm.get("deps")
        deps = [str(x) for x in deps] if isinstance(deps, list) else ([str(deps)] if deps else [])
        parent_crit = self.minfo[owner]["crit"] if owner in self.minfo else self.mg.get("criticality")
        crit = fm.get("criticality") or parent_crit
        self.minfo[name] = {"rel": rel, "sources": sources, "crit": crit, "dir": d}
        node.update({"crit": str(crit) if crit else None, "status": _s(fm.get("status")), "state": None,
                     "version": fm.get("version"), "deps": deps, "reqs": [], "icd": None})
        self.modules[name] = {"id": nid, "name": name, "kind": kind, "deps": deps, "closure": [],
                              "sources": sources, "docs": list(node["docs"]), "icd": None, "bind": {}, "reqs": {},
                              "overview": item, "parent": owner}
        if self.modgate:
            self.module_docs(name, d, node)
        self.fill(d, nid, name, "module")
        return nid

    def module_docs(self, name: str, d: _Dir, node: dict) -> None:
        m = self.modules[name]
        docs = []
        if node["item"]:
            docs.append({"item": node["item"], "role": "overview", "title": node["title"]})
        ddir = d.path / "docs"
        drel = _join(d.rel, "docs")
        texts: dict[str, str] = {}
        for role in DOC_ROLES:
            p = ddir / f"{name}.{role}.md"
            if p.is_file():
                rel = _join(drel, p.name)
                texts[role] = _read(p)
                self.read.add(rel)
                docs.append({"item": rel, "role": role, "title": mdparse.doc_title(texts[role], p.name)})
        for sub, pat, role in (("resources", "*.md", "resource"), ("diagrams", "*.svg", "figure")):
            sd = ddir / sub
            if sd.is_dir():
                for p in sorted(sd.glob(pat)):
                    if p.is_file() and not self.skipped(p.name, _join(drel, f"{sub}/{p.name}")):
                        rel = _join(drel, f"{sub}/{p.name}")
                        if role == "resource":
                            t = _read(p)
                            self.read.add(rel)
                            title = mdparse.doc_title(t, p.name)
                        else:
                            title = p.stem
                        docs.append({"item": rel, "role": role, "title": title})
        node["docs"] = m["docs"] = docs
        if "icd" in texts:
            item = _join(drel, f"{name}.icd.md")
            m["icd"] = item
            head = next((h for _, h, _ in mdparse.headings(texts["icd"]) if re.search(r"api|interface", h, re.I)), None)
            node["icd"] = {"item": item, "head": head}
        reqs = mdparse.req_lines(texts["req"]) if "req" in texts else {}
        if not reqs and ddir.is_dir():
            for p in sorted(ddir.glob(f"{name}.*.md")):
                if p.name.endswith(GENERATED) or p.name == f"{name}.req.md":
                    continue
                rel = _join(drel, p.name)
                t = texts.get(p.name[len(name) + 1:-3]) or _read(p)
                self.read.add(rel)
                for k, v in mdparse.req_lines(t).items():
                    reqs.setdefault(k, v)
        m["reqs"] = {k: v for k, v in reqs.items() if k.startswith("REQ-")}
        node["reqs"] = sorted(m["reqs"])
        tp = ddir / f"{name}.trace.md"
        if tp.is_file():
            self.read.add(_join(drel, tp.name))
            node["state"] = mdparse.trace_state(_read(tp))
        bp = ddir / f"{name}.bind.yaml"
        if bp.is_file():
            self.read.add(_join(drel, bp.name))
            m["_bind_raw"] = mdparse.bind_yaml(_read(bp))

    # --- post passes ---
    def finish(self) -> None:
        self.collapse_groups()
        for name, m in self.modules.items():
            raw = m.pop("_bind_raw", None)
            if raw is None:
                continue
            rel = self.minfo[name]["rel"]
            own = sorted((r[len(rel) + 1:] if rel != "." else r) for r, f in self.files.items() if f["mod"] == name)
            bind = {}
            for req, paths in raw.items():
                out: list[str] = []
                for b in paths:
                    hits = [f for f in own if f == b or f.startswith(b + "/")]
                    out.extend(_join(rel, h) for h in (hits or [b]))
                bind[req] = sorted(set(out))
            m["bind"] = bind
        for name, m in self.modules.items():
            seen: list[str] = []
            todo = list(m["deps"])
            while todo:
                dep = todo.pop(0)
                if dep == name or dep in seen:
                    continue
                seen.append(dep)
                if dep in self.modules:
                    todo.extend(self.modules[dep]["deps"])
            m["closure"] = sorted(seen)
        for nid in list(self.children):
            self.sort(nid)
        self.bucket()
        for nid, node in self.nodes.items():
            node["children_n"] = len(self.children.get(nid, []))

    def sort(self, nid: str) -> None:
        self.children[nid].sort(key=lambda c: (self.nodes[c]["tier"] != "sys", self.nodes[c]["name"].lower(), c))

    def depth(self, nid: str) -> int:
        n, k = self.nodes[nid], 0
        while n.get("parent") is not None:
            n, k = self.nodes[n["parent"]], k + 1
        return k

    def collapse_groups(self) -> None:
        for gid in sorted((i for i, n in self.nodes.items() if n["type"] == "group"), key=self.depth):
            g = self.nodes.get(gid)
            if g is None or g["kind"] != "group" or g.get("item"):
                continue
            kids = self.children.get(gid, [])
            if len(kids) != 1:
                continue
            c = self.nodes[kids[0]]
            if c["type"] != "group" or c["kind"] != "group":
                continue
            parent = g["parent"]
            c["parent"] = parent
            c["name"] = f"{g['name']}/{c['name']}"
            c["title"] = c["name"] if not c.get("item") else c["title"]
            sib = self.children[parent]
            sib[sib.index(gid)] = c["id"]
            del self.nodes[gid]
            del self.children[gid]

    def bucket(self) -> None:
        for cid in list(self.children):
            kids = self.children[cid]
            for tier in ("sys", "code"):
                mine = [k for k in kids if self.nodes[k]["tier"] == tier]
                if len(mine) <= BUCKET_OVER:
                    continue
                mine.sort(key=lambda k: (self.nodes[k]["name"].lower(), k))
                prefix = "" if cid == "." else cid + "/"
                new: list[str] = []
                for i in range(0, len(mine), BUCKET_SIZE):
                    chunk = mine[i:i + BUCKET_SIZE]
                    first, last = self.nodes[chunk[0]]["name"], self.nodes[chunk[-1]]["name"]
                    bid = f"{prefix}~{first}-{last}"
                    self.nodes[bid] = {"id": bid, "parent": cid, "type": "bucket", "tier": tier, "kind": "bucket",
                                       "name": f"{first}–{last}", "title": f"{first}–{last}", "path": cid,
                                       "mod": self.nodes[cid].get("mod"), "item": None}
                    self.children[bid] = chunk
                    for k in chunk:
                        self.nodes[k]["parent"] = bid
                    new.append(bid)
                keep = [k for k in kids if self.nodes[k]["tier"] != tier]
                self.children[cid] = kids = keep + new
                self.sort(cid)
                kids = self.children[cid]

    def build(self) -> dict:
        top = self.scan(self.root, ".", self.root.name)
        if self.modgate:
            self.module_node(top, None, None, root_node=True)
        elif top.manifest or not top.has_unit:
            self.module_node(top, None, None, root_node=True)
            self.nodes["."]["kind"] = top.manifest or "dir"
        else:
            node = self.add({"id": ".", "parent": None, "type": "root", "tier": "sys", "kind": "dir",
                             "name": self.project, "title": self.project, "summary": "", "path": ".",
                             "mod": None, "item": None, "docs": []})
            self.plain_overview(top, node)
            self.fill(top, ".", None, "group")
        self.finish()
        out = {"root": str(self.root), "modgate": self.modgate, "project": self.project, "nodes": self.nodes,
               "children": self.children, "files": self.files, "modules": self.modules,
               "diagrams": self.diagrams, "config": self.config, "read": sorted(self.read),
               "vendor": self.vendor, "ignore": self.ignore, "criticality": _s(self.mg.get("criticality"))}
        areas = (self.config.get("systems") or {}).get("areas") if isinstance(self.config.get("systems"), dict) else None
        if areas:
            self.areas(out, areas)
        return out

    # --- logical areas (Systems lens only; the physical tree stays as scanned) ---
    def areas(self, out: dict, specs: list) -> None:
        """Add `systems.areas` from the config: area group nodes under the root and `sparent` overrides.

        Members keep their physical parent in `nodes`; `out["sparent"]` {member id: area id} re-parents them
        in the Systems lens only. An area's diagram is the first flowchart under its `doc#Heading`.
        """
        sparent: dict[str, str] = {}
        info: dict[str, dict] = {}
        for spec in specs if isinstance(specs, list) else []:
            if not isinstance(spec, dict):
                continue
            aid = str(spec.get("id") or "").strip()
            if not MODULE_SHAPE.match(aid) or "/" in aid or aid in self.nodes:
                continue
            title = str(spec.get("title") or aid)
            doc, _, anchor = str(spec.get("doc") or "").partition("#")
            doc = doc.strip().strip("/")
            text = ""
            if doc and not self.skipped_path((self.root / doc).resolve()):
                text = _read(self.root / doc)
                if text:
                    self.read.add(doc)
            summary, flow, line = _area_section(text, anchor.strip())
            self.add({"id": aid, "parent": ".", "type": "group", "tier": "sys", "kind": "area", "name": title,
                      "title": title, "summary": summary, "path": ".", "mod": None,
                      "item": doc if text else None, "docs": [doc] if text else []})
            self.children["."].remove(aid)  # the physical root never lists an area
            self.nodes[aid]["children_n"] = 0
            if flow is not None:
                self.diagrams[aid] = {"doc": doc, "flow": flow, "line": line}
            members, missing = [], []
            for raw in spec.get("members") or []:
                ref = str(raw).strip().strip("/")
                nid = ref if ref in self.nodes and self.nodes[ref]["tier"] == "sys" else \
                    resolve_ref(out, ".", ref, ref)
                if nid is None or nid == "." or nid in sparent or self.nodes[nid].get("kind") == "area":
                    missing.append(ref)
                    continue
                sparent[nid] = aid
                members.append(nid)
            info[aid] = {"title": title, "doc": doc or None, "anchor": anchor.strip() or None,
                         "members": members, "missing": missing}
        out["read"] = sorted(self.read)
        cfg = Path(self.root).joinpath(*CONFIG_JSON)
        if info and cfg.is_file():
            out["read"] = sorted(set(out["read"]) | {"/".join(CONFIG_JSON)})
        out["sparent"] = sparent
        out["areas"] = info


def _area_section(text: str, anchor: str) -> tuple[str, dict | None, int]:
    """(first paragraph, parsed flowchart | None, fence line) under heading `anchor` (whole doc when empty)."""
    if not text:
        return "", None, 0
    _, start = mdparse.frontmatter(text)
    lines = text.splitlines()
    lo, hi, level = start, len(lines) + 1, 0
    if anchor:
        hs = mdparse.headings(text)
        hit = next((h for h in hs if h[1].lower() == anchor.lower()), None)
        if hit is None:
            return "", None, 0
        level, lo = hit[0], hit[2] + 1
        hi = next((h[2] for h in hs if h[2] > hit[2] and h[0] <= level), hi)
    para: list[str] = []
    fenced = False
    for raw in lines[max(lo, 1) - 1:hi - 1]:
        t = raw.strip()
        if t.startswith(("```", "~~~")):
            fenced = not fenced
            if para:
                break
            continue
        if fenced or t.startswith("#") or t.startswith(">") or t.startswith("|"):
            if para:
                break
            continue
        if not t:
            if para:
                break
            continue
        para.append(t)
    summary = " ".join(para)
    if not anchor:
        flow, line = mdparse.pick_diagram(text)
        return summary, flow, line
    for b in mdparse.mermaid_blocks(text):
        if lo <= b["line"] < hi and mdparse._FLOW_HDR.match(mdparse._first_stmt(b["src"])):
            return summary, mdparse.parse_flowchart(b["src"], b["line"]), b["line"]
    return summary, None, 0


def _s(v) -> str | None:
    return None if v is None or v == "" else str(v)


def load_tree(root: Path, *, modgate: bool, config: dict | None = None) -> dict:
    """Build the hierarchy (§2.3). Never executes repo content; unreadable files are skipped.

    Result: {"root","modgate","project","nodes":{id:node},"children":{id:[ids]},
             "files":{rel:{"node","mod","lang","insrc","test","vendor"}},"modules":{name:{…}},
             "diagrams":{container:{"doc","flow","line"}},"config","read":[doc rels],"vendor","ignore","criticality"}
    """
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(config or {})
    return _Builder(Path(root).resolve(), bool(modgate), cfg).build()


# ---------- Mermaid node → tree node ----------

def _anc_depth(tree: dict, nid: str) -> tuple[list[str], int]:
    nodes, chain = tree["nodes"], []
    cur = nodes.get(nid, {}).get("parent")
    while cur is not None and cur in nodes:
        chain.append(cur)
        cur = nodes[cur].get("parent")
    return chain, len(chain)


def _base(nid: str) -> str:
    return nid.rsplit("/", 1)[-1]


def resolve_ref(tree: dict, container: str, label: str, mid: str, own_names: dict[str, str] | None = None) -> str | None:
    """Map a Mermaid node of `container`'s diagram to a tree node id (§4.3), or None (→ actor)."""
    nodes = tree["nodes"]
    cands = mdparse.label_candidates(label, mid)
    pool = []
    for nid, n in nodes.items():
        if n["type"] not in ("module", "group", "root"):
            continue  # the container itself stays a candidate, but only in the whole-tree pass (it is not inside)
        anc, depth = _anc_depth(tree, nid)
        pool.append((nid, n, container in anc, depth))
    matchers = (
        lambda nid, n, c: n["type"] in ("module", "root") and mdparse.norm(n["name"]) == c,
        lambda nid, n, c: n["type"] == "group" and mdparse.norm(_base(nid)) == c,
        lambda nid, n, c: nid != "." and (mdparse.norm(nid) == c or mdparse.norm(nid).endswith("/" + c)),
        lambda nid, n, c: "/" in c and (
            (n["type"] in ("module", "root") and mdparse.norm(n["name"]) == c.rsplit("/", 1)[-1])
            or (n["type"] == "group" and mdparse.norm(_base(nid)) == c.rsplit("/", 1)[-1])),
    )
    for c in cands:
        for inside in (True, False):
            scope = [p for p in pool if p[2]] if inside else pool
            for match in matchers:
                hits = [(nid != container, depth, nid) for nid, n, _, depth in scope if match(nid, n, c)]
                if hits:
                    return min(hits)[2]
    if own_names:
        idx: dict[str, str] = {}
        for k, v in sorted(own_names.items()):
            idx.setdefault(mdparse.norm(k), v)
            idx.setdefault(mdparse.norm(re.split(r"::|\.", k)[-1]), v)
        for c in cands:
            if c in idx:
                return idx[c]
    return None


def resolve_diagram(tree: dict, container: str, own_names: dict[str, str] | None = None) -> dict | None:
    """Resolve every node and edge of `container`'s diagram.

    → {"doc","line","nodes":{mid:{"label","ref","id","ext","shape","kind","line","sub"}},
       "edges":[{"s","t","ms","mt","label","dash","thick","line"}],"diagnode":[mid],"skipped":int}
    `ref` is the matched tree/symbol id or None; `id` is ref or the actor id `<container>#m:<mid>`;
    `kind` (unmatched only) is ext | req | actor; `shape` is "module" when the label head is module-shaped.
    """
    d = tree.get("diagrams", {}).get(container)
    if not d:
        return None
    flow = d["flow"]
    out: dict[str, dict] = {}
    items = [(mid, n, False) for mid, n in flow["nodes"].items()] + [(sid, s, True) for sid, s in flow["subgraphs"].items()]
    for mid, n, sub in items:
        ref = resolve_ref(tree, container, n["label"], mid, own_names)
        head = mdparse.label_head(n["label"])
        ext = bool(n.get("ext"))
        kind = None if ref else ("ext" if ext else "req" if REQ_HEAD.match(head) else "actor")
        out[mid] = {"label": n["label"], "ref": ref, "id": ref or f"{container}#m:{mid}", "ext": ext,
                    "shape": "module" if MODULE_SHAPE.match(head) else "other", "kind": kind,
                    "line": n.get("line"), "sub": sub}
    edges = [{"s": out[e["s"]]["id"], "t": out[e["t"]]["id"], "ms": e["s"], "mt": e["t"], "label": e["label"],
              "dash": e["dash"], "thick": e["thick"], "line": e["line"]}
             for e in flow["edges"] if e["s"] in out and e["t"] in out]
    diag = [mid for mid, n in out.items() if n["ref"] is None and not n["ext"] and n["shape"] == "module"]
    return {"doc": d["doc"], "line": d["line"], "nodes": out, "edges": edges, "diagnode": diag,
            "skipped": flow.get("skipped", 0)}

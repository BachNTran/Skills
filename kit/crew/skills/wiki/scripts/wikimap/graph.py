"""The wiki map model: one tree of nodes (root → modules/groups → dirs → files → symbols), base edges, and
per-level lifting for the Systems and Code lenses (spec §2.4–§2.7, §5, §6).

`build_map` walks the tree (`tree.load_tree`), extracts every code file through a content-hash cache
(`<data>/map/cache.json`), builds symbol nodes (merging C/C++ declarations into definitions), resolves
Mermaid interactions, calls, imports, inheritance and contracts (`resolve.py`), and writes the last model to
`<data>/map/map.json`. It never writes inside the repo. Repo text is data: nothing is executed. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from . import mdparse
from . import tree as T
from .lang.extract import ADAPTER_VERSION, empty as _empty_rec, extract as _extract, lang_of as _lang_of
from .resolve import CLASS_KINDS, Resolver, family

__all__ = ["Map", "build_map", "default_data_dir", "MAP_DIR"]

MAP_DIR = "map"
LENSES = ("systems", "code")
CODE_KINDS = ("call", "import", "inherit", "contract", "data")
KIND_ORDER = ("flow", "dep") + CODE_KINDS
MAX_SOURCE = 1 << 20
SYM_BUCKET_OVER, SYM_BUCKET_SIZE = T.BUCKET_OVER, T.BUCKET_SIZE
HEADER_EXT = (".h", ".hh", ".hpp", ".hxx")
NO_COV_KINDS = frozenset({"ctor", "test", "macro", "namespace"})
TYPE_RANK = {"root": 0, "module": 0, "group": 0, "actor": 0, "own": 0, "bucket": 1, "dir": 1, "file": 1,
             "symbol": 2}
NODE_FIELDS = ("id", "parent", "type", "tier", "kind", "name", "title", "summary", "path", "mod", "item", "docs",
               "crit", "status", "state", "version", "deps", "reqs", "lang", "lines", "insrc", "test", "vendor",
               "qual", "key", "sig", "params", "pub", "src", "decl", "doc", "doc_src", "icd", "impls",
               "children_n", "badges")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha12(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def default_data_dir(root: Path) -> Path:
    """`<root>/.wiki` when it exists or is git-ignored, else `$XDG_CACHE_HOME/wiki/<sha12 of root>` (O2)."""
    root = Path(root).resolve()
    local = root / ".wiki"
    try:
        ignored = any(ln.strip() in (".wiki", ".wiki/", "/.wiki", "/.wiki/")
                      for ln in (root / ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        ignored = False
    if local.is_dir() or ignored:
        return local
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "wiki" / hashlib.sha256(str(root).encode()).hexdigest()[:12]


def own_id(cid: str) -> str:
    return f"{cid}/:own"


def is_own(nid: str) -> bool:
    return isinstance(nid, str) and nid.endswith("/:own")


def own_base(nid: str) -> str:
    return nid[: -len("/:own")]


# ---------------------------------------------------------------- cache

class _Cache:
    """`<data>/map/cache.json`: {"v":1,"adapter","files":{rel:[mtime_ns,size,sha12,rec]},"docs":{rel:[…,sha]}}."""

    def __init__(self, data: Path, adapter: str):
        self.path = Path(data) / MAP_DIR / "cache.json"
        self.adapter = adapter
        self.old_files: dict = {}
        self.old_docs: dict = {}
        self.map_rev = None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("v") == 1 and raw.get("adapter") == adapter:
                self.old_files = raw.get("files") or {}
                self.old_docs = raw.get("docs") or {}
                self.map_rev = raw.get("map_rev")
        except (OSError, ValueError):
            pass
        self.files: dict = {}
        self.docs: dict = {}
        self.dirty = False
        self.extracted = 0
        self.reused = 0

    def file(self, root: Path, rel: str, *, code: bool, cfg: dict) -> tuple[str, dict] | None:
        p = root / rel
        try:
            st = p.stat()
        except OSError:
            return None
        old = self.old_files.get(rel)
        if (isinstance(old, list) and len(old) == 4 and old[0] == st.st_mtime_ns and old[1] == st.st_size
                and isinstance(old[3], dict)):
            self.files[rel] = old
            self.reused += 1
            return old[2], old[3]
        if st.st_size > MAX_SOURCE:
            # never read a big data file whole: it is skipped, identified by size and mtime only
            sha = _sha12(f"size:{st.st_size}:{st.st_mtime_ns}".encode())
            rec = _empty_rec((_lang_of(rel) or "text") if code else "text")
            rec["skip"], rec["lines"] = "size", 0
            self.files[rel] = [st.st_mtime_ns, st.st_size, sha, rec]
            self.dirty = True
            return sha, rec
        try:
            data = p.read_bytes()
        except OSError:
            return None
        sha = _sha12(data)
        if isinstance(old, list) and len(old) == 4 and old[2] == sha and isinstance(old[3], dict):
            rec = old[3]
            self.reused += 1
        else:
            if code:
                rec = _extract(rel, data, cfg)
                self.extracted += 1
            else:
                rec = _empty_rec("text")
                if b"\x00" in data[:8192]:
                    rec["skip"] = "binary"
                elif len(data) > MAX_SOURCE:
                    rec["skip"] = "size"
            rec["lines"] = data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1)
        self.files[rel] = [st.st_mtime_ns, st.st_size, sha, rec]
        self.dirty = True
        return sha, rec

    def doc(self, root: Path, rel: str) -> str | None:
        p = root / rel
        try:
            st = p.stat()
        except OSError:
            return None
        old = self.old_docs.get(rel)
        if isinstance(old, list) and len(old) == 3 and old[0] == st.st_mtime_ns and old[1] == st.st_size:
            self.docs[rel] = old
            return old[2]
        try:
            if st.st_size > T.MAX_DOC:  # not read by the tree either; identified by size and mtime
                sha = _sha12(f"size:{st.st_size}:{st.st_mtime_ns}".encode())
            else:
                sha = _sha12(p.read_bytes())
        except OSError:
            return None
        self.docs[rel] = [st.st_mtime_ns, st.st_size, sha]
        self.dirty = True
        return sha

    def save(self, rev: str) -> None:
        if not self.dirty and set(self.files) == set(self.old_files) and set(self.docs) == set(self.old_docs) \
                and self.map_rev == rev:
            return
        body = {"v": 1, "adapter": self.adapter, "files": self.files, "docs": self.docs, "map_rev": rev}
        _atomic_write(self.path, json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


# ---------------------------------------------------------------- build

def _last(q: str) -> str:
    return re.split(r"::|\.", q)[-1] if q else q


class _Build:
    def __init__(self, root: Path, data: Path, config: dict, modgate: bool):
        self.root, self.data, self.config, self.modgate = root, data, config, modgate
        self.adapter = ADAPTER_VERSION + ":" + _sha12(json.dumps(config.get("macros") or {}, sort_keys=True).encode())
        self.cache = _Cache(data, self.adapter)

    def run(self) -> "Map":
        t0 = time.monotonic()
        tr = T.load_tree(self.root, modgate=self.modgate, config=self.config)
        self.tr = tr
        self.nodes: dict[str, dict] = tr["nodes"]
        self.children: dict[str, list[str]] = tr["children"]
        self.modules: dict[str, dict] = tr["modules"]
        self.files: dict[str, dict] = {}
        self.meta: dict[str, dict] = {}
        self.loc: dict[tuple, list] = {}
        self.extract_files()
        t_ex = time.monotonic()
        if self.cache.dirty and t_ex - t0 > 2.0:
            # a long extraction is saved before resolving, so a build killed by a hook timeout still progresses
            try:
                self.cache.save(self.cache.map_rev)
            except OSError:
                pass
        self.make_symbols()
        self.edges: list[dict] = []
        self.diagrams: dict[str, dict] = {}
        self.make_diagrams()
        res = self.resolve()
        self.make_deps()
        self.edges.sort(key=lambda e: (e["k"], e["s"], e["t"], e.get("file") or "", e.get("line") or 0,
                                       e.get("label") or ""))
        self.mark_x()
        self.finish()
        m = Map()
        m.root, m.data, m.modgate, m.project = self.root, self.data, self.modgate, tr["project"]
        m.config = self.config
        m.nodes, m.children, m.edges, m.files, m.modules = self.nodes, self.children, self.edges, self.files, self.modules
        m.diagrams = self.diagrams
        m.sparent, m.areas = dict(tr.get("sparent") or {}), dict(tr.get("areas") or {})
        m.rev = self.compute_rev(tr)
        m.built = _now()
        calls = [e for e in self.edges if e["k"] == "call"]
        hi = sum(1 for e in calls if e["conf"] >= 0.8)
        m.stats = {"files": len(self.files), "symbols": sum(1 for n in self.nodes.values() if n["type"] == "symbol"),
                   "edges": len(self.edges), "resolved_hi": round(hi / len(calls), 3) if calls else 0.0,
                   "unresolved": res.unresolved, "truncated": False,
                   "seconds": 0.0, "extracted": self.cache.extracted, "reused": self.cache.reused}
        m.cache_stats = {"extracted": self.cache.extracted, "reused": self.cache.reused}
        m._sig = _signature(self.root, tr)
        m._init()
        try:
            self.cache.save(m.rev)
            mp = self.data / MAP_DIR / "map.json"
            if self.cache.map_rev != m.rev or not mp.is_file() or self.cache.dirty:
                _atomic_write(mp, json.dumps({"v": 1, "rev": m.rev, "built": m.built, "modgate": m.modgate,
                                              "nodes": m.nodes, "edges": m.edges},
                                             sort_keys=True, ensure_ascii=False))
        except OSError:
            pass  # a read-only data dir only costs the next build its cache
        m.stats["seconds"] = round(time.monotonic() - t0, 3)
        warm = round(time.monotonic() - t_ex, 3)  # what a warm rebuild costs: everything but extraction
        try:
            bp = self.data / MAP_DIR / "build.json"
            old = json.loads(bp.read_text(encoding="utf-8")) if bp.is_file() else {}
            if (not isinstance(old, dict) or "warm_s" not in old
                    or abs(float(old.get("warm_s") or 0) - warm) > 0.25 * max(warm, 0.2)):
                _atomic_write(bp, json.dumps({"v": 1, "warm_s": warm, "files": len(self.files)}))
        except (OSError, ValueError, TypeError):
            pass
        return m

    # --- files ---
    def extract_files(self) -> None:
        cfg = {"macros": self.config.get("macros") or {}}
        for rel in sorted(self.tr["files"]):
            info = dict(self.tr["files"][rel])
            info.update({"sha": None, "rec": None})
            node = self.nodes.get(info.get("node") or rel)
            if not info.get("vendor"):
                got = self.cache.file(self.root, rel, code=info.get("lang") != "text", cfg=cfg)
                if got:
                    info["sha"], info["rec"] = got
                    rec = got[1]
                    if rec.get("lang") and rec["lang"] != info.get("lang") and info.get("lang") != "text":
                        info["lang"] = rec["lang"]
                    if node is not None:
                        node["lang"] = node["kind"] = info["lang"]
                        node["lines"] = rec.get("lines") or 0
                        node["src"] = [rel, 1, max(1, rec.get("lines") or 1)]
            self.files[rel] = info

    # --- symbols ---
    def make_symbols(self) -> None:
        groups: dict[str, list] = {}
        order: list[str] = []
        for rel in sorted(self.files):
            info = self.files[rel]
            rec = info.get("rec")
            if not rec or info.get("vendor") or rec.get("skip"):
                continue
            fam = family(rec.get("lang") or info.get("lang"))
            mod = info.get("mod")
            mid = (self.modules.get(mod) or {}).get("id") or "."
            for s in rec.get("symbols") or []:
                if not s.get("qual"):
                    continue
                local = "(anon)" in s["qual"] or (s.get("kind") == "function" and s.get("static"))
                if fam == "c" and not local and s.get("kind") not in ("test",):
                    key = f"cpp:{mid}:{s['qual']}~{s.get('arity') or 0}"
                else:
                    key = f"\0{rel}\0{s['qual']}\0{s.get('line')}"
                if key not in groups:
                    groups[key] = []
                    order.append(key)
                groups[key].append((rel, s, rec))
        placed: list[tuple] = []  # (key, rel, primary, partner, extras(merged decls))
        for key in order:
            ents = groups[key]
            if key.startswith("\0"):
                placed.append((None, ents[0][0], ents[0], None, []))
                continue
            defs = sorted((e for e in ents if not e[1].get("decl")), key=lambda e: (e[0].endswith(HEADER_EXT), e[0], e[1]["line"]))
            decls = sorted((e for e in ents if e[1].get("decl")), key=lambda e: (not e[0].endswith(HEADER_EXT), e[0], e[1]["line"]))
            if defs:
                prim, partner, rest = defs[0], (decls[0] if decls else None), decls[1:]
                placed.append((key, prim[0], prim, partner, rest))
                for extra in defs[1:]:
                    placed.append((None, extra[0], extra, None, []))
            else:
                placed.append((key, decls[0][0], decls[0], None, decls[1:]))
        count: dict[tuple, int] = {}
        for key, rel, prim, _, _ in placed:
            count[(rel, prim[1]["qual"])] = count.get((rel, prim[1]["qual"]), 0) + 1
        used: set[str] = set()
        by_file_qual: dict[tuple, str] = {}
        built: list[tuple[str, dict, str]] = []
        for key, rel, prim, partner, rest in placed:
            s = prim[1]
            nid = f"{rel}#{s['qual']}"
            if count[(rel, s["qual"])] > 1:
                nid = f"{nid}~{s.get('arity') or 0}"
            base, k = nid, 2
            while nid in used or nid in self.nodes:
                nid, k = f"{base}~{k}", k + 1
            used.add(nid)
            node, meta = self.symbol_node(nid, key, rel, prim, partner, rest)
            self.nodes[nid] = node
            self.meta[nid] = meta
            by_file_qual.setdefault((rel, s["qual"]), nid)
            built.append((nid, s, rel))
            for r, sym, _ in [prim] + ([partner] if partner else []) + list(rest):
                self.loc.setdefault((r, sym["qual"]), []).append((sym.get("line") or 0, sym.get("end") or 0, nid))
        for nid, s, rel in built:
            parent_q = s.get("parent")
            parent = by_file_qual.get((rel, parent_q)) if parent_q else None
            if parent is None or parent == nid:
                parent = self.files[rel].get("node") or rel
                if parent_q and self.nodes[nid]["kind"] in ("method", "ctor") and family(self.nodes[nid]["lang"]) == "c":
                    self.nodes[nid]["name"] = f"{_last(parent_q)}::{self.nodes[nid]['name']}"
            self.nodes[nid]["parent"] = parent
            self.children.setdefault(parent, []).append(nid)
            self.children.setdefault(nid, [])
        for v in self.loc.values():
            v.sort()

    def symbol_node(self, nid, key, rel, prim, partner, rest):
        _, s, rec = prim
        d = partner[1] if partner else None
        info = self.files[rel]
        others = [d] if d else []
        others += [e[1] for e in rest]
        doc, doc_src = s.get("doc"), ("self" if s.get("doc") else None)
        if not doc and d and d.get("doc"):
            doc, doc_src = d["doc"], "decl"
        params_src = d if (d and doc_src == "decl") else s
        reqs = set()
        for r, sym, rr in [prim] + ([partner] if partner else []) + list(rest):
            for q in rr.get("reqs") or []:
                if q.get("from") == sym["qual"]:
                    reqs.add(q["id"])
        flags = {f: bool(s.get(f) or any(o.get(f) for o in others)) for f in ("virtual", "pure", "override", "static")}
        ignore = sorted(set(s.get("ignore") or []).union(*[set(o.get("ignore") or []) for o in others]))
        kind = s.get("kind") or "function"
        if d and d.get("kind") in ("function", "method", "ctor"):
            # `int Geo::area(…)` in a .cpp cannot tell a namespace from a class; the header declaration can
            kind = d["kind"]
        node = {"id": nid, "parent": None, "type": "symbol", "tier": "code", "kind": kind,
                "name": s.get("name") or _last(s["qual"]), "title": s["qual"], "summary": "", "path": rel,
                "mod": info.get("mod"), "item": None, "lang": info.get("lang"), "qual": s["qual"],
                "key": key or nid, "sig": (d or s).get("sig") or "", "params": list(params_src.get("params") or []),
                "arity": s.get("arity") or 0, "pub": bool((d or s).get("pub")),
                "src": [rel, s.get("line") or 1, s.get("end") or s.get("line") or 1],
                "decl": [partner[0], d.get("line") or 1] if d else None, "doc": doc, "doc_src": doc_src,
                "test": bool(s.get("test")), "insrc": bool(info.get("insrc")), "vendor": False, "impls": [],
                "sig_hash": s.get("sig_hash"), "body_hash": s.get("body_hash"), "ignore": ignore,
                "reqs": sorted(reqs), **flags}
        mem = dict(s.get("members") or {})
        for o in others:
            for k2, v in (o.get("members") or {}).items():
                mem.setdefault(k2, v)
        meta = {"name_short": s.get("name") or _last(s["qual"]), "parent_q": s.get("parent"), "members": mem,
                "bases": list(s.get("bases") or []) or [b for o in others for b in (o.get("bases") or [])],
                "words": s.get("words") or []}
        return node, meta

    def sys_owner(self, nid: str) -> str:
        cur = self.nodes[nid].get("parent")
        while cur is not None and self.nodes[cur]["tier"] != "sys":
            cur = self.nodes[cur].get("parent")
        return cur or "."

    # --- diagrams and actors ---
    def make_diagrams(self) -> None:
        own: dict[str, dict[str, str]] = {}
        for rel, info in self.files.items():
            fid = info.get("node") or rel
            if fid not in self.nodes:
                continue
            owner = self.sys_owner(fid)
            for nid in self._symbols_in(fid):
                if self.nodes[nid]["kind"] in CLASS_KINDS:
                    own.setdefault(owner, {}).setdefault(self.nodes[nid]["qual"], nid)
        sp = self.tr.get("sparent") or {}
        light = {"nodes": {i: ({**n, "parent": sp[i]} if i in sp else n) for i, n in self.nodes.items()
                           if n["tier"] == "sys"},
                 "diagrams": self.tr.get("diagrams", {})}
        for cid in sorted(light["diagrams"]):
            if cid not in self.nodes:
                continue
            r = T.resolve_diagram(light, cid, own.get(cid))
            if r is None:
                continue
            self.diagrams[cid] = r
            for mid, n in sorted(r["nodes"].items()):
                if n["ref"] is not None or n["id"] in self.nodes:
                    continue
                label = n.get("label") or mid
                head = mdparse.label_head(label) or mid
                first = label.split("\n", 1)[0]
                self.nodes[n["id"]] = {"id": n["id"], "parent": cid, "type": "actor", "tier": "sys",
                                       "kind": n.get("kind") or "actor", "name": head, "title": first,
                                       "summary": label.replace("\n", " · "), "path": cid,
                                       "mod": self.nodes[cid].get("mod"), "item": None, "ext": bool(n.get("ext")),
                                       "line": n.get("line"), "docs": []}
                self.children.setdefault(cid, []).append(n["id"])
                self.children.setdefault(n["id"], [])
            for e in r["edges"]:
                if e["s"] == e["t"] or e["s"] not in self.nodes or e["t"] not in self.nodes:
                    continue
                self.edges.append({"s": e["s"], "t": e["t"], "k": "flow", "conf": 1.0, "why": "mermaid", "diag": cid,
                                   "file": r["doc"], "line": e.get("line") or 0, "label": e.get("label") or "",
                                   "dash": bool(e.get("dash")), "prov": f"{r['doc']}:{e.get('line') or 0}"})

    def _symbols_in(self, nid: str):
        todo = list(self.children.get(nid, []))
        while todo:
            c = todo.pop()
            if self.nodes[c]["type"] == "symbol":
                yield c
                todo.extend(self.children.get(c, []))

    # --- resolution ---
    def resolve(self) -> Resolver:
        rnodes = {nid: {**n, **self.meta[nid]} for nid, n in self.nodes.items() if n["type"] == "symbol"}
        pyprojects = {}
        for rel in self.files:
            if rel.rsplit("/", 1)[-1] == "pyproject.toml":
                try:
                    pyprojects[rel] = (self.root / rel).read_text(encoding="utf-8", errors="replace")[:65536]
                except OSError:
                    pass
        res = Resolver(self.files, rnodes, self.loc, self.modules, set(self.files), pyprojects)
        edges = res.run()
        for e in edges:
            if e["s"] in self.nodes and e["t"] in self.nodes:
                self.edges.append(e)
        for mid, hits in res.impls.items():
            if mid in self.nodes:
                self.nodes[mid]["impls"] = list(hits)
        return res

    def make_deps(self) -> None:
        for name in sorted(self.modules):
            info = self.modules[name]
            sid = info.get("id")
            for dep in info.get("deps") or []:
                t = (self.modules.get(dep) or {}).get("id")
                if sid in self.nodes and t in self.nodes and t != sid:
                    self.edges.append({"s": sid, "t": t, "k": "dep", "conf": 1.0, "why": "deps",
                                       "file": info.get("overview") or "", "line": 0})

    def mark_x(self) -> None:
        if not self.modgate:
            return
        for e in self.edges:
            if e["k"] not in ("import", "call", "inherit") or e["conf"] < 0.8:
                continue
            a, b = self.nodes[e["s"]].get("mod"), self.nodes[e["t"]].get("mod")
            if not a or not b or a == b or a not in self.modules or b not in self.modules:
                continue
            ai, bi = self.modules[a], self.modules[b]
            if b in (ai.get("closure") or []) or b in (ai.get("deps") or []):
                continue
            ad, bd = ai.get("id") or ".", bi.get("id") or "."
            if _within(ad, bd) or _within(bd, ad):
                continue
            if self.nodes[e["t"]].get("vendor"):
                continue
            e["x"] = True

    # --- finish: buckets, sort, badges ---
    def finish(self) -> None:
        for cid in list(self.children):
            self.bucket_symbols(cid)
        for cid, kids in self.children.items():
            kids.sort(key=lambda c: (self.nodes[c]["tier"] != "sys", self.nodes[c]["name"].lower(), c))
        cov: dict[str, list[int]] = {}
        for nid, n in self.nodes.items():
            if n["type"] != "symbol":
                continue
            f = self.files.get(n["path"]) or {}
            if not n.get("pub") or not f.get("insrc") or f.get("test") or f.get("vendor") or n.get("test") \
                    or n.get("override") or n["kind"] in NO_COV_KINDS:
                continue
            doc = 1 if n.get("doc") else 0
            cur = nid
            while cur is not None:
                c = cov.setdefault(cur, [0, 0])
                c[0] += doc
                c[1] += 1
                cur = self.nodes[cur].get("parent")
        for rel, info in self.files.items():
            if info.get("lang") in (None, "text"):
                continue
            cur = info.get("node") or rel
            while cur is not None and cur in self.nodes and not self.nodes[cur].get("_code"):
                self.nodes[cur]["_code"] = True
                cur = self.nodes[cur].get("parent")
        for nid, n in self.nodes.items():
            n["_code"] = bool(n.get("_code"))
            n["children_n"] = len(self.children.get(nid, []))
            n.setdefault("impls", [])
            n["badges"] = {"crit": n.get("crit") if n["tier"] == "sys" else None, "status": n.get("status"),
                           "state": n.get("state"), "cov": cov.get(nid), "stale": 0, "findings": 0, "debt": 0,
                           "reqs": len(n.get("reqs") or []) if n["type"] in ("module", "root") else 0}

    def bucket_symbols(self, cid: str) -> None:
        kids = self.children.get(cid, [])
        syms = [k for k in kids if self.nodes[k]["type"] == "symbol"]
        if len(syms) <= SYM_BUCKET_OVER:
            return
        syms.sort(key=lambda k: (self.nodes[k]["name"].lower(), k))
        base = cid if "#" not in cid else cid.split("#", 1)[0]
        new = []
        for i in range(0, len(syms), SYM_BUCKET_SIZE):
            chunk = syms[i:i + SYM_BUCKET_SIZE]
            first, last = self.nodes[chunk[0]]["name"], self.nodes[chunk[-1]]["name"]
            bid = f"{base}#~{first}-{last}"
            while bid in self.nodes:
                bid += "~"
            self.nodes[bid] = {"id": bid, "parent": cid, "type": "bucket", "tier": "code", "kind": "bucket",
                               "name": f"{first}–{last}", "title": f"{first}–{last}", "path": base,
                               "mod": self.nodes[cid].get("mod"), "item": None}
            self.children[bid] = chunk
            for k in chunk:
                self.nodes[k]["parent"] = bid
            new.append(bid)
        self.children[cid] = [k for k in kids if self.nodes[k]["type"] != "symbol"] + new

    def compute_rev(self, tr: dict) -> str:
        lines = [f"{rel}\t{info['sha']}" for rel, info in self.files.items() if info.get("sha")]
        for rel in tr.get("read") or []:
            sha = self.cache.doc(self.root, rel)
            if sha:
                lines.append(f"{rel}\t{sha}")
        return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()[:12]


def _within(a: str, b: str) -> bool:
    return b in (".", "") or a == b or a.startswith(b + "/")


def _signature(root: Path, tr: dict) -> tuple:
    out = []
    for rel in sorted(set(tr["files"]) | set(tr.get("read") or [])):
        try:
            st = (root / rel).stat()
            out.append((rel, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((rel, 0, -1))
    return tuple(out)


def build_map(root: Path, data: Path, *, exact: bool = True, config: dict | None = None) -> "Map":
    """Build (incrementally, via `<data>/map/cache.json`) the map of `root`. Writes only under `<data>/map/`."""
    root = Path(root).resolve()
    if not exact:
        root = T.find_root(root)[0]
    cfg = json.loads(json.dumps(T.DEFAULT_CONFIG))
    cfg.update(config or {})
    m = _Build(root, Path(data), cfg, (root / T.CONFIG).is_file()).run()
    m.exact = exact
    return m


# ---------------------------------------------------------------- the model

class Map:
    """The built model plus per-request views (index, level, node, trace, search, text)."""

    root: Path
    data: Path
    modgate: bool
    project: str
    rev: str
    built: str

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.children: dict[str, list[str]] = {}
        self.edges: list[dict] = []
        self.files: dict[str, dict] = {}
        self.modules: dict[str, dict] = {}
        self.diagrams: dict[str, dict] = {}
        self.sparent: dict[str, str] = {}  # Systems-lens parent overrides (config `systems.areas`)
        self.areas: dict[str, dict] = {}
        self.stats: dict = {}
        self.findings: list = []
        self.config: dict = {}
        self.cache_stats: dict = {}
        self.exact = True
        self._sig: tuple = ()
        self._init()

    def _init(self) -> None:
        self._chains: dict[tuple, list[str]] = {}
        self._skids, self._sdrop = self._overlay()
        self._actors: dict | None = None
        self._gbase: set | None = None
        self._levels: dict[tuple, dict | None] = {}
        self._out: dict[str, list[dict]] | None = None
        self._in: dict[str, list[dict]] | None = None

    # ---------- hierarchy ----------
    def _overlay(self) -> tuple[dict[str, list[str]], set[str]]:
        """Systems-lens children of the containers the areas touch, and the containers they leave empty.

        A directory group or module whose module/group children all moved into areas (and that is no member
        itself) drops out of the Systems lens; its own code stays in the Code lens.
        """
        if not self.sparent and not self.areas:
            return {}, set()
        sk: dict[str, list[str]] = {}

        def kids(c: str) -> list[str]:
            if c not in sk:
                sk[c] = list(self.children.get(c, []))
            return sk[c]
        for a in self.areas:
            if a in self.nodes:
                kids(".").append(a)
                kids(a)
        for nid, a in sorted(self.sparent.items()):
            p = self.nodes[nid].get("parent")
            if p is not None and nid in kids(p):
                kids(p).remove(nid)
            kids(a).append(nid)
        isbox = lambda k: self.nodes[k]["type"] in ("module", "group")  # noqa: E731
        drop: set[str] = set()
        todo = [c for c in sk if c != "." and c not in self.areas]
        while todo:
            c = todo.pop()
            if c in drop or c in self.sparent or c == "." or c in self.areas:
                continue
            if any(isbox(k) for k in self.children.get(c, [])) and not any(isbox(k) for k in kids(c)):
                drop.add(c)
                p = self.nodes[c].get("parent")
                if p is not None and c in kids(p):
                    kids(p).remove(c)
                    todo.append(p)
        for c in sk:
            sk[c].sort(key=lambda k: (self.nodes[k]["tier"] != "sys", self.nodes[k]["name"].lower(), k))
        return sk, drop

    def _akey(self, nid: str) -> tuple:
        n = self.nodes.get(nid) or {}
        return (n.get("kind"), " ".join(str(n.get("name") or nid).lower().split()))

    def _actor_canon(self, key: tuple) -> str:
        """One id per actor name across all diagrams (the smallest), so a level shows one ghost per actor."""
        got = self._actors
        if got is None:
            got = self._actors = {}
            for nid in sorted(self.nodes):
                if self.nodes[nid].get("type") == "actor":
                    got.setdefault(self._akey(nid), nid)
        return got.get(key) or ""

    def _base_members(self, members: list[str], agg: dict) -> set[str]:
        """Members that are shared vocabulary (config `systems.base`, else: boxes only ever targeted by dashed
        "uses" flows, from three or more sources)."""
        cfg = (self.config.get("systems") or {}) if isinstance(self.config.get("systems"), dict) else {}
        boxes = [k for k in members if (self.nodes.get(k) or {}).get("type") in ("module", "group")]
        if "base" in cfg:
            names = {str(x) for x in cfg.get("base") or []}
            return {k for k in boxes if k in names or self.nodes[k]["name"] in names}
        out = set()
        for k in boxes:
            into = [(p, g) for p, g in agg.items() if p[1] == k and g["flows"]]
            if any(p[0] == k and g["flows"] for p, g in agg.items()):
                continue
            if len({p[0] for p, _ in into}) >= 3 and all(all(g["flows"]) for _, g in into):
                out.add(k)
        return out

    def _global_base(self) -> set[str]:
        """Base members seen from the root and from each area (where shared vocabulary is placed)."""
        if self._gbase is None:
            self._gbase = set()  # while it is computed, levels see no base ghosts (no recursion)
            got: set[str] = set()
            for at in (".", *sorted(self.areas)):
                lv = self.level("systems", at)
                got |= {n["id"] for n in (lv or {}).get("nodes", []) if n.get("base")}
            self._levels = {k: v for k, v in self._levels.items() if k[0] != "systems"}  # rebuilt with it
            self._gbase = got
        return self._gbase

    def _shown(self, e: dict, at: str, depth: int = 0) -> bool:
        """A drawn flow belongs to level `at` when `at`'s diagram drew it (the root: also the area diagrams),
        or it crosses `at`'s boundary and the level above shows it (continuity); never from a child diagram."""
        d = e.get("diag")
        if d is None or d == at:
            return True
        if at == ".":
            return d in self.areas
        if depth > 16:
            return False
        if (at in self.chain(e["s"], "systems")) == (at in self.chain(e["t"], "systems")):
            return False
        p = self.parent_of(at, "systems")
        return p is not None and self._shown(e, p, depth + 1)

    def parent_of(self, nid: str, lens: str = "systems") -> str | None:
        """Parent of a node in `lens`: areas re-parent their members in the Systems lens only."""
        if lens == "systems" and nid in self.sparent:
            return self.sparent[nid]
        n = self.nodes.get(nid)
        return n.get("parent") if n else None

    def kids(self, nid: str, lens: str = "systems") -> list[str]:
        if lens == "systems" and nid in self._skids:
            return self._skids[nid]
        if lens == "code" and nid in self.areas:
            return []  # an area exists in the Systems lens only
        return self.children.get(nid, [])

    def chain(self, nid: str, lens: str = "systems") -> list[str]:
        """Root-first ids from the root down to `nid` (inclusive) in `lens`. Unknown ids → [].

        In the Systems lens a node inside a container the areas left empty has no chain.
        """
        key = (nid, "code" if lens == "code" or not self.sparent else "systems")
        got = self._chains.get(key)
        if got is not None:
            return got
        lens = key[1]
        if is_own(nid):
            base = own_base(nid)
            out = self.chain(base, lens) + [nid] if base in self.nodes else []
            if base in self.nodes and not out[:-1]:
                out = []
        elif nid in self.nodes:
            if lens == "systems" and nid in self._sdrop:
                out = []
            else:
                p = self.parent_of(nid, lens)
                up = self.chain(p, lens) if p is not None else []
                out = up + [nid] if (p is None or up) else []
        else:
            out = []
        self._chains[key] = out
        return out

    def anc(self, id: str, lens: str = "systems") -> list[str]:
        """Ancestors of `id`, root first, excluding `id`."""
        return self.chain(id, lens)[:-1]

    def module_of(self, id: str) -> str | None:
        """Owning module NAME (plain mode: unit name); None for root-level code in plain mode."""
        if isinstance(id, str) and id.startswith("ghost:"):
            id = id[6:]
        if is_own(id):
            id = own_base(id)
        n = self.nodes.get(id)
        return n.get("mod") if n else None

    def _name(self, nid: str) -> str:
        if is_own(nid):
            return "(own code)"
        n = self.nodes.get(nid)
        return n["name"] if n else nid

    def _path(self, nid: str, lens: str = "systems") -> str:
        ch = self.chain(nid, lens) or self.chain(nid, "code")
        return " › ".join(self._name(i) for i in ch[1:]) or self._name(nid)

    def _crumbs(self, nid: str, lens: str = "systems") -> list[dict]:
        return [{"id": i, "name": self._name(i)} for i in (self.chain(nid, lens) or self.chain(nid, "code"))]

    # ---------- refresh ----------
    def refresh(self) -> bool:
        """Stat walk; rebuild changed files (cache-backed). True when the rev changed."""
        try:
            tr = T.load_tree(self.root, modgate=self.modgate, config=self.config)
            if _signature(self.root, tr) == self._sig:
                return False
        except Exception:
            pass
        old = self.rev
        new = build_map(self.root, self.data, exact=True, config=self.config)
        self.__dict__.update(new.__dict__)
        self._init()
        try:
            from . import fresh
            fresh.annotate(self)
        except Exception:
            pass
        return self.rev != old

    # ---------- drill / payload helpers ----------
    def _drill(self, nid: str) -> dict:
        if is_own(nid):
            base = own_base(nid)
            code = any(self.nodes[k]["tier"] == "code" for k in self.children.get(base, []))
            return {"systems": "code" if code else None, "code": "code" if code else None}
        kids = self.kids(nid, "systems")
        sys_ = any(self.nodes[k]["tier"] == "sys" for k in kids)
        code = any(self.nodes[k]["tier"] == "code" for k in kids)
        return {"systems": "systems" if sys_ else ("code" if code else None),
                "code": "code" if self.kids(nid, "code") else None}

    def _n(self, nid: str, lens: str) -> int:
        if is_own(nid):
            return sum(1 for k in self.children.get(own_base(nid), []) if self.nodes[k]["tier"] == "code")
        kids = self.kids(nid, lens)
        if lens == "systems":
            s = sum(1 for k in kids if self.nodes[k]["tier"] == "sys")
            if s:
                return s + (1 if any(self.nodes[k]["tier"] == "code" and self.nodes[k].get("_code")
                                     for k in kids) else 0)
        return len(kids)

    def _brief(self, n: dict) -> str:
        text = n.get("summary") or ((n.get("doc") or {}).get("brief") if isinstance(n.get("doc"), dict) else "") or ""
        text = " ".join(str(text).split())
        return text if len(text) <= 160 else text[:159] + "…"

    def _own_payload(self, oid: str, lens: str) -> dict:
        base = own_base(oid)
        bn = self.nodes[base]
        cov = [0, 0]
        for k in self.children.get(base, []):
            if self.nodes[k]["tier"] == "code":
                c = (self.nodes[k].get("badges") or {}).get("cov")
                if c:
                    cov[0] += c[0]
                    cov[1] += c[1]
        return {"id": oid, "type": "own", "tier": "sys", "kind": "own", "name": "(own code)",
                "title": f"{bn['name']}: own code", "brief": "Code that belongs to this container directly",
                "drill": self._drill(oid)[lens] if lens in LENSES else self._drill(oid), "n": self._n(oid, lens),
                "item": bn.get("item"), "src": None, "sig": None, "path": bn.get("path"), "parent": base,
                "badges": {"crit": None, "status": None, "state": None, "cov": cov if cov[1] else None,
                           "stale": 0, "findings": 0, "debt": 0, "reqs": 0}}

    def _payload(self, nid: str, lens: str) -> dict:
        if is_own(nid):
            return self._own_payload(nid, lens)
        n = self.nodes[nid]
        out = {"id": nid, "type": n["type"], "tier": n["tier"], "kind": n.get("kind"), "name": n["name"],
               "title": n.get("title") or n["name"], "brief": self._brief(n), "drill": self._drill(nid)[lens],
               "n": self._n(nid, lens), "item": n.get("item"), "src": n.get("src"), "sig": n.get("sig") or None,
               "path": n.get("path"), "lang": n.get("lang"), "badges": n.get("badges") or {}}
        for k in ("qual", "test", "pub", "ext", "vendor"):
            if n.get(k) is not None:
                out[k] = n[k]
        return out

    # ---------- /api/map ----------
    def index(self) -> dict:
        nodes = []
        for nid in sorted(self.nodes):
            if "#" in nid:
                continue
            n = self.nodes[nid]
            row = {"id": nid, "parent": n.get("parent"), "type": n["type"], "tier": n["tier"],
                   "kind": n.get("kind"), "name": n["name"], "title": n.get("title") or n["name"],
                   "path": n.get("path"), "lang": n.get("lang"), "n": len(self.children.get(nid, [])),
                   "drill": self._drill(nid), "item": n.get("item"), "badges": n.get("badges") or {}}
            if nid in self.sparent:
                row["sp"] = self.sparent[nid]  # the Systems-lens parent (an area)
            elif nid in self._sdrop:
                row["sp"] = None  # not shown in the Systems lens
            if nid in self.areas:
                row["n"] = len(self._skids.get(nid, []))
            nodes.append(row)
        rb = (self.nodes.get(".") or {}).get("badges") or {}
        counts = {"modules": len(self.modules),
                  "groups": sum(1 for n in self.nodes.values() if n["type"] == "group"),
                  "files": len(self.files), "symbols": self.stats.get("symbols", 0), "edges": len(self.edges),
                  "findings": len(self.findings or []), "debt": rb.get("debt", 0)}
        st = {k: self.stats.get(k) for k in ("resolved_hi", "unresolved", "truncated", "seconds")}
        return {"v": 1, "rev": self.rev, "repo": self.project, "modgate": self.modgate, "built": self.built,
                "root": ".", "nodes": nodes, "counts": counts, "stats": st}

    # ---------- levels ----------
    def _members(self, lens: str, at: str) -> list[str] | None:
        if is_own(at):
            base = own_base(at)
            if lens != "code" or base not in self.nodes:
                return None
            kids = [k for k in self.children.get(base, []) if self.nodes[k]["tier"] == "code"]
            return kids or None
        if at not in self.nodes or (lens == "systems" and at in self._sdrop):
            return None
        kids = self.kids(at, lens)
        if lens == "systems" and at == "." and self.areas:
            kids = [x for k in kids for x in (self.kids(k, "systems") if k in self.areas else [k])]
        if lens == "systems":
            sys_ = [k for k in kids if self.nodes[k]["tier"] == "sys"]
            if not sys_:
                return None
            if any(self.nodes[k]["tier"] == "code" and self.nodes[k].get("_code") for k in kids):
                sys_.append(own_id(at))
            return sys_
        return list(kids) or None

    def level(self, lens: str, at: str) -> dict | None:
        """Children of `at` in `lens` with lifted edges and ghosts (§2.5, §6.3); None → 404."""
        if lens not in LENSES or not isinstance(at, str):
            return None
        key = (lens, at)
        if key not in self._levels:
            self._levels[key] = self._level(lens, at)
        return self._levels[key]

    def _lift_fn(self, lens: str, at: str, members: list[str]):
        own_level = is_own(at)
        opened = set(self.areas) if lens == "systems" and at == "." else set()
        cc = self.chain(at, lens)
        mset = set(members)
        has_own = own_id(at) in mset
        if own_level:
            cb = cc[:-1]
            db = len(cb) - 1
            base = cb[-1]
        d = len(cc) - 1

        def ghost(ch: list[str]):
            lim = min(len(cc), len(ch) - 1)
            l = 0
            while l < len(ch) and l < len(cc) and ch[l] == cc[l]:
                l += 1
            if l >= len(ch):
                return None  # an ancestor of the level
            best = None
            for i in range(l, lim + 1):
                if self.nodes[ch[i]]["tier"] == "sys":
                    best = i
            if best is None:
                best = l
                if lens == "systems" and self.nodes[ch[l]]["tier"] == "code":
                    return ("g", own_id(ch[l - 1]))
            return ("g", ch[best])

        def mp(x: str):
            ch = self.chain(x, lens)
            if not ch:
                return None
            if own_level:
                if len(ch) > db and ch[db] == base:
                    if len(ch) == db + 1:
                        return ("self",)
                    c = ch[db + 1]
                    if self.nodes[c]["tier"] == "code":
                        return ("in", c)
                return ghost(ch)
            if len(ch) > d and ch[d] == at:
                if len(ch) == d + 1:
                    return ("self",)
                c = ch[d + 1]
                if c in opened:  # an open area box: the edge lands on its member, never on the box
                    if len(ch) == d + 2:
                        return None
                    c = ch[d + 2]
                if lens == "systems" and self.nodes[c]["tier"] == "code":
                    return ("in", own_id(at)) if has_own else None
                return ("in", c)
            return ghost(ch)
        return mp, has_own

    def _level(self, lens: str, at: str) -> dict | None:
        members = self._members(lens, at)
        if members is None:
            return None
        opened = set(self.areas) if lens == "systems" and at == "." else set()
        sys_lv = lens == "systems" and not is_own(at)
        same: dict[str, str] = {}
        mine: dict[tuple, str] = {}
        if sys_lv:  # one block per outside actor: every diagram draws its own copy of the same actor
            byname: dict[tuple, list[str]] = {}
            for k in members:
                if (self.nodes.get(k) or {}).get("type") == "actor":
                    byname.setdefault(self._akey(k), []).append(k)
            for key, ids in byname.items():
                keep = min(ids, key=lambda k: (k in self.sparent or self.parent_of(k) != at, k))
                mine[key] = keep
                for k in ids:
                    if k != keep:
                        same[k] = keep
                if opened and len({self.parent_of(k) for k in ids}) > 1:
                    same.setdefault("~loose:" + keep, keep)  # drawn by several areas: outside every box
            members = [k for k in members if k not in same]
        mp0, has_own = self._lift_fn(lens, at, members)

        def mp(x: str):
            r = mp0(x)
            if not r or r[0] not in ("in", "g"):
                return r
            if r[0] == "in" and r[1] in same:
                return ("in", same[r[1]])
            if sys_lv and r[0] == "g" and (self.nodes.get(r[1]) or {}).get("type") == "actor":
                key = self._akey(r[1])  # an outside copy of an actor: the one block (inside, or one ghost)
                return ("in", mine[key], "alias") if key in mine else ("g", self._actor_canon(key))
            return r
        agg: dict[tuple, dict] = {}
        sides: dict[str, set] = {}
        deferred: list[tuple] = []

        def add(a: str, b: str, e: dict) -> None:
            g = agg.get((a, b))
            if g is None:
                g = agg[(a, b)] = {"kinds": {}, "n": 0, "conf": 0.0, "hist": [0, 0, 0], "labels": [], "flows": [],
                                   "code": False, "prov": [], "samples": [], "x": False}
            k = e["k"]
            g["kinds"][k] = g["kinds"].get(k, 0) + 1
            g["n"] += 1
            g["conf"] = max(g["conf"], float(e.get("conf") or 0))
            if k in CODE_KINDS:
                c = float(e.get("conf") or 0)
                g["hist"][0 if c >= 0.8 else 1 if c >= 0.5 else 2] += 1
                g["code"] = True
                g["samples"].append(e)
            if k == "flow":
                g["flows"].append(bool(e.get("dash")))
                if e.get("label") and e["label"] not in g["labels"]:
                    g["labels"].append(e["label"])
                if e.get("prov") and e["prov"] not in g["prov"]:
                    g["prov"].append(e["prov"])
            if e.get("x"):
                g["x"] = True

        def key_of(r):
            return r[1] if r[0] == "in" else "ghost:" + r[1]

        lifted = []
        peers: set[str] = set()
        for e in self.edges:
            if sys_lv and e["k"] == "flow" and not self._shown(e, at):
                continue  # a level shows its own diagram (and what crosses its boundary from the level above)
            a, b = mp(e["s"]), mp(e["t"])
            if a is None or b is None:
                continue
            if a[0] == "g" and b[0] == "g":
                continue
            selfish = a[0] == "self" or b[0] == "self"
            if not selfish or (lens == "systems" and not is_own(at) and has_own):
                for r in (a, b):
                    if r[0] == "g":
                        peers.add(r[1])
            lifted.append((a, b, e))
        top: dict[str, str] = {}
        for p in peers:  # a ghost inside another ghost folds into the outer one
            outer = next((c for c in self.chain(own_base(p) if is_own(p) else p, lens)[:-1] if c in peers), None)
            top[p] = outer or (own_base(p) if is_own(p) and own_base(p) in peers else p)
        for a, b, e in lifted:
            if a[0] == "g":
                a = ("g", top.get(a[1], a[1]))
            if b[0] == "g":
                b = ("g", top.get(b[1], b[1]))
            if a[0] == "self" or b[0] == "self":
                if a[0] == "self" and b[0] == "self":
                    continue
                if lens == "systems" and not is_own(at):
                    if e["k"] in ("flow", "dep") and ("g" in (a[0], b[0]) or len(a) > 2 or len(b) > 2):
                        deferred.append((a, b, e))  # an edge across the boundary: on the child that handles it
                        continue
                    if not has_own:
                        continue
                    a = ("in", own_id(at)) if a[0] == "self" else a
                    b = ("in", own_id(at)) if b[0] == "self" else b
                else:
                    # only declared edges of `at` itself (deps/flows) are pinned onto the code pairs that
                    # observe them; a code edge ending at the container (a call of its class) is not a pair
                    if e["k"] in ("flow", "dep"):
                        deferred.append((a, b, e))
                    continue
            if a[0] == "g" and b[0] == "g":
                continue
            ka, kb = key_of(a), key_of(b)
            if ka == kb:
                continue
            if a[0] == "g":
                sides.setdefault(a[1], set()).add("in")
            if b[0] == "g":
                sides.setdefault(b[1], set()).add("out")
            add(ka, kb, e)
        sys_lv = lens == "systems" and not is_own(at)
        oid = own_id(at)

        def edge_kid(out: bool) -> str | None:
            """The member an unplaced boundary edge lands on: fewest inner edges on its outer side, then name."""
            boxes = [k for k in members if not is_own(k) and (self.nodes.get(k) or {}).get("type") in ("module", "group")]
            if not boxes:
                return None
            inner = [p for p in agg if not p[0].startswith("ghost:") and not p[1].startswith("ghost:")]
            deg = {k: sum(1 for p in inner if p[0 if out else 1] == k) for k in boxes}
            return min(boxes, key=lambda k: (deg[k], self.nodes[k]["name"].lower(), k))
        for a, b, e in deferred:  # container-own edges (deps/flows of `at` itself) go to the code that observes them
            out = a[0] == "self"
            other = key_of(b) if out else key_of(a)
            mine = (lambda q: not q.startswith("ghost:") and q != oid) if sys_lv else (lambda q: not q.startswith("ghost:"))
            pairs = [p for p, g in agg.items() if p[1 if out else 0] == other and mine(p[0 if out else 1])
                     and (g["code"] or (sys_lv and "flow" in g["kinds"]))]
            if not pairs and sys_lv and has_own:
                pairs = [(oid, other) if out else (other, oid)]  # nothing inside handles it: the own code does
            if not pairs and sys_lv:
                kid = edge_kid(out)  # nor any own code: the child where the inner flow starts (or ends)
                if kid:
                    pairs = [(kid, other) if out else (other, kid)]
            if sys_lv and pairs and other.startswith("ghost:"):
                sides.setdefault(other[6:], set()).add("out" if out else "in")
            for p in pairs:
                add(p[0], p[1], e)
        base = self._base_members(members, agg) if sys_lv else set()
        if sys_lv:
            gb = self._global_base()
            base |= {k for p in agg for k in p if k.startswith("ghost:") and k[6:] in gb}
        edges = []
        for (a, b), g in sorted(agg.items()):
            declared = "flow" in g["kinds"] or "dep" in g["kinds"]
            observed = any(float(s.get("conf") or 0) >= 0.8 for s in g["samples"])
            if declared and observed:
                state = "both"
            elif declared:
                state = "declared"
            elif g["x"]:
                state = "undeclared"
            else:
                state = "observed"
            samples = sorted(g["samples"], key=lambda s: (-float(s.get("conf") or 0), s.get("file") or "",
                                                          s.get("line") or 0, s["s"], s["t"]))[:5]
            edges.append({"id": f"{a}>{b}", "s": a, "t": b,
                          "kinds": {k: g["kinds"][k] for k in KIND_ORDER if k in g["kinds"]},
                          "n": g["n"], "conf": round(g["conf"], 3), "hist": g["hist"], "labels": g["labels"],
                          "dash": bool(g["flows"]) and all(g["flows"]) and not g["code"], "state": state,
                          "x": g["x"], "prov": g["prov"][:5], **({"base": True} if a in base or b in base else {}),
                          "samples": [{"s": s["s"], "t": s["t"], "k": s["k"], "file": s.get("file"),
                                       "line": s.get("line"), "conf": s.get("conf"), "why": s.get("why")}
                                      for s in samples]})
        ghosts = []
        for peer in sorted(sides):
            sd = sides[peer]
            ghosts.append({"id": "ghost:" + peer, "peer": peer, "name": self._name(peer),
                           "path": self._path(peer, lens), "side": "both" if len(sd) > 1 else next(iter(sd)),
                           "at": own_base(peer) if is_own(peer) else self.parent_of(peer, lens)})
        nodes = [self._payload(i, lens) for i in members]
        for p in nodes:
            if p["id"] in base:
                p["base"] = True  # shared vocabulary: drawn as a strip under its box, its edges on demand
        out = {"v": 1, "rev": self.rev, "lens": lens, "at": at, "crumbs": self._crumbs(at, lens),
               "nodes": nodes, "ghosts": ghosts, "edges": edges, "overflow": len(members) > T.BUCKET_OVER}
        if opened:  # the root of the Systems lens: each area is an open box around its members
            for p in nodes:
                a = self.sparent.get(p["id"]) or self.parent_of(p["id"])
                if a in opened and "~loose:" + p["id"] not in same:
                    p["area"] = a
            tag = {p["id"]: p.get("area") for p in nodes}
            for p in nodes:  # an outside actor that only talks to one area sits in that area's box
                if p.get("area") or p["type"] != "actor":
                    continue
                near = {tag.get(e["t"] if e["s"] == p["id"] else e["s"]) for e in edges
                        if p["id"] in (e["s"], e["t"]) and "flow" in e["kinds"]}
                if len(near) == 1 and None not in near:
                    p["area"] = near.pop()
            out["areas"] = [{"id": a, "name": self.nodes[a]["name"], "title": self.nodes[a].get("title") or a,
                             "brief": self._brief(self.nodes[a]), "item": self.nodes[a].get("item"),
                             "members": [p["id"] for p in nodes if p.get("area") == a]}
                            for a in self.kids(".", "systems") if a in opened]
        return out

    # ---------- /api/map/node ----------
    def _adj(self):
        if self._out is None:
            out: dict[str, list[dict]] = {}
            inn: dict[str, list[dict]] = {}
            for e in self.edges:
                out.setdefault(e["s"], []).append(e)
                inn.setdefault(e["t"], []).append(e)
            self._out, self._in = out, inn
        return self._out, self._in

    def _file_reqs(self) -> dict[str, set]:
        got = getattr(self, "_freqs", None)
        if got is None:
            got = {}
            for info in self.modules.values():
                for req, paths in (info.get("bind") or {}).items():
                    for p in paths:
                        got.setdefault(p, set()).add(req)
            self._freqs = got
        return got

    def _req_index(self) -> dict[str, dict]:
        got = getattr(self, "_reqidx", None)
        if got is None:
            got = {}
            for info in self.modules.values():
                item = next((d["item"] for d in info.get("docs") or [] if d.get("role") == "req"), None)
                for rid, r in (info.get("reqs") or {}).items():
                    got.setdefault(rid, {"id": rid, "item": item, "title": (r or {}).get("title") or ""})
            self._reqidx = got
        return got

    def _node_reqs(self, nid: str) -> list[str]:
        n = self.nodes[nid]
        out = set(n.get("reqs") or [])
        if n["type"] in ("file", "symbol"):
            out |= self._file_reqs().get(n.get("path") or nid, set())
        return sorted(out)

    def node(self, id: str) -> dict | None:
        if is_own(id):
            if own_base(id) not in self.nodes:
                return None
            n = self._own_payload(id, "code")
        elif id in self.nodes:
            n = {k: self.nodes[id].get(k) for k in NODE_FIELDS}
        else:
            return None
        nid = id
        out_e, in_e = self._adj()
        base = own_base(id) if is_own(id) else id
        node = self.nodes[base]

        def row(other: str, e: dict) -> dict:
            return {"id": other, "name": self._name(other), "path": self._path(other), "conf": e.get("conf"),
                    "why": e.get("why"), "file": e.get("file"), "line": e.get("line")}

        callers = sorted((row(e["s"], e) for e in in_e.get(nid, []) if e["k"] == "call"),
                         key=lambda r: (-(r["conf"] or 0), r["id"]))[:50]
        callees = sorted((row(e["t"], e) for e in out_e.get(nid, []) if e["k"] == "call"),
                         key=lambda r: (-(r["conf"] or 0), r["id"]))[:50]
        impls = [{"id": i, "name": self._name(i), "path": self._path(i)} for i in (node.get("impls") or [])
                 if i in self.nodes] if not is_own(id) else []
        implements = []
        if not is_own(id):
            for oid, o in self.nodes.items():
                if nid in (o.get("impls") or []):
                    implements.append({"id": oid, "name": o["name"], "path": self._path(oid)})
            for e in out_e.get(nid, []):
                if e["k"] == "inherit":
                    implements.append({"id": e["t"], "name": self._name(e["t"]), "path": self._path(e["t"])})
        if node["type"] in ("file", "symbol", "dir", "bucket"):
            mod = self.modules.get(node.get("mod") or "")
            docs = list((mod or {}).get("docs") or [])
        else:
            docs = list(node.get("docs") or [])
        rids = self._node_reqs(base) if not is_own(id) else []
        idx = self._req_index()
        reqs = [idx.get(r) or {"id": r, "item": None, "title": ""} for r in rids]
        tests = []
        rset = set(rids)
        callers_ids = {e["s"] for e in in_e.get(nid, []) if e["k"] == "call"}
        for tid, t in self.nodes.items():
            if t["type"] != "symbol" or not t.get("test"):
                continue
            if tid in callers_ids or (rset and rset & set(t.get("reqs") or [])):
                tests.append({"id": tid, "name": t["name"], "src": t.get("src")})
        tests.sort(key=lambda x: x["id"])
        findings = []
        for f in self.findings or []:
            fn = getattr(f, "node", None)
            if fn == nid or (fn and n.get("type") != "symbol" and (nid in self.chain(fn) or nid in self.chain(fn, "code"))):
                try:
                    findings.append(f.line())
                except Exception:
                    continue
            if len(findings) >= 50:
                break
        return {"node": n, "chain": self._crumbs(nid)[:-1], "docs": docs, "callers": callers, "callees": callees,
                "impls": impls, "implements": implements, "reqs": reqs, "tests": tests, "findings": findings}

    # ---------- /api/map/trace ----------
    def trace(self, id: str, dir: str = "both", depth: int = 2) -> dict | None:
        if id not in self.nodes or dir not in ("in", "out", "both"):
            return None
        depth = max(1, min(4, int(depth)))
        out_e, in_e = self._adj()
        seen = {id}
        edges: dict[tuple, dict] = {}
        ways = ("out", "in") if dir == "both" else (dir,)
        for way in ways:
            frontier = [id]
            reached = {id}  # per direction: the out pass must not stop the in pass from expanding a node
            for _ in range(depth):
                nxt = []
                for x in frontier:
                    for e in (out_e if way == "out" else in_e).get(x, []):
                        if e["k"] not in ("call", "inherit") or float(e.get("conf") or 0) < 0.5:
                            continue
                        edges.setdefault((e["s"], e["t"], e["k"]), {"s": e["s"], "t": e["t"], "k": e["k"],
                                                                    "conf": e.get("conf")})
                        y = e["t"] if way == "out" else e["s"]
                        if y not in reached:
                            reached.add(y)
                            seen.add(y)
                            nxt.append(y)
                    if len(edges) > 2000:
                        break
                frontier = nxt
        return {"root": id, "nodes": {n: self.anc(n) for n in sorted(seen)},
                "edges": [edges[k] for k in sorted(edges)]}

    # ---------- /api/map/search ----------
    def search(self, q: str, limit: int = 30) -> list[dict]:
        ql = (q or "").strip().lower()
        if not ql:
            return []
        hits = []
        for nid, n in self.nodes.items():
            if n["type"] == "bucket":
                continue
            name = str(n.get("name") or "").lower()
            if name == ql:
                r = 0
            elif name.startswith(ql):
                r = 1
            elif ql in name:
                r = 2
            elif n.get("qual") and ql in n["qual"].lower():
                r = 3
            elif ql in self._brief(n).lower():
                r = 4
            else:
                continue
            path = self._path(nid)
            hits.append(((r, TYPE_RANK.get(n["type"], 1), len(path), nid), nid, path))
        hits.sort()
        out = []
        for _, nid, path in hits[:max(1, min(100, int(limit)))]:
            n = self.nodes[nid]
            lens = "systems" if n["tier"] == "sys" else "code"
            at = self.parent_of(nid, lens) or "."
            out.append({"id": nid, "name": n["name"], "type": n["type"], "kind": n.get("kind"), "path": path,
                        "at": at, "lens": lens})
        return out

    # ---------- /api/source ----------
    def source_path(self, rel: str) -> Path | None:
        """The real path of an indexed file: inside the root, not a link out, ≤ 1 MB, not binary; else None."""
        if not isinstance(rel, str) or rel not in self.files:
            return None
        info = self.files[rel]
        rec = info.get("rec") or {}
        if rec.get("skip") == "binary":
            return None
        root = Path(self.root).resolve()
        try:
            p = (root / rel).resolve()
            if not p.is_relative_to(root) or not p.is_file() or p.stat().st_size > MAX_SOURCE:
                return None
            prel = p.relative_to(root).as_posix()
            if prel != rel and prel not in self.files:
                return None  # a link to a file the walk skips (`.env`, `.git/config`) is never served
            with p.open("rb") as f:
                if b"\x00" in f.read(8192):
                    return None
        except (OSError, ValueError):
            return None
        return p

    # ---------- text for LLMs ----------
    def _node_line(self, p: dict, width: int, ind: str) -> str:
        b = p.get("badges") or {}
        parts = [f"{ind}{p['name']:<{width}}", f"{p['type']}/{p.get('kind')}"]
        for k in ("crit", "status", "state"):
            if b.get(k):
                parts.append(str(b[k]))
        if p.get("drill"):
            parts.append(f"▸{p['n']}")
        if b.get("cov"):
            parts.append(f"cov {b['cov'][0]}/{b['cov'][1]}")
        if b.get("findings"):
            parts.append(f"findings {b['findings']}")
        if b.get("debt"):
            parts.append(f"debt {b['debt']}")
        return "  ".join(parts)

    def _show_nodes(self, lens: str, at: str, depth: int, ind: str, out: list[str]) -> None:
        lv = self.level(lens, at)
        if not lv:
            return
        width = max((len(p["name"]) for p in lv["nodes"]), default=0)
        groups = [(None, [p for p in lv["nodes"] if not p.get("area")])]
        groups += [(a, [p for p in lv["nodes"] if p.get("area") == a["id"]]) for a in lv.get("areas") or []]
        for a, ps in groups:
            sub = ind
            if a is not None:
                out.append(f"{ind}[{a['title']}]  area/{a['id']}")
                sub = ind + "  "
            for p in ps:
                out.append(self._node_line(p, width, sub))
                if depth > 1 and p.get("drill") == lens:
                    self._show_nodes(lens, p["id"], depth - 1, sub + "  ", out)

    def show_text(self, lens: str, at: str, depth: int = 1) -> str:
        lv = self.level(lens, at)
        if lv is None:
            return ""
        head = self._own_payload(at, lens) if is_own(at) else self.nodes[at]
        out = [f"{head['name']}  {head.get('kind')}  [{lens}]  at {at}"]
        self._show_nodes(lens, at, max(1, min(3, int(depth))), "  ", out)
        names = {p["id"]: p["name"] for p in lv["nodes"]}
        names.update({g["id"]: g["path"] for g in lv["ghosts"]})
        out.append("edges:")
        rows = []
        for e in lv["edges"]:
            kinds = " ".join(k if (k in ("flow", "dep") and n == 1) else f"{k}×{n}" for k, n in e["kinds"].items())
            rows.append((f"{names.get(e['s'], e['s'])} → {names.get(e['t'], e['t'])}", kinds,
                         list(e["labels"]), e["state"]))
        w = max((len(r[0]) for r in rows), default=0)
        for pair, kinds, labels, state in rows:
            head = f'"{labels[0]}"' + (f" +{len(labels) - 1} more" if len(labels) > 1 else "") if labels else ""
            out.append("  " + "  ".join([f"{pair:<{w}}", kinds] + ([head] if head else []) + [state]))
            if len(labels) > 1:  # several labels lifted onto one edge: one per line
                out.extend(f"      · {lb}" for lb in labels)
        if not rows:
            out.append("  (none)")
        out.append("ghosts:")
        for g in lv["ghosts"]:
            out.append(f"  {g['name']}  {g['path']}  {g['side']}")
        if not lv["ghosts"]:
            out.append("  (none)")
        return "\n".join(out) + "\n"

    def trace_text(self, id: str, dir: str = "both", depth: int = 2) -> str:
        tr = self.trace(id, dir, depth)
        if tr is None:
            return ""
        hops: dict[tuple, dict] = {}
        for e in tr["edges"]:
            cs, ct = self.chain(e["s"]), self.chain(e["t"])
            l = 0
            while l < len(cs) and l < len(ct) and cs[l] == ct[l]:
                l += 1
            lca = cs[l - 1] if l else "."
            a = cs[l] if l < len(cs) else e["s"]
            b = ct[l] if l < len(ct) else e["t"]
            h = hops.setdefault((lca, a, b), {"kinds": {}, "conf": 0.0})
            h["kinds"][e["k"]] = h["kinds"].get(e["k"], 0) + 1
            h["conf"] = max(h["conf"], float(e.get("conf") or 0))
        n = self.nodes[id]
        out = [f"trace {n.get('qual') or n['name']}  [{dir}, depth {max(1, min(4, int(depth)))}]  {len(tr['edges'])} edges"]
        for (lca, a, b), h in sorted(hops.items(), key=lambda kv: (len(self.chain(kv[0][0])), self._path(kv[0][0]),
                                                                    self._name(kv[0][1]), self._name(kv[0][2]))):
            crumb = " › ".join(self._name(i) for i in self.chain(lca))
            kinds = ", ".join(f"{k} ×{c}" for k, c in sorted(h["kinds"].items()))
            out.append(f"  {crumb}: {self._name(a)} → {self._name(b)} ({kinds}, conf {h['conf']:.2f})")
        if not hops:
            out.append("  (no edges)")
        return "\n".join(out) + "\n"

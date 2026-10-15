"""Cross-file resolution for the wiki map (spec §5): calls, imports, includes, inheritance, contracts.

Input is the extractor output of every file plus the symbol nodes built by `graph.py`; output is a list of
base edges (`call import inherit contract data`), the `impls` lists of overridable methods, and counters.
Every rule is name based and conservative: first rule that matches wins, its `conf` and `why` are recorded,
and a call with more than five candidates is dropped. Repo text is data; nothing is executed. Stdlib only.
"""
from __future__ import annotations

import posixpath
import re

__all__ = ["Resolver", "family", "CLASS_KINDS"]

CLASS_KINDS = frozenset({"class", "struct", "interface"})
CALL_KINDS = frozenset({"function", "ctor", "class", "struct", "macro"})
METHOD_KINDS = frozenset({"method", "ctor", "function"})
MAX_AMBIG = 5
JS_PROBES = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", "/index.ts", "/index.js")
SELF_RECV = ("self", "this", "cls")
_PYPATH = re.compile(r"^\s*pythonpath\s*=\s*(\[[^\]]*\]|\"[^\"]*\"|'[^']*')", re.M)
_SMART = re.compile(r"^(?:std::)?(?:unique_ptr|shared_ptr|weak_ptr|optional|reference_wrapper|Optional|Promise)\s*[<\[](.+)[>\]]$")
_TYPE_NOISE = re.compile(r"\b(?:const|volatile|struct|class|typename|mutable|readonly)\b|[&*]")


def family(lang: str | None) -> str:
    if lang in ("c", "cpp"):
        return "c"
    if lang == "python":
        return "py"
    if lang in ("js", "ts"):
        return "js"
    return "other"


def _last(name: str) -> str:
    return re.split(r"::|\.", name)[-1] if name else name


def _norm_field(s: str) -> str:
    return s.lower().replace("_", "")


class Resolver:
    """One resolution pass over a built symbol table.

    files:   rel -> {"mod","lang","rec","vendor"}   (rec = extract() result or None)
    nodes:   every map node (symbol nodes carry qual/name/kind/parent_q/members/bases/...)
    loc:     (rel, qual) -> [(line, end, node id)] for every extracted symbol (merged declarations included)
    modules: tree modules (name -> {"id","deps","closure",...})
    """

    def __init__(self, files: dict, nodes: dict, loc: dict, modules: dict, file_ids: set[str],
                 pyprojects: dict[str, str] | None = None):
        self.files, self.nodes, self.loc, self.modules = files, nodes, loc, modules
        self.pyprojects = pyprojects or {}
        self.all_files = file_ids
        self.edges: dict[tuple, dict] = {}
        self.unresolved = 0
        self.resolved = 0
        self.impls: dict[str, list[str]] = {}
        self.syms_by_file: dict[str, list[str]] = {}
        self.by_name: dict[tuple, list[str]] = {}       # (family, name) -> ids  (callable kinds)
        self.classes_by_qual: dict[str, list[str]] = {}
        self.class_by_name: dict[tuple, list[str]] = {}  # (family, short name) -> class ids
        self.methods: dict[str, dict[str, list[str]]] = {}  # class id -> name -> method ids
        self.method_owner: dict[str, str] = {}
        self.bases: dict[str, list[str]] = {}
        self.methods_by_name: dict[tuple, list[str]] = {}  # (family, name) -> method ids
        self.includes: dict[str, list[str]] = {}
        self.bindings: dict[str, dict[str, tuple]] = {}
        self.usings: dict[str, list[str]] = {}
        self._closure: dict[str, set[str]] = {}
        self._index_symbols()

    # ---------- tables ----------
    def _fam_of(self, rel: str) -> str:
        return family((self.files.get(rel) or {}).get("lang"))

    def _mod(self, rel: str) -> str | None:
        return (self.files.get(rel) or {}).get("mod")

    def _index_symbols(self) -> None:
        for nid in sorted(self.nodes):
            n = self.nodes[nid]
            if n.get("type") != "symbol":
                continue
            rel = n["path"]
            self.syms_by_file.setdefault(rel, []).append(nid)
            fam = family(n.get("lang"))
            kind = n.get("kind")
            if kind in CALL_KINDS or kind in CLASS_KINDS:
                self.by_name.setdefault((fam, n["name_short"]), []).append(nid)
            if kind in CLASS_KINDS:
                self.classes_by_qual.setdefault(n["qual"], []).append(nid)
                self.class_by_name.setdefault((fam, n["name_short"]), []).append(nid)
        for nid in sorted(self.nodes):
            n = self.nodes[nid]
            if n.get("type") != "symbol" or n.get("kind") not in METHOD_KINDS or not n.get("parent_q"):
                continue
            ctx = (n.get("decl") or [n["path"]])[0]
            cls = self.lookup_class(n["parent_q"], ctx, family(n.get("lang")))
            if cls is None:
                continue
            self.methods.setdefault(cls, {}).setdefault(n["name_short"], []).append(nid)
            self.method_owner[nid] = cls
            self.methods_by_name.setdefault((family(n.get("lang")), n["name_short"]), []).append(nid)

    def lookup_class(self, qual: str, ctx: str, fam: str) -> str | None:
        cands = [c for c in self.classes_by_qual.get(qual, []) if family(self.nodes[c].get("lang")) == fam]
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        same = [c for c in cands if self.nodes[c]["path"] == ctx]
        if same:
            return same[0]
        mod = self._mod(ctx)
        same = [c for c in cands if self.nodes[c].get("mod") == mod]
        if same:
            return same[0]
        clo = self.include_closure(ctx)
        same = [c for c in cands if self.nodes[c]["path"] in clo]
        return (same or cands)[0]

    # ---------- edges ----------
    def add(self, s: str, t: str, k: str, conf: float, why: str, rel: str, line) -> None:
        if not s or not t or s == t:
            return
        key = (s, t, k)
        conf = round(conf, 3)
        e = self.edges.get(key)
        if e is None:
            self.edges[key] = {"s": s, "t": t, "k": k, "conf": conf, "why": why, "file": rel,
                               "line": int(line or 0), "w": 1}
            return
        e["w"] += 1
        if conf > e["conf"]:
            e["conf"], e["why"] = conf, why
        if (rel, int(line or 0)) < (e["file"], e["line"]):
            e["file"], e["line"] = rel, int(line or 0)

    # ---------- C/C++ includes ----------
    def _mod_dirs(self, mod: str | None) -> list[str]:
        out = []
        names = [mod] if mod else []
        if mod and mod in self.modules:
            names += list(self.modules[mod].get("closure") or [])
        for name in names:
            info = self.modules.get(name)
            if not info:
                continue
            mid = info.get("id") or "."
            for sub in ("include", "fakes"):
                out.append(sub if mid == "." else f"{mid}/{sub}")
        return out

    def resolve_include(self, rel: str, target: str, system: bool) -> tuple[str | None, float, str]:
        target = target.strip()
        if not target:
            return None, 0, ""
        if not system:
            p = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
            if p in self.all_files:
                return p, 0.8, "include"
        for d in self._mod_dirs(self._mod(rel)):
            p = posixpath.normpath(f"{d}/{target}")
            if p in self.all_files:
                return p, 0.8, "include"
        suf = "/" + target
        hits = sorted(f for f in self.all_files if (f.endswith(suf) or f == target) and self._fam_of(f) == "c")
        if len(hits) > 1:
            mod = self._mod(rel)
            same = [h for h in hits if self._mod(h) == mod]
            hits = same if len(same) == 1 else hits
        if len(hits) == 1:
            return hits[0], 0.6, "basename"
        return None, 0, ""

    def include_closure(self, rel: str) -> set[str]:
        got = self._closure.get(rel)
        if got is not None:
            return got
        one = set(self.includes.get(rel, []))
        two = set(one)
        for r in one:
            two.update(self.includes.get(r, []))
        two.discard(rel)
        self._closure[rel] = two
        return two

    # ---------- Python modules ----------
    def _py_index(self) -> None:
        pyfiles = sorted(r for r, f in self.files.items() if f.get("lang") == "python" and not f.get("vendor"))
        inits = {posixpath.dirname(r) for r in pyfiles if r.rsplit("/", 1)[-1] == "__init__.py"}
        roots_extra: set[str] = set()
        for r, text in sorted(self.pyprojects.items()):
            if text:
                m = _PYPATH.search(text)
                if m:
                    base = posixpath.dirname(r)
                    for p in re.findall(r"[\"']([^\"']+)[\"']", m.group(1)):
                        roots_extra.add(posixpath.normpath(posixpath.join(base, p)) if base else posixpath.normpath(p))
        self.py_full: dict[str, list[str]] = {}
        self.py_suffix: dict[str, list[str]] = {}
        self.py_pkgdir: dict[str, str] = {}
        for r in pyfiles:
            d = posixpath.dirname(r)
            top = d
            while top and top in inits:
                top = posixpath.dirname(top)
            roots = {top}
            parts = d.split("/") if d else []
            for i in range(len(parts)):
                anc = "/".join(parts[:i + 1])
                if parts[i] == "src" or anc in roots_extra:
                    roots.add(anc)
            roots.add(d)
            names = set()
            for root in roots:
                if root and not (d == root or d.startswith(root + "/")):
                    continue
                sub = r[len(root) + 1:] if root else r
                dotted = sub[:-3].replace("/", ".")
                if dotted.endswith(".__init__"):
                    dotted = dotted[: -len(".__init__")]
                elif dotted == "__init__":
                    continue
                if dotted:
                    names.add(dotted)
            for dotted in sorted(names):
                self.py_full.setdefault(dotted, []).append(r)
                segs = dotted.split(".")
                for i in range(len(segs)):
                    self.py_suffix.setdefault(".".join(segs[i:]), []).append(r)

    def py_module(self, rel: str, target: str, level: int) -> str | None:
        if level:
            base = posixpath.dirname(rel)
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            if not target:
                p = f"{base}/__init__.py" if base else "__init__.py"
                return p if p in self.all_files else None
            path = posixpath.join(base, target.replace(".", "/")) if base else target.replace(".", "/")
            for p in (path + ".py", path + "/__init__.py"):
                if p in self.all_files:
                    return p
            return None
        if not target:
            return None
        cands = list(dict.fromkeys(self.py_full.get(target, [])))
        if not cands:
            cands = list(dict.fromkeys(self.py_suffix.get(target, [])))
            if "." not in target:
                cands = [c for c in cands if self._mod(c) == self._mod(rel)]
        cands = [c for c in cands if c != rel] or cands
        if not cands:
            return None
        mod = self._mod(rel)
        cands.sort(key=lambda c: (self._mod(c) != mod, len(c), c))
        return cands[0]

    # ---------- JS modules ----------
    def js_module(self, rel: str, spec: str) -> str | None:
        if not spec.startswith("."):
            return None
        base = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
        if base.startswith(".."):
            return None
        probes = [base + p for p in JS_PROBES]
        stem, ext = posixpath.splitext(base)
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            probes += [stem + ".ts", stem + ".tsx"]
        for p in probes:
            if p in self.all_files:
                return p
        return None

    # ---------- imports pass ----------
    def run_imports(self) -> None:
        self._py_index()
        for rel in sorted(self.files):
            f = self.files[rel]
            rec = f.get("rec")
            if not rec or f.get("vendor"):
                continue
            lang = rec.get("lang") or f.get("lang")
            fam = family(lang)
            binds: dict[str, tuple] = {}
            for imp in rec.get("imports") or []:
                kind, target, line = imp.get("kind"), imp.get("target") or "", imp.get("line")
                if fam == "c":
                    if kind == "using":
                        self.usings.setdefault(rel, []).append(target)
                        continue
                    t, conf, why = self.resolve_include(rel, target, bool(imp.get("system")))
                    if t:
                        self.includes.setdefault(rel, []).append(t)
                        self.add(rel, t, "import", conf, why, rel, line)
                elif fam == "py":
                    self._py_import(rel, imp, binds)
                elif fam == "js":
                    self._js_import(rel, imp, binds)
            self.bindings[rel] = binds

    def _py_import(self, rel: str, imp: dict, binds: dict) -> None:
        target, level, line = imp.get("target") or "", int(imp.get("level") or 0), imp.get("line")
        names, alias = imp.get("names") or [], imp.get("alias")
        if imp.get("kind") == "import":
            mod = self.py_module(rel, target, 0)
            if mod:
                self.add(rel, mod, "import", 0.8, "import", rel, line)
                if alias:
                    binds[alias] = ("mod", mod)
                else:
                    head = target.split(".")[0]
                    hm = self.py_module(rel, head, 0)
                    binds.setdefault(head, ("mod", hm) if hm else ("ext",))
                    binds[target] = ("mod", mod)
            else:
                binds[alias or target.split(".")[0]] = ("ext",)
            return
        mod = self.py_module(rel, target, level)
        for name in names:
            local = alias if alias and len(names) == 1 else name
            if name == "*":
                continue
            sub = None
            base = mod
            if level and not target:
                base = None
                pkg = posixpath.dirname(rel)
                for _ in range(level - 1):
                    pkg = posixpath.dirname(pkg)
                sub = self.py_module(rel, name, level)
                if sub is None:
                    base = (f"{pkg}/__init__.py" if pkg else "__init__.py")
                    base = base if base in self.all_files else None
            elif mod and mod.endswith("/__init__.py"):
                cand = posixpath.dirname(mod) + "/" + name
                sub = next((p for p in (cand + ".py", cand + "/__init__.py") if p in self.all_files), None)
            if sub:
                binds[local] = ("mod", sub)
                self.add(rel, sub, "import", 0.8, "import", rel, line)
            elif base:
                binds[local] = ("sym", base, name)
                self.add(rel, base, "import", 0.8, "import", rel, line)
            else:
                binds[local] = ("ext",)

    def _js_import(self, rel: str, imp: dict, binds: dict) -> None:
        target, line = imp.get("target") or "", imp.get("line")
        mod = self.js_module(rel, target)
        if mod:
            self.add(rel, mod, "import", 0.8, "import", rel, line)
        if not imp.get("names") and imp.get("alias"):
            # `const cj = require("./cj")`, TS `import cj = require("./cj")`: the alias is the module
            binds[imp["alias"]] = ("mod", mod) if mod else ("ext",)
        for name in imp.get("names") or []:
            if imp.get("kind") == "reexport":
                local = imp.get("alias") or name
                if name == "*":
                    if mod:
                        binds.setdefault("*", ())
                        binds["*"] = tuple(binds["*"]) + (mod,)
                    continue
                binds.setdefault("export:" + local, ("sym", mod, name) if mod else ("ext",))
                continue
            local = imp.get("alias") or name
            if not mod:
                binds[local] = ("ext",)
            elif name == "*":
                binds[local] = ("mod", mod)
            elif name == "default":
                binds[local] = ("default", mod, local)
            else:
                binds[local] = ("sym", mod, name)

    # ---------- symbol lookup through modules ----------
    def top_symbol(self, rel: str, name: str, depth: int = 0) -> str | None:
        """Top-level symbol `name` of module file `rel`, following re-exports (≤ 3 hops)."""
        for nid in self.syms_by_file.get(rel, []):
            n = self.nodes[nid]
            if n["qual"] == name:
                return nid
        if depth >= 3:
            return None
        binds = self.bindings.get(rel, {})
        b = binds.get(name) or binds.get("export:" + name)
        if b:
            got = self._follow(b, depth + 1)
            if got:
                return got
        for star in binds.get("*", ()):
            got = self.top_symbol(star, name, depth + 1)
            if got:
                return got
        return None

    def _follow(self, b: tuple, depth: int = 0) -> str | None:
        if not b or b[0] == "ext":
            return None
        if b[0] == "mod":
            return b[1]
        if b[0] == "sym":
            return self.top_symbol(b[1], b[2], depth) if b[1] else None
        if b[0] == "default":
            rel, local = b[1], b[2]
            rec = (self.files.get(rel) or {}).get("rec") or {}
            dflt = rec.get("default_export")
            if dflt:  # the module marks which symbol `export default` names
                return self.top_symbol(rel, dflt, depth)
            if dflt == "":  # `export default <expression>`: no symbol
                return None
            return self.top_symbol(rel, local, depth) or self.top_symbol(rel, "default", depth)
        return None

    # ---------- types ----------
    def _ns_prefixes(self, qual: str | None) -> list[str]:
        if not qual:
            return []
        parts = qual.split("::")[:-1]
        return ["::".join(parts[:i]) for i in range(len(parts), 0, -1)]

    def resolve_type(self, typ: str, rel: str, from_q: str | None) -> tuple[str | None, bool]:
        """(class id, external) for a declared type name in the context of file `rel`."""
        t = (typ or "").strip()
        for _ in range(4):
            t = _TYPE_NOISE.sub("", t).strip()
            m = _SMART.match(t)
            if not m:
                break
            t = m.group(1).strip()
        t = re.sub(r"<.*>$|\[.*\]$", "", t).strip().strip("'\"")
        t = t.split("|")[0].strip()
        if not t or not re.match(r"^[A-Za-z_][\w.:]*$", t):
            return None, False
        fam = self._fam_of(rel)
        if fam == "c":
            if t.startswith("std::"):
                return None, True
            cands = [f"{p}::{t}" for p in self._ns_prefixes(from_q)] + [t]
            cands += [f"{u}::{t}" for u in self.usings.get(rel, [])]
            for q in cands:
                c = self.lookup_class(q, rel, fam)
                if c:
                    return c, False
            hits = [c for c in self.classes_by_qual.get(t, [])]
            if not hits:
                hits = [c for (f, nm), ids in self.class_by_name.items() if f == fam and nm == _last(t)
                        for c in ids if self.nodes[c]["qual"].endswith("::" + t) or self.nodes[c]["qual"] == t]
            return (hits[0], False) if len(set(hits)) == 1 else (None, False)
        binds = self.bindings.get(rel, {})
        if "." in t:
            head, rest = t.split(".", 1)
            b = binds.get(head)
            if b and b[0] == "mod":
                c = self.top_symbol(b[1], rest)
                return (c, False) if c and self.nodes.get(c, {}).get("kind") in CLASS_KINDS else (None, False)
            if b and b[0] == "ext":
                return None, True
            t = rest.split(".")[-1]
        for nid in self.syms_by_file.get(rel, []):
            n = self.nodes[nid]
            if n.get("kind") in CLASS_KINDS and n["qual"] == t:
                return nid, False
        b = binds.get(t)
        if b:
            if b[0] == "ext":
                return None, True
            c = self._follow(b)
            if c and self.nodes.get(c, {}).get("kind") in CLASS_KINDS:
                return c, False
        hits = self.class_by_name.get((fam, t), [])
        return (hits[0], False) if len(hits) == 1 else (None, False)

    def class_of(self, from_id: str | None) -> str | None:
        """Enclosing class of a symbol node (walks parent quals: method, nested function)."""
        if not from_id or from_id not in self.nodes:
            return None
        n = self.nodes[from_id]
        if n.get("kind") in CLASS_KINDS:
            return from_id
        if from_id in self.method_owner:
            return self.method_owner[from_id]
        fam = family(n.get("lang"))
        ctx = (n.get("decl") or [n["path"]])[0]
        q = n.get("parent_q")
        sep = "::" if fam == "c" else "."
        while q:
            c = self.lookup_class(q, ctx, fam) or self.lookup_class(q, n["path"], fam)
            if c:
                return c
            q = q.rsplit(sep, 1)[0] if sep in q else None
        return None

    def mro(self, cls: str) -> list[str]:
        out, todo = [], [cls]
        while todo:
            c = todo.pop(0)
            if c in out:
                continue
            out.append(c)
            todo.extend(self.bases.get(c, []))
        return out

    def method_in(self, cls: str, name: str, skip_self: bool = False) -> str | None:
        for c in self.mro(cls)[1 if skip_self else 0:]:
            hits = self.methods.get(c, {}).get(name)
            if hits:
                return hits[0]
        return None

    def member_type(self, cls: str, key: str) -> str | None:
        for c in self.mro(cls):
            t = (self.nodes[c].get("members") or {}).get(key)
            if t:
                return t
        return None

    # ---------- inheritance ----------
    def run_bases(self) -> None:
        for fam_name in sorted(self.classes_by_qual):
            for cid in self.classes_by_qual[fam_name]:
                n = self.nodes[cid]
                out = []
                for b in n.get("bases") or []:
                    bc, _ = self.resolve_type(b, n["path"], n["qual"])
                    if bc and bc != cid and bc not in out:
                        out.append(bc)
                        same = self.nodes[bc]["path"] == n["path"]
                        self.add(cid, bc, "inherit", 0.85 if same else 0.8, "file" if same else "qual",
                                 n["path"], n.get("line"))
                if out:
                    self.bases[cid] = out

    def run_impls(self) -> None:
        subs: dict[str, list[str]] = {}
        for c, bs in self.bases.items():
            for b in bs:
                subs.setdefault(b, []).append(c)
        for cls in sorted(self.methods):
            desc, todo = [], list(subs.get(cls, []))
            while todo:
                d = todo.pop(0)
                if d in desc or d == cls:
                    continue
                desc.append(d)
                todo.extend(subs.get(d, []))
            if not desc:
                continue
            for name, mids in sorted(self.methods[cls].items()):
                for mid in mids:
                    m = self.nodes[mid]
                    if m.get("kind") == "ctor":
                        continue
                    if family(m.get("lang")) == "c" and not (m.get("virtual") or m.get("pure")):
                        continue
                    hits = sorted({x for d in desc for x in self.methods.get(d, {}).get(name, [])})
                    if hits:
                        self.impls[mid] = hits

    # ---------- calls ----------
    def from_id(self, rel: str, qual: str | None, line) -> str:
        if not qual:
            return rel
        spans = self.loc.get((rel, qual))
        if not spans:
            return rel
        if len(spans) > 1 and line:
            for a, b, nid in spans:
                if a <= line <= b:
                    return nid
        return spans[0][2]

    def run_calls(self) -> None:
        for rel in sorted(self.files):
            f = self.files[rel]
            rec = f.get("rec")
            if not rec or f.get("vendor") or rec.get("skip"):
                continue
            mult = 0.5 if (rec.get("ok") is False or rec.get("conf") == "low") else 1.0
            for c in rec.get("calls") or []:
                src = self.from_id(rel, c.get("from"), c.get("line"))
                hits = self.resolve_call(rel, c, src)
                if not hits:
                    self.unresolved += 1
                    continue
                self.resolved += 1
                for tid, conf, why in hits:
                    self.add(src, tid, "call", conf * mult, why, rel, c.get("line"))

    def _cands(self, fam: str, name: str, kinds=CALL_KINDS) -> list[str]:
        short = _last(name)
        ids = self.by_name.get((fam, short), [])
        if "::" in name:
            ids = [i for i in ids if self.nodes[i]["qual"] == name or self.nodes[i]["qual"].endswith("::" + name)]
        return [i for i in ids if self.nodes[i].get("kind") in kinds]

    def resolve_call(self, rel: str, c: dict, src: str) -> list[tuple[str, float, str]]:
        name = c.get("name") or ""
        recv, rtype = c.get("recv"), c.get("recv_type")
        fam = self._fam_of(rel)
        glob = name.startswith("::")  # C++ `::close(fd)`: global scope, never a member
        if glob:
            name = name.lstrip(":")
        short = _last(name)
        if not short or name in SELF_RECV or name == "super":
            return []
        if fam == "c" and name.startswith("std::"):
            return []
        from_q = self.nodes[src].get("qual") if src in self.nodes and self.nodes[src].get("type") == "symbol" else None
        cls = self.class_of(src) if from_q else None
        if recv == "?":
            # receiver is an expression (`", ".join(x)`, `make().read()`): only the method name is known
            return self._method_name(fam, short)
        # 1. self / this / cls / implicit member (C/C++), super
        if recv in SELF_RECV or (recv is None and fam == "c" and cls and "::" not in name and not glob):
            if cls:
                hit = self.method_in(cls, short)
                if hit:
                    return [(hit, 0.9, "self")]
            if recv is not None:
                return self._method_name(fam, short)
        if recv == "super":
            hit = self.method_in(cls, short, skip_self=True) if cls else None
            return [(hit, 0.9, "self")] if hit else []
        # 2. member type
        typ = rtype
        if not typ and recv and cls:
            key = recv.split(".", 1)[1] if recv.startswith(("self.", "this.")) else recv
            if "." not in key:
                typ = self.member_type(cls, key)
        if typ:
            tcls, external = self.resolve_type(typ, rel, from_q)
            if tcls:
                hit = self.method_in(tcls, short)
                return [(hit, 0.85, "member-type")] if hit else []
            if external:
                return []
        if recv is not None:
            b = self.bindings.get(rel, {}).get(recv)
            if b is None and fam == "py" and "." in recv:
                mod = self.py_module(rel, recv, 0)
                b = ("mod", mod) if mod else None
            if b is not None:
                if b[0] == "ext":
                    return []
                tgt = self._follow(b)
                if tgt and b[0] == "mod":
                    hit = self.top_symbol(tgt, short)
                    return [(hit, 0.8, "import")] if hit else []
                if tgt and self.nodes.get(tgt, {}).get("kind") in CLASS_KINDS:
                    hit = self.method_in(tgt, short)
                    return [(hit, 0.8, "import")] if hit else []
            if fam in ("py", "js") and "." not in recv:
                # `A.make()` on a class with no import binding: same-file class, else a unique class name
                tcls, _ = self.resolve_type(recv, rel, from_q)
                hit = self.method_in(tcls, short) if tcls else None
                if hit:
                    same = self.nodes[tcls]["path"] == rel
                    return [(hit, 0.85, "file") if same else (hit, 0.5, "unique")]
            return self._method_name(fam, short)
        if fam == "c" and "::" in name and c.get("kind") != "new":
            # `ui::Widget::create()`, `Base::f()`: a static or explicitly qualified method call
            pre, _, mname = name.rpartition("::")
            tcls, _ = self.resolve_type(pre, rel, from_q)
            hit = self.method_in(tcls, mname) if tcls else None
            if hit:
                same = self.nodes[hit]["path"] == rel
                return [(hit, 0.85, "file") if same else (hit, 0.8, "qual")]
        kinds = CALL_KINDS if c.get("kind") != "new" else CLASS_KINDS | {"ctor"}
        # 3. same file
        same = [i for i in self.syms_by_file.get(rel, []) if self.nodes[i]["name_short"] == short
                and self.nodes[i].get("kind") in kinds
                and ("::" not in name or self.nodes[i]["qual"] == name or self.nodes[i]["qual"].endswith("::" + name))]
        if same:
            if len(same) > 1 and from_q:
                inner = [i for i in same if self.nodes[i]["qual"].startswith(from_q + ".")]
                same = inner or same
            return [(same[0], 0.85, "file")]
        # 4. import
        if fam in ("py", "js"):
            b = self.bindings.get(rel, {}).get(name)
            if b is not None:
                if b[0] == "ext":
                    return []
                tgt = self._follow(b)
                if tgt and tgt in self.nodes and self.nodes[tgt].get("type") == "symbol":
                    return [(tgt, 0.8, "import")]
        elif fam == "c":
            clo = self.include_closure(rel)
            hits = [i for i in self._cands(fam, name, kinds) if self.nodes[i]["path"] in clo
                    or (self.nodes[i].get("decl") or [None])[0] in clo]
            if len(hits) == 1:
                return [(hits[0], 0.8, "import")]
            if hits:
                return [(sorted(hits)[0], 0.8, "import")]
        cands = self._cands(fam, name, kinds)
        # 5. qualified name
        if "::" in name:
            if len(cands) == 1:
                return [(cands[0], 0.8, "qual")]
        if not cands:
            return []
        # 6. same module
        mod = self._mod(rel)
        mine = [i for i in cands if self.nodes[i].get("mod") == mod and mod is not None]
        if len(mine) == 1:
            return [(mine[0], 0.6, "module")]
        # 7. unique in the language family
        if len(cands) == 1:
            return [(cands[0], 0.5, "unique")]
        pool = mine if len(mine) > 1 else cands
        return self._ambiguous(pool)

    def _method_name(self, fam: str, short: str) -> list[tuple[str, float, str]]:
        ids = self.methods_by_name.get((fam, short), [])
        ids = [i for i in ids if self.nodes[i].get("kind") != "ctor"]
        owners = {self.method_owner.get(i) for i in ids}
        if len(owners) == 1 and ids:
            return [(ids[0], 0.4, "method-name")]
        return self._ambiguous(ids)

    @staticmethod
    def _ambiguous(ids: list[str]) -> list[tuple[str, float, str]]:
        ids = sorted(set(ids))
        if 2 <= len(ids) <= MAX_AMBIG:
            return [(i, 0.3 / len(ids), "ambiguous") for i in ids]
        return []

    # ---------- contracts and data ----------
    def run_contracts(self) -> None:
        messages: dict[str, str] = {}
        tables: dict[str, list[str]] = {}
        for nid in sorted(self.nodes):
            n = self.nodes[nid]
            if n.get("type") != "symbol":
                continue
            if n.get("kind") == "message":
                messages.setdefault(n["qual"], nid)
            elif n.get("kind") == "table":
                tables.setdefault(n["name_short"].lower(), []).append(nid)
        msg_fields = {}
        for q, mid in messages.items():
            fields = {_norm_field(k) for k in (self.nodes[mid].get("members") or {})}
            if len(fields) >= 3:
                msg_fields[mid] = fields
        for rel in sorted(self.files):
            f = self.files[rel]
            rec = f.get("rec")
            if not rec or f.get("vendor") or rec.get("skip"):
                continue
            lang = rec.get("lang")
            for m in rec.get("mentions") or []:
                mid = messages.get(m)
                if mid and self.nodes[mid]["path"] != rel:
                    self.add(rel, mid, "contract", 0.6, "mention", rel, None)
            if lang not in ("proto", "sql"):
                for nid in self.syms_by_file.get(rel, []):
                    n = self.nodes[nid]
                    kind = n.get("kind")
                    if kind in CLASS_KINDS:
                        words = {_norm_field(k) for k in (n.get("members") or {})}
                        exact = True
                    elif kind in ("function", "method", "ctor", "test"):
                        words = {_norm_field(w) for w in (n.get("words") or [])}
                        exact = False
                    else:
                        continue
                    if len(words) < 3:
                        continue
                    for mid, fields in msg_fields.items():
                        shared = words & fields
                        if len(shared) < 3:
                            continue
                        score = len(shared) / len(words | fields) if exact else len(shared) / len(fields)
                        if score >= 0.6:
                            self.add(nid, mid, "contract", 0.6, "fields", rel, n.get("line"))
            for s in rec.get("strings") or []:
                if s.get("kind") != "sql":
                    continue
                cands = tables.get(str(s.get("value") or "").lower())
                if not cands:
                    continue
                mod = self._mod(rel)
                closure = set((self.modules.get(mod) or {}).get("closure") or []) if mod else set()
                cands = sorted(cands, key=lambda t: (self.nodes[t].get("mod") != mod,
                                                     self.nodes[t].get("mod") not in closure, t))
                src = self.from_id(rel, s.get("from"), s.get("line"))
                self.add(src, cands[0], "data", 0.8, "sqlname", rel, s.get("line"))

    def run(self) -> list[dict]:
        self.run_imports()
        self.run_bases()
        self.run_impls()
        self.run_calls()
        self.run_contracts()
        return [self.edges[k] for k in sorted(self.edges, key=lambda k: (k[2], k[0], k[1]))]

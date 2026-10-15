"""wikimap.fresh: Finding format, baseline file, rules, debt, ratchet (spec §7.1–§7.3).

Most tests drive ``fresh`` through ``FakeMap``, a duck-typed stand-in for the §6 ``Map``
contract, so the rules are pinned independently of the graph builder. The ``poly`` fixture
tests at the bottom run the real ``open_map`` and skip until it lands.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
for p in (str(SCRIPTS), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from wikimap import fresh  # noqa: E402
from wikimap.fresh import Finding  # noqa: E402

PY = "lib/src/calc.py"


# ---- shared helpers (imported by test_cli.py and test_hook.py) -----------------------------

def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def mkdoc(text="Does the thing.", params=None, explicit=False):
    params = dict(params or {})
    return {"style": "docstring", "brief": text[:200], "text": text, "params": params,
            "explicit_params": explicit, "returns": "", "raises": [], "see": [], "deprecated": False,
            "line": 1, "end": 1, "hash": sha(text + repr(sorted(params.items())))}


class FakeMap:
    """The §6 Map contract surface that fresh.py and cli.py read, nothing more."""

    def __init__(self, root, modgate=True, project="demo"):
        self.root = Path(root)
        self.data = self.root / ".wiki"
        self.modgate, self.project, self.rev, self.built = modgate, project, "r0", "2026-10-14T00:00:00Z"
        self.nodes, self.children, self.edges, self.files, self.modules, self.diagrams = {}, {}, [], {}, {}, {}
        self.stats = {"files": 0, "symbols": 0, "edges": 0, "resolved_hi": 0.75, "unresolved": 0,
                      "truncated": False, "seconds": 0.1}
        self.findings = []
        self._n = 0
        self._node(".", None, "root", "sys", "system", project)
        self.modules[project] = self._minfo(".", [], [])

    @staticmethod
    def _minfo(mid, deps, closure, icd=None):
        return {"id": mid, "deps": list(deps), "closure": list(closure), "sources": [], "docs": [],
                "icd": icd, "bind": {}, "reqs": {}}

    def _bump(self):
        self._n += 1
        self.rev = f"r{self._n}"

    def _node(self, nid, parent, type_, tier, kind, name, **kw):
        self.nodes[nid] = {"id": nid, "parent": parent, "type": type_, "tier": tier, "kind": kind, "name": name,
                           "badges": {}, **kw}
        if parent is not None:
            self.children.setdefault(parent, []).append(nid)
        self._bump()
        return nid

    def module(self, name, mid, parent=".", deps=(), closure=None, icd=None):
        self._node(mid, parent, "module", "sys", "code", name)
        self.modules[name] = self._minfo(mid, deps, deps if closure is None else closure, icd)
        return mid

    def group(self, gid, parent="."):
        return self._node(gid, parent, "group", "sys", "group", gid.rsplit("/", 1)[-1])

    def file(self, rel, parent, lang="python", insrc=True, test=False, vendor=False, file_doc="Module doc.",
             refs=()):
        self._node(rel, parent, "file", "code", lang, rel.rsplit("/", 1)[-1], lang=lang, vendor=vendor)
        self.files[rel] = {"node": rel, "mod": self.module_of(parent), "lang": lang, "sha": "x", "insrc": insrc,
                           "test": test, "vendor": vendor,
                           "rec": {"lang": lang, "ok": True, "skip": None,
                                   "file_doc": mkdoc(file_doc) if file_doc else None,
                                   "symbols": [], "refs": list(refs), "calls": [], "imports": []}}
        return rel

    def sym(self, rel, qual, line=1, kind="function", pub=True, doc=None, params=(), sig="s0", body="b0",
            key=None, sig_text="", ignore=(), override=False, test=False):
        nid = f"{rel}#{qual}"
        name = qual.split("::")[-1].split(".")[-1]
        self._node(nid, rel, "symbol", "code", kind, name, qual=qual, key=key or nid, pub=pub,
                   src=[rel, line, line + 3], decl=None, doc=doc, params=list(params), sig=sig_text)
        self.files[rel]["rec"]["symbols"].append(
            {"qual": qual, "name": name, "kind": kind, "line": line, "sig_hash": sig, "body_hash": body,
             "ignore": list(ignore), "override": override, "test": test, "params": list(params)})
        return nid

    def _rec(self, nid):
        n = self.nodes[nid]
        for s in self.files[n["src"][0]]["rec"]["symbols"]:
            if s["qual"] == n["qual"]:
                return s
        raise KeyError(nid)

    def edit(self, nid, *, sig=None, body=None, doc="keep", params=None):
        rec = self._rec(nid)
        if sig is not None:
            rec["sig_hash"] = sig
        if body is not None:
            rec["body_hash"] = body
        if doc != "keep":
            self.nodes[nid]["doc"] = doc
        if params is not None:
            self.nodes[nid]["params"] = list(params)
        self._bump()

    def rename(self, nid, qual):
        n = self.nodes.pop(nid)
        rec = self._rec_by(n)
        self.children[n["parent"]].remove(nid)
        new = f"{n['src'][0]}#{qual}"
        n.update(id=new, qual=qual, key=new, name=qual.split(".")[-1])
        rec["qual"], rec["name"] = qual, n["name"]
        self.nodes[new] = n
        self.children[n["parent"]].append(new)
        self._bump()
        return new

    def _rec_by(self, n):
        return next(s for s in self.files[n["src"][0]]["rec"]["symbols"] if s["qual"] == n["qual"])

    def remove(self, nid):
        n = self.nodes.pop(nid)
        self.files[n["src"][0]]["rec"]["symbols"].remove(self._rec_by(n))
        self.children[n["parent"]].remove(nid)
        self._bump()

    def anc(self, nid):
        chain, p = [], self.nodes[nid]["parent"]
        while p is not None:
            chain.append(p)
            p = self.nodes[p]["parent"]
        return chain[::-1]

    def module_of(self, nid):
        cur = nid
        while cur is not None and cur in self.nodes:
            n = self.nodes[cur]
            if n["type"] in ("module", "root"):
                return next((k for k, v in self.modules.items() if v["id"] == cur), None)
            cur = n["parent"]
        return None

    def level(self, lens, at):
        return {"at": at} if self.children.get(at) and self.nodes[at]["type"] != "symbol" else None

    def show_text(self, lens, at, depth=1):
        rows = [f"  {self.nodes[c]['name']}  {self.nodes[c]['type']}" for c in self.children.get(at, [])]
        return f"{self.nodes[at]['name']}  [{lens}]  at {at}\n" + "\n".join(rows)

    def trace_text(self, nid, direction, depth):
        return f"trace {nid} {direction} {depth}"


def std_map(root) -> FakeMap:
    """lib (calc.py with one of every symbol case), app (calls lib, no deps), proto; a root
    diagram drawing only lib plus a ghost node."""
    fm = FakeMap(root)
    fm.module("lib", "lib")
    fm.module("app", "app")
    fm.module("proto", "proto")
    fm.file(PY, "lib", refs=[{"text": "Nowhere", "style": "see", "line": 5, "from": "area"},
                             {"text": "helper()", "style": "see", "line": 6, "from": "area"},
                             {"text": "https://example.org/x", "style": "see", "line": 7, "from": "area"}])
    fm.sym(PY, "area", line=3, doc=mkdoc("Area.", {"w": "m", "h": "m"}, True), params=["w", "h"])
    fm.sym(PY, "helper", line=10)
    fm.sym(PY, "_private", line=14, pub=False)
    fm.sym(PY, "Engine", line=18, kind="class", doc=mkdoc("Engine."))
    fm.sym(PY, "Engine.__init__", line=19, kind="method")
    fm.sym(PY, "Engine.run", line=24, kind="method", doc=mkdoc("Run.", {"n": "", "mode": ""}, True),
           params=["self", "n", "strict"])
    fm.sym(PY, "Engine.shape", line=30, kind="method", override=True)
    fm.sym(PY, "quiet", line=34, ignore=["UNDOC"])
    fm.sym(PY, "LIMIT", line=38, kind="const")
    fm.file("lib/test/test_calc.py", "lib", insrc=False, test=True)
    fm.sym("lib/test/test_calc.py", "test_area", line=3, test=True)
    main = fm.sym(fm.file("app/src/main.py", "app"), "main", line=2, doc=mkdoc("Main."))
    fm.edges.append({"s": main, "t": f"{PY}#area", "k": "call", "conf": 0.9, "why": "import",
                     "file": "app/src/main.py", "line": 4})
    fm.diagrams["."] = {"doc": "demo.md", "line": 8, "edges": [], "nodes": {
        "LIB": {"label": "lib", "ref": "lib", "ext": False, "shape": "module", "line": 9},
        "GHOST": {"label": "ghost_mod", "ref": None, "ext": False, "shape": "module", "line": 10},
        "OP": {"label": "Operator", "ref": None, "ext": True, "shape": "other", "line": 11}}}
    return fm


def run(cli, argv, stdin=""):
    out, errb, old = io.StringIO(), io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(out), redirect_stderr(errb):
            code = cli.main(list(argv))
    finally:
        sys.stdin = old
    return code, out.getvalue(), errb.getvalue()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)


def codes_ids(fs):
    return {(f.code, f.id) for f in fs}


# ---- Finding -------------------------------------------------------------------------------

def test_line_padding_and_parts():
    f = Finding("UNDOC", "finding", "lib", "helper", ["src/calc.py:10"], "add a docstring to helper()")
    assert f.line() == "UNDOC       lib  helper  src/calc.py:10  → add a docstring to helper()"
    v = Finding("XCALL", "violation", "web", "fmt", ["src/entry.ts:3"], "x")
    assert v.label == "E:XCALL" and v.line() == "E:XCALL     web  fmt  src/entry.ts:3  → x"
    assert Finding("DOCREVIEW", "finding", "m", "", [], "").line() == "DOCREVIEW   m"
    assert Finding("DIAGNODE", "finding", "m", "G", ["m.md:4", "m.md:9"], "").line() == "DIAGNODE    m  G  m.md:4 m.md:9"
    assert f.label.ljust(10) == f.line()[:10]


def test_json_shape_and_key():
    f = Finding("DOCSIG", "finding", "pkg", "Engine.run", ["src/pkg/core.py:9"], "fix", node="n#x")
    assert f.key == "DOCSIG|pkg|Engine.run"
    assert f.json() == {"code": "DOCSIG", "severity": "finding", "module": "pkg", "id": "Engine.run",
                        "files": ["src/pkg/core.py:9"], "action": "fix", "node": "n#x", "key": "DOCSIG|pkg|Engine.run"}


def test_sort_order():
    mk = lambda c, m="a", i="x": Finding(c, "finding", m, i, [], "")  # noqa: E731
    fs = [mk("UNDRAWN"), mk("UNDOC", "b"), mk("UNDOC", "a", "z"), mk("UNDOC", "a", "y"), mk("XCALL"), mk("DEADLINK")]
    assert [(f.code, f.module, f.id) for f in fresh.sort_findings(fs)] == [
        ("XCALL", "a", "x"), ("UNDOC", "a", "y"), ("UNDOC", "a", "z"), ("UNDOC", "b", "x"),
        ("DEADLINK", "a", "x"), ("UNDRAWN", "a", "x")]


# ---- baseline and config files -------------------------------------------------------------

def test_baseline_exact_text_and_round_trip(tmp_path):
    base = {"v": 1, "created": "2026-10-14T09:00:00Z",
            "symbols": {"b.py#f": ["s2", "b2", "-"], "a.py#g": ["s1", "b1", "d1"]},
            "debt": ["UNDRAWN|demo|proto", "UNDOC|lib|f"]}
    fresh.save_baseline(tmp_path, base)
    p = tmp_path / ".wikimap" / "baseline.json"
    assert p.read_text() == (
        '{"v": 1,\n "created": "2026-10-14T09:00:00Z",\n "symbols": {\n'
        '  "a.py#g": ["s1", "b1", "d1"],\n  "b.py#f": ["s2", "b2", "-"]\n },\n'
        ' "debt": [\n  "UNDOC|lib|f",\n  "UNDRAWN|demo|proto"\n ]\n}\n')
    assert fresh.load_baseline(tmp_path) == {**base, "debt": sorted(base["debt"])}
    assert sorted(x.name for x in p.parent.iterdir()) == ["baseline.json"]  # no temp file left


def test_baseline_empty_missing_and_corrupt(tmp_path):
    assert fresh.load_baseline(tmp_path) is None
    fresh.save_baseline(tmp_path, {"v": 1, "created": None, "symbols": {}, "debt": []})
    p = tmp_path / ".wikimap" / "baseline.json"
    assert p.read_text() == '{"v": 1,\n "created": null,\n "symbols": {},\n "debt": []\n}\n'
    assert json.loads(p.read_text())["symbols"] == {}
    for bad in ("<<<<<<< HEAD\n{", "[]", '{"v": 2, "symbols": {}, "debt": []}',
                '{"v": 1, "symbols": {"k": ["a", "b"]}, "debt": []}', '{"v": 1, "symbols": {}, "debt": [1]}'):
        p.write_text(bad)
        with pytest.raises(fresh.BaselineError):
            fresh.load_baseline(tmp_path)


def test_config(tmp_path):
    assert fresh.load_config(tmp_path) == {}
    (tmp_path / ".wikimap").mkdir()
    (tmp_path / ".wikimap" / "config.json").write_text('{"violations": ["XCALL"], "max_hook_lines": 3}')
    assert fresh.load_config(tmp_path)["max_hook_lines"] == 3
    for bad in ("{nope", "[1]"):
        (tmp_path / ".wikimap" / "config.json").write_text(bad)
        with pytest.raises(fresh.ConfigError):
            fresh.load_config(tmp_path)


# ---- rules on the fake map -----------------------------------------------------------------

@pytest.fixture
def fm(tmp_path):
    return std_map(tmp_path / "repo")


def test_each_rule_fires_once_and_stays_quiet_elsewhere(fm):
    got = codes_ids(fresh.compute(fm, None))
    assert got == {("UNDOC", "helper"), ("DOCSIG", "Engine.run"), ("DEADLINK", "area"),
                   ("XCALL", "lib"), ("DIAGNODE", "GHOST"), ("UNDRAWN", "app"), ("UNDRAWN", "proto")}


def test_exact_lines(fm):
    lines = {f.code: f.line() for f in fresh.compute(fm, None)}
    assert lines["UNDOC"] == "UNDOC       lib  helper  src/calc.py:10  → add a docstring to helper(): what it does, units, errors"
    assert lines["DOCSIG"] == ("DOCSIG      lib  Engine.run  src/calc.py:24  → doc names [n, mode], "
                               "signature has [n, strict]: fix the params section")
    assert lines["DEADLINK"] == ('DEADLINK    lib  area  src/calc.py:5  → @see target "Nowhere" matches no symbol; '
                                 'fix the name or drop it')
    assert lines["XCALL"] == ("XCALL       app  lib  src/main.py:4  → app uses lib but lib is not reachable "
                              "through app's deps; add it to deps (needs approval) or remove the coupling")
    assert lines["DIAGNODE"] == ('DIAGNODE    demo  GHOST  demo.md:10  → Mermaid node "ghost_mod" matches no module; '
                                 'use the module name or mark it :::ext')
    undrawn = sorted(f.line() for f in fresh.compute(fm, None, codes={"UNDRAWN"}))
    assert undrawn[0] == 'UNDRAWN     demo  app  demo.md:8  → add app to "Subsystems and interactions" in demo.md with a labelled edge'


def test_undoc_action_per_language(tmp_path):
    fm = FakeMap(tmp_path)
    fm.module("m", "m")
    for rel, lang in (("m/a.cpp", "cpp"), ("m/b.ts", "ts"), ("m/c.go", "go")):
        fm.file(rel, "m", lang=lang)
        fm.sym(rel, f"f_{lang}")
    fm.sym("m/a.cpp", "ns::Thing", kind="class")
    acts = {f.id: f.action for f in fresh.compute(fm, None)}
    assert acts["f_cpp"] == "add a /// doc comment above f_cpp(): what it does, units, errors"
    assert acts["f_ts"] == "add a /** JSDoc */ above f_ts(): what it does, units, errors"
    assert acts["f_go"] == "add a doc comment above f_go(): what it does, units, errors"
    assert acts["ns::Thing"] == "add a /// doc comment above Thing: what it does, units, errors"


def test_undoc_exemptions(tmp_path):
    fm = FakeMap(tmp_path)
    fm.module("m", "m")
    fm.file("m/x.cpp", "m", lang="cpp")
    fm.sym("m/x.cpp", "A::~A", kind="method")
    fm.sym("m/x.cpp", "A::A", kind="ctor")
    fm.sym("m/x.cpp", "A::B", kind="method", sig_text="B() = default")
    fm.sym("m/x.cpp", "Geo.REQ_GEO_001_area", kind="test")
    fm.sym("m/x.cpp", "MAX", kind="macro")
    fm.sym("m/x.cpp", "ns", kind="namespace")
    fm.file("m/v.c", "m", lang="c", vendor=True)
    fm.sym("m/v.c", "vend")
    fm.file("m/notsrc.py", "m", insrc=False)
    fm.sym("m/notsrc.py", "tool")
    assert fresh.compute(fm, None) == []
    fm.config = {"undoc": "off"}
    fm.file("m/y.py", "m")
    fm.sym("m/y.py", "loud")
    assert fresh.compute(fm, None) == []


def test_python_module_docstring(fm):
    fm.file("lib/src/pkg/nodoc.py", "lib", file_doc=None)
    fm.sym("lib/src/pkg/nodoc.py", "f", doc=mkdoc("F."))
    fm.file("lib/src/pkg/__init__.py", "lib", file_doc=None)  # no public symbol: quiet
    hits = [f for f in fresh.compute(fm, None, codes={"UNDOC"}) if f.files == ["src/pkg/nodoc.py:1"]]
    assert [(f.id, f.action) for f in hits] == [("pkg.nodoc", "add a module docstring: what it is for")]


def test_docsig_quiet_cases(tmp_path):
    fm = FakeMap(tmp_path)
    fm.module("m", "m")
    fm.file("m/a.py", "m")
    fm.sym("m/a.py", "ok", doc=mkdoc("x", {"a": ""}, True), params=["self", "a", "*args", "**kw"])
    fm.sym("m/a.py", "implicit", doc=mkdoc("x", {"zzz": ""}, False), params=["a"])
    fm.sym("m/a.py", "docs_varargs", doc=mkdoc("x", {"a": "", "*args": ""}, True), params=["a", "*args"])
    assert fresh.compute(fm, None) == []


def test_xcall_quiet_cases(fm):
    def xc():
        return [f for f in fresh.compute(fm, None) if f.code == "XCALL"]
    fm.modules["app"]["closure"] = ["lib"]
    assert xc() == []
    fm.modules["app"]["closure"] = []
    fm.edges[0]["conf"] = 0.5
    assert xc() == []
    fm.edges[0]["conf"] = 0.9
    fm.modgate = False
    assert xc() == []
    fm.modgate = True
    fm.files[PY]["vendor"] = True
    assert xc() == []
    fm.files[PY]["vendor"] = False
    fm.module("sub", "app/sub", parent="app")  # calling into a descendant module is fine
    fm.file("app/sub/s.py", "app/sub")
    fm.edges[0]["t"] = fm.sym("app/sub/s.py", "s", doc=mkdoc("S."))
    assert xc() == []


def test_violation_severity_from_config(fm):
    fm.config = {"violations": ["XCALL"]}
    x = [f for f in fresh.compute(fm, None) if f.code == "XCALL"][0]
    assert x.severity == "violation" and x.line().startswith("E:XCALL     app  lib")


def test_icdsym(fm, tmp_path):
    pytest.importorskip("wikimap.mdparse")
    icd = fm.root / "lib" / "docs" / "lib.icd.md"
    icd.parent.mkdir(parents=True)
    icd.write_text("# lib ICD\n\n## Public API\n\n```py\narea(w, h)\nhelper(x)\nperimeter(w, h)\nprint(x)\n"
                   "MAX(a)\n```\n\n## Notes\n\n```py\nnot_api(x)\n```\n")
    fm.modules["lib"]["icd"] = "lib/docs/lib.icd.md"
    fs = fresh.compute(fm, None, codes={"ICDSYM"})
    assert [f.line() for f in fs] == [
        "ICDSYM      lib  perimeter  docs/lib.icd.md:8  → ICD names perimeter(), no such symbol; fix the ICD "
        "(modgate: version +1, status draft, changelog) or restore it"]


def test_scopes(fm):
    assert codes_ids(fresh.compute(fm, None, files={"app/src/main.py"})) == {("XCALL", "lib")}
    assert codes_ids(fresh.compute(fm, None, files={"demo.md"})) == {
        ("DIAGNODE", "GHOST"), ("UNDRAWN", "app"), ("UNDRAWN", "proto")}
    assert codes_ids(fresh.compute(fm, None, modules={"lib"}, codes={"UNDOC"})) == {("UNDOC", "helper")}


# ---- debt, staleness, ratchet --------------------------------------------------------------

def test_baseline_creation_records_debt(fm):
    base = fresh.create_baseline(fm)
    assert base["created"].endswith("Z")
    assert set(base["debt"]) == {f.key for f in fresh.compute(fm, None)}
    assert base["symbols"][f"{PY}#area"] == ["s0", "b0", mkdoc("Area.", {"w": "m", "h": "m"}, True)["hash"]]
    assert base["symbols"][f"{PY}#helper"] == ["s0", "b0", "-"]
    assert fresh.compute(fm, base) == []
    assert {f.key for f in fresh.compute(fm, base, all_=True)} == set(base["debt"])


def test_undoc_debt_resurfaces_when_code_changes(fm):
    base = fresh.create_baseline(fm)
    fm.edit(f"{PY}#helper", body="b1")
    assert codes_ids(fresh.compute(fm, base)) == {("UNDOC", "helper")}


def test_docstale_and_docreview(fm):
    area = f"{PY}#area"
    base = fresh.create_baseline(fm)
    fm.edit(area, sig="s1")
    f = fresh.compute(fm, base)[0]
    assert (f.code, f.id) == ("DOCSTALE", "area")
    assert f.action == (f"signature changed since its doc was confirmed; update the doc, or: "
                        f'wiki ack {area} --unchanged "<why>"')
    fm.edit(area, sig="s0", body="b1")
    f = fresh.compute(fm, base)[0]
    assert (f.code, f.action) == ("DOCREVIEW", f'body changed, doc unchanged; check every claim in the doc, or: '
                                               f'wiki ack {area} --unchanged "<why>"')
    fm.edit(area, doc=mkdoc("Area, reviewed.", {"w": "m", "h": "m"}, True))
    assert fresh.compute(fm, base) == []


def test_advance_transitions(fm):
    area, helper = f"{PY}#area", f"{PY}#helper"
    base = fresh.create_baseline(fm)
    fm.edit(area, body="b1")                                    # code changed, doc unchanged → keep
    new = fresh.advance(fm, base, files=None)
    assert new["symbols"][area] == base["symbols"][area]
    assert codes_ids(fresh.compute(fm, new)) == {("DOCREVIEW", "area")}
    fm.edit(area, doc=mkdoc("Area v2.", {"w": "m", "h": "m"}, True))   # doc changed → refresh
    new = fresh.advance(fm, new, files=None)
    assert new["symbols"][area] == ["s0", "b1", mkdoc("Area v2.", {"w": "m", "h": "m"}, True)["hash"]]
    fresh_key = fm.sym(PY, "brand_new", line=50, doc=mkdoc("New."))  # new key → added
    new = fresh.advance(fm, new, files={PY})
    assert fresh_key in new["symbols"]
    fm.remove(helper)                                           # vanished → dropped, its debt pruned
    new = fresh.advance(fm, new, files={PY})
    assert helper not in new["symbols"] and "UNDOC|lib|helper" not in new["debt"]
    assert base is not new and helper in base["symbols"]        # input untouched


def test_advance_moves_renamed_entry_and_debt(fm):
    base = fresh.create_baseline(fm)
    assert "UNDOC|lib|helper" in base["debt"]
    new_id = fm.rename(f"{PY}#helper", "assist")
    assert fresh.compute(fm, base, codes={"UNDOC"})[0].id == "assist"  # not in baseline yet
    new = fresh.advance(fm, base, files={PY})
    assert new["symbols"][new_id] == base["symbols"][f"{PY}#helper"]
    assert f"{PY}#helper" not in new["symbols"]
    assert "UNDOC|lib|assist" in new["debt"] and "UNDOC|lib|helper" not in new["debt"]
    assert fresh.compute(fm, new) == []


def test_advance_full_prunes_unproduced_debt(fm):
    base = fresh.create_baseline(fm)
    fm.diagrams["."]["nodes"]["APP"] = {"label": "app", "ref": "app", "ext": False, "shape": "module", "line": 12}
    new = fresh.advance(fm, base, files=None)
    assert "UNDRAWN|demo|app" in base["debt"] and "UNDRAWN|demo|app" not in new["debt"]
    assert "UNDRAWN|demo|proto" in new["debt"]


def test_changed_files(fm):
    base = fresh.create_baseline(fm)
    assert fresh.changed_files(fm, base) == set()
    fm.edit(f"{PY}#area", body="b9")
    assert fresh.changed_files(fm, base) == {PY}
    assert "app/src/main.py" in fresh.changed_files(fm, None)


def test_annotate_badges_and_never_writes(fm):
    base = fresh.create_baseline(fm)
    fresh.save_baseline(fm.root, base)
    fm.edit(f"{PY}#area", sig="s1")
    fresh.annotate(fm)
    assert [f.code for f in fm.findings] == ["DOCSTALE"]
    root = fm.nodes["."]["badges"]
    assert (root["findings"], root["stale"], root["debt"]) == (1, 1, len(base["debt"]))
    assert fm.nodes["lib"]["badges"]["findings"] == 1 and fm.nodes["app"]["badges"]["findings"] == 0
    assert fm.nodes["app"]["badges"]["debt"] == 2   # XCALL (on main) + UNDRAWN app


def test_annotate_without_or_with_corrupt_baseline(fm):
    fresh.annotate(fm)
    assert len(fm.findings) == 7 and not (fm.root / ".wikimap").exists()
    (fm.root / ".wikimap").mkdir(parents=True)
    (fm.root / ".wikimap" / "baseline.json").write_text("{broken")
    fresh.annotate(fm)
    assert len(fm.findings) == 7


# ---- real Map on the poly fixture (waits for WP3) ------------------------------------------

@pytest.fixture
def poly_map(request, tmp_path):
    wm = pytest.importorskip("wikimap")
    if not hasattr(wm, "open_map"):
        pytest.skip("wikimap.open_map not landed")
    try:
        root = request.getfixturevalue("poly")
    except pytest.FixtureLookupError:
        pytest.skip("conftest poly fixture not landed")
    return wm.open_map(Path(root), tmp_path / "data", exact=True)


def test_poly_each_code_fires(poly_map):
    fs = fresh.compute(poly_map, None)
    got = {(f.code, f.module, f.id) for f in fs}
    assert ("UNDOC", "geo", "geo::make") in got
    assert any(c == "DOCSIG" and m == "pkg" and i.endswith("Engine.run") for c, m, i in got)
    assert ("ICDSYM", "geo", "perimeter") in got
    assert ("XCALL", "web", "fmt") in got
    assert any(f.code == "DEADLINK" and "Nowhere" in f.action for f in fs)
    assert ("DIAGNODE", "poly", "GHOST") in got
    assert ("UNDRAWN", "poly", "tools") in got


def test_poly_quiet_cases(poly_map):
    fs = fresh.compute(poly_map, None)
    ids = {(f.code, f.id) for f in fs}
    assert not any(c == "UNDOC" and ("Circle::area" in i or "REQ_GEO_001" in i) for c, i in ids)
    assert not any(f.code == "DEADLINK" and "util_sum" in f.action for f in fs)
    assert not any(c == "ICDSYM" and i in ("area", "make") for c, i in ids)
    assert not any(c == "DIAGNODE" and i == "OP" for c, i in ids)
    assert not any(c == "UNDRAWN" and i in ("core", "svc", "web", "proto") for c, i in ids)
    assert not any(f.module == "thirdparty" or "vendor/" in " ".join(f.files) for f in fs)
    assert not any(c == "UNDOC" and i == "broken" and f.action.startswith("add a module docstring")
                   for f in fs for c, i in [(f.code, f.id)])          # broken.py has one; it just does not parse
    assert [f.id for f in fs if f.code == "DOCSIG"] == ["Engine.run"]

"""WP1 acceptance: golden extraction per poly fixture file, skips, hashes, example files."""
from __future__ import annotations

import random
import time
from pathlib import Path

import pytest

import importlib

from wikimap.lang.extract import ADAPTER_VERSION, LANG_BY_EXT, extract, lang_of

POLY = Path(__file__).resolve().parents[1] / "fixtures" / "poly"
EXAMPLE = Path(__file__).resolve().parents[6] / "example" / "weather-station"

RESULT_KEYS = {"lang", "ok", "conf", "skip", "file_doc", "symbols", "calls", "imports", "refs", "strings",
               "reqs", "mentions", "errors"}
SYMBOL_KEYS = {"qual", "name", "kind", "line", "end", "sig", "params", "arity", "decl", "pub", "parent", "bases",
               "virtual", "pure", "override", "static", "members", "doc", "sig_hash", "body_hash", "test", "words",
               "ignore"}
DOC_KEYS = {"style", "brief", "text", "params", "explicit_params", "returns", "raises", "see", "deprecated",
            "line", "end", "hash"}


def fx(rel: str) -> dict:
    return extract(rel, (POLY / rel).read_bytes())


def src(rel: str, text: str, cfg: dict | None = None) -> dict:
    return extract(rel, text.encode("utf-8"), cfg)


def sym(r: dict, qual: str) -> dict:
    hits = [s for s in r["symbols"] if s["qual"] == qual]
    assert hits, f"{qual} not in {[s['qual'] for s in r['symbols']]}"
    return hits[0]


def quals(r: dict) -> list[str]:
    return [s["qual"] for s in r["symbols"]]


def calls_from(r: dict, owner: str) -> list[tuple]:
    return [(c["name"], c["recv"], c["recv_type"], c["kind"]) for c in r["calls"] if c["from"] == owner]


def brief(s: dict) -> str | None:
    return s["doc"]["brief"] if s["doc"] else None


def check_shape(r: dict) -> None:
    assert set(r) - {"default_export"} == RESULT_KEYS  # JS/TS may add the default-export qual
    for s in r["symbols"]:
        assert set(s) == SYMBOL_KEYS, s["qual"]
        assert len(s["sig_hash"]) == 12 and len(s["body_hash"]) == 12
        assert s["line"] <= s["end"]
        if s["doc"]:
            assert set(s["doc"]) == DOC_KEYS
            assert len(s["doc"]["hash"]) == 12
    for c in r["calls"]:
        assert set(c) == {"from", "name", "recv", "recv_type", "line", "kind"}
    for m in r["imports"]:
        assert set(m) == {"target", "names", "alias", "line", "kind", "level", "system"}


ALL_CODE = sorted(p.relative_to(POLY).as_posix() for p in POLY.rglob("*")
                  if p.is_file() and lang_of(p.name) is not None)


# --- contract -------------------------------------------------------------------------

def test_lang_table():
    assert ADAPTER_VERSION == "2"
    expect = {"a.py": "python", "a.c": "c", "a.h": "c", "a.cc": "cpp", "a.cpp": "cpp", "a.cxx": "cpp",
              "a.hpp": "cpp", "a.hh": "cpp", "a.hxx": "cpp", "a.ino": "cpp", "a.js": "js", "a.mjs": "js",
              "a.cjs": "js", "a.jsx": "js", "a.ts": "ts", "a.tsx": "ts", "a.mts": "ts", "a.go": "go",
              "a.rs": "rust", "a.java": "clike", "a.kt": "clike", "a.cs": "clike", "a.swift": "clike",
              "a.proto": "proto", "a.sql": "sql", "a.sh": "shell", "a.bash": "shell"}
    for rel, lang in expect.items():
        assert lang_of(rel) == lang, rel
        assert LANG_BY_EXT[rel[1:]] == lang
    assert lang_of("dir.py/README.md") is None
    assert lang_of("Makefile") is None
    assert lang_of("x/Y.CPP") == "cpp"


def test_dot_h_upgrades_to_cpp_on_cpp_syntax():
    assert src("a.h", "int f(int x);\n")["lang"] == "c"
    assert src("a.h", "namespace n { int f(); }\n")["lang"] == "cpp"
    assert src("a.h", "#include <iostream>\nint f();\n")["lang"] == "cpp"
    assert fx("core/c/include/util.h")["lang"] == "c"


@pytest.mark.parametrize("rel", ALL_CODE)
def test_every_fixture_file_has_contract_shape(rel):
    r = fx(rel)
    check_shape(r)
    assert r["skip"] is None
    if rel != "svc/pkg/src/broken.py":
        assert r["ok"] and r["conf"] == "high", (rel, r["errors"])


@pytest.mark.parametrize("rel", ALL_CODE)
def test_never_raises_on_mangled_input(rel):
    data = (POLY / rel).read_bytes()
    rnd = random.Random(rel)
    variants = [data[: len(data) // 2], data[len(data) // 3:], data.replace(b"}", b"", 1),
                data.replace(b")", b"(", 2), data + b"\n/* unterminated", data + b'\n"unterminated',
                bytes(rnd.choice(b"{}()[]<>;:'\"/*#\\\nabc ") for _ in range(400))]
    for v in variants:
        r = extract(rel, v)
        check_shape(r)


def test_unknown_language_returns_empty_result():
    r = src("notes.txt", "def f(): pass\n")
    assert r["lang"] is None and r["symbols"] == [] and r["skip"] is None


# --- skips ----------------------------------------------------------------------------

def test_generated_files(poly):
    t0 = time.perf_counter()
    r = extract("extra/src/long.c", (poly / "extra/src/long.c").read_bytes())
    assert time.perf_counter() - t0 < 1.0
    assert r["ok"] and r["conf"] == "high"
    assert len(r["symbols"]) == 1000
    assert sym(r, "f999")["line"] == 5995
    b = extract("extra/src/blob.bin", (poly / "extra/src/blob.bin").read_bytes())
    assert b["lang"] is None  # unknown extension: not even read
    b = extract("extra/src/blob.c", (poly / "extra/src/blob.bin").read_bytes())
    assert b["skip"] == "binary" and b["symbols"] == [] and b["calls"] == []


def test_skip_reasons():
    assert extract("a.c", b"int f(void);\n\x00rest")["skip"] == "binary"
    assert extract("a.c", b"int f(void) { return '\xff'; }\n")["skip"] == "binary"  # not UTF-8
    assert extract("a.c", b"\xef\xbb\xbfint f(void) { return 0; }\n")["skip"] is None  # BOM stripped
    assert extract("a.c", b"int x;\n" * 200000)["skip"] == "size"
    r = extract("a.js", b"var a=1;" * 80 + b"\nfunction f() {}\n")
    assert r["skip"] == "minified" and r["symbols"] == []
    assert extract("a.js", b"\n" * 25 + b"var a=1;" * 80 + b"\n")["skip"] is None  # only the first 20 lines


# --- C ----------------------------------------------------------------------------------

def test_util_h_golden():
    r = fx("core/c/include/util.h")
    got = [(s["qual"], s["kind"], s["line"], s["pub"], s["decl"]) for s in r["symbols"]]
    assert got == [
        ("UTIL_MAX", "macro", 11, True, False),
        ("UTIL_CLAMP", "macro", 14, True, False),
        ("util_acc", "struct", 19, True, False),
        ("util_fn", "type", 25, True, False),
        ("util_round", "enum", 28, True, False),
        ("util_sum", "function", 36, True, True),
        ("util_avg", "function", 42, True, True),
        ("util_map", "function", 45, True, True),
        ("util_calls", "function", 48, True, True),
    ]
    assert r["file_doc"]["brief"] == "Small numeric helpers shared by the core modules."
    assert brief(sym(r, "UTIL_MAX")) == "Maximum number of samples a buffer holds."
    assert sym(r, "UTIL_CLAMP")["params"] == ["v", "lo", "hi"]
    acc = sym(r, "util_acc")
    assert acc["members"] == {"total": "long", "count": "int"} and acc["end"] == 22
    s = sym(r, "util_sum")
    assert s["params"] == ["values", "n"] and s["arity"] == 2
    assert s["doc"]["style"] == "doxygen" and s["doc"]["explicit_params"]
    assert s["doc"]["params"] == {"values": "pointer to the samples", "n": "number of samples to read"}
    assert s["doc"]["returns"].startswith("the sum")
    a = sym(r, "util_avg")
    assert a["doc"]["brief"] == "Average of the first n values, rounded per mode."
    assert set(a["doc"]["params"]) == {"values", "n", "mode"}
    calls = sym(r, "util_calls")
    assert calls["doc"]["style"] == "line" and not calls["doc"]["explicit_params"]
    assert calls["params"] == [] and calls["arity"] == 0
    assert {"text": "util_sum", "style": "see", "line": 44, "from": "util_map"} in r["refs"]
    assert r["imports"] == [{"target": "stddef.h", "names": [], "alias": None, "line": 8, "kind": "include",
                             "level": 0, "system": True}]


def test_util_c_golden():
    r = fx("core/c/src/util.c")
    assert quals(r) == ["abs_i", "util_sum", "util_avg", "util_map", "util_calls"]
    assert not any(s["pub"] for s in r["symbols"])  # .c file: never public
    assert sym(r, "abs_i")["static"]
    assert brief(sym(r, "abs_i")) == "helper: absolute value"
    assert sym(r, "util_sum")["doc"] is None and (sym(r, "util_sum")["line"], sym(r, "util_sum")["end"]) == (8, 13)
    assert brief(sym(r, "util_avg")) == "Average with explicit rounding."
    refs = [(x["text"], x["from"]) for x in r["refs"]]
    assert ("util_sum", "util_avg") in refs and ("Nowhere", "util_avg") in refs
    assert calls_from(r, "util_avg") == [("util_sum", None, None, "call")]
    assert sorted(c[0] for c in calls_from(r, "util_map")) == ["abs_i", "fn"]
    assert r["imports"][0]["target"] == "util.h" and not r["imports"][0]["system"]


def test_header_and_definition_docs_both_captured():
    h = sym(fx("core/c/include/util.h"), "util_avg")
    c = sym(fx("core/c/src/util.c"), "util_avg")
    assert h["decl"] and not c["decl"]
    assert h["doc"]["brief"] != c["doc"]["brief"]
    assert h["sig_hash"] == c["sig_hash"]  # same signature tokens in both places


def test_main_c_golden():
    r = fx("core/c/src/main.c")
    assert quals(r) == ["twice", "report", "main"]
    rep = sym(r, "report")
    assert rep["params"] == ["values", "n", "label"] and rep["arity"] == 3
    assert (rep["line"], rep["end"]) == (10, 19)
    assert "\n" not in rep["sig"]
    assert [c[0] for c in calls_from(r, "report")] == ["util_sum", "printf", "util_avg"]
    assert [c[0] for c in calls_from(r, "main")] == ["util_map", "report", "util_calls"]
    assert [(m["target"], m["system"]) for m in r["imports"]] == [("stdio.h", True), ("util.h", False)]


# --- C++ --------------------------------------------------------------------------------

def test_shape_hpp_golden():
    r = fx("core/geo/include/geo/shape.hpp")
    assert r["lang"] == "cpp"
    got = [(s["qual"], s["kind"], s["line"]) for s in r["symbols"]]
    assert got == [
        ("geo::detail::square", "function", 6),
        ("geo::Point", "struct", 10),
        ("geo::Point::norm", "method", 13),
        ("geo::Kind", "enum", 17),
        ("geo::Shape", "class", 22),
        ("geo::Shape::~Shape", "method", 24),
        ("geo::Shape::area", "method", 29),
        ("geo::Shape::name", "method", 31),
        ("geo::largest", "function", 38),
        ("geo::make", "function", 43),
    ]
    assert not sym(r, "geo::detail::square")["pub"]  # detail namespace
    assert sym(r, "geo::Point")["members"] == {"x": "double", "y": "double"}
    assert brief(sym(r, "geo::Point")) == "A point on the plane, in metres."
    area = sym(r, "geo::Shape::area")
    assert area["pure"] and area["virtual"] and area["decl"] and area["pub"]
    assert area["parent"] == "geo::Shape"
    assert area["doc"]["brief"] == "Area of the shape." and area["doc"]["returns"] == "area in square metres"
    assert sym(r, "geo::Shape")["members"] == {"origin_": "Point"}
    assert brief(sym(r, "geo::largest")) == "Largest of two values."
    assert sym(r, "geo::largest")["params"] == ["a", "b"]
    mk = sym(r, "geo::make")
    assert mk["pub"] and mk["decl"] and mk["doc"] is None and mk["params"] == ["k", "size"]
    assert calls_from(r, "geo::Point::norm") == [("detail::square", None, None, "call")] * 2


def test_circle_hpp_golden():
    r = fx("core/geo/include/geo/circle.hpp")
    c = sym(r, "geo::Circle")
    assert c["bases"] == ["Shape"] and c["members"] == {"r_": "double"}
    assert sym(r, "geo::Circle::Circle")["kind"] == "ctor"
    assert brief(sym(r, "geo::Circle::Circle")) == "Build a circle of radius @p r metres."
    area = sym(r, "geo::Circle::area")
    assert area["override"] and area["decl"] and area["pub"] and not area["pure"]
    assert r["imports"][0]["target"] == "geo/shape.hpp"


def test_circle_cpp_golden():
    r = fx("core/geo/src/circle.cpp")
    # raw string R"x(})x" does not unbalance braces; `using namespace geo;` re-qualifies Circle::
    assert quals(r) == ["(anon)::kPi", "(anon)::scale", "(anon)::kBanner", "geo::Circle::Circle",
                        "geo::Circle::area"]
    assert not any(s["pub"] for s in r["symbols"])
    area = sym(r, "geo::Circle::area")
    assert area["kind"] == "method" and area["parent"] == "geo::Circle" and not area["decl"]
    assert brief(area) == "Area of a circle: pi r squared."
    assert calls_from(r, "geo::Circle::area") == [("detail::square", None, None, "call")]
    assert calls_from(r, "geo::Circle::Circle") == [("scale", None, None, "call")]  # init list, r_ is no call
    assert {"target": "geo", "kind": "using"}.items() <= next(m for m in r["imports"] if m["kind"] == "using").items()


def test_app_cpp_golden():
    r = fx("core/geo/src/app.cpp")
    assert quals(r) == ["geo::make", "geo::operator+", "run_app"]  # `#if 0 {` dropped, ui::Point is a fwd decl
    assert r["conf"] == "high"
    assert brief(sym(r, "geo::operator+")) == "Sum of two points."
    assert calls_from(r, "geo::make") == [("Circle", None, None, "new")]
    rc = calls_from(r, "run_app")
    assert ("geo::make", None, None, "call") in rc
    assert ("area", "s", "geo::Shape", "call") in rc
    assert ("norm", "p", "geo::Point", "call") in rc


def test_test_macro_becomes_test_symbol_with_req():
    r = fx("core/geo/test/test_geo.cpp")
    t = sym(r, "Geo.REQ_GEO_001_area")
    assert t["kind"] == "test" and t["test"] and t["name"] == "Geo.REQ_GEO_001_area"
    assert brief(t) == "Verifies REQ-GEO-001: a unit circle has area pi."
    assert {"id": "REQ-GEO-001", "line": 6, "from": "Geo.REQ_GEO_001_area"} in r["reqs"]
    assert calls_from(r, "Geo.REQ_GEO_001_area")[0] == ("area", "c", "geo::Circle", "call")


def test_macro_table_extendable_and_unknown_macro_block_isolated():
    text = "MY_TEST(A, b) { f(); }\nint g(int x) { Foo y(1); auto z = Bar(2); y.run(); z.go(); return x; }\n"
    plain = src("a.cpp", text)
    assert quals(plain) == ["g"]
    assert calls_from(plain, "g") == [("Bar", None, None, "call"), ("run", "y", "Foo", "call"),
                                      ("go", "z", "Bar", "call")]
    ext = src("a.cpp", text, {"macros": {"MY_TEST": "test"}})
    assert (sym(ext, "A.b")["kind"], sym(ext, "A.b")["test"]) == ("test", True)


def test_cpp_brace_imbalance_falls_back_low_conf():
    r = src("a.cpp", "#ifdef X\nvoid f() {\n#else\nvoid f() {\n#endif\n  g();\n}\nint h() { return 1; }\n")
    assert r["conf"] == "low"
    assert "f" in quals(r) and "h" in quals(r)


def test_cpp_access_and_static_visibility():
    r = src("a.hpp", "namespace n {\nstruct S { int a(); private: int b(); };\nclass C { int c(); public: static int d(); };\n"
                     "static int e();\nnamespace { int f(); }\n}\n")
    pub = {s["qual"]: s["pub"] for s in r["symbols"]}
    assert pub["n::S::a"] and not pub["n::S::b"] and not pub["n::C::c"] and pub["n::C::d"]
    assert not pub["n::e"] and not pub["n::(anon)::f"]


def test_cpp_trailing_member_doc_and_default():
    r = src("a.hpp", "struct P {\n  int v;  ///< value\n  P() = default;\n};\n")
    assert sym(r, "P")["members"] == {"v": "int"}
    assert sym(r, "P::P")["kind"] == "ctor"


# --- Python -------------------------------------------------------------------------------

def test_core_py_golden():
    r = fx("svc/pkg/src/pkg/core.py")
    got = [(s["qual"], s["kind"], s["line"], s["pub"]) for s in r["symbols"]]
    assert got == [
        ("FIELDS", "const", 9, True),
        ("traced", "function", 13, True),
        ("traced.wrapper", "function", 17, False),
        ("Base", "class", 23, True),
        ("Base.__init__", "method", 26, False),
        ("Base.reset", "method", 29, True),
        ("Engine", "class", 33, True),
        ("Engine.__init__", "method", 40, False),
        ("Engine.run", "method", 45, True),
        ("Engine.step", "method", 59, True),
        ("Engine.version", "method", 77, True),
        ("Engine.build", "method", 86, True),
        ("Engine.ready", "method", 98, True),
        ("Engine.flush", "method", 103, True),
        ("Engine.flush.inner", "function", 106, False),
        ("Engine.drain", "method", 111, True),
        ("Store", "class", 116, True),
        ("Store.__init__", "method", 119, False),
        ("Store.add", "method", 122, True),
        ("Store.close", "method", 127, True),
    ]
    assert r["file_doc"]["brief"] == "Engine core: turns raw samples into stored rows."
    eng = sym(r, "Engine")
    assert eng["bases"] == ["Base"] and eng["members"]["store"] == "Store" and "count" in eng["members"]
    run = sym(r, "Engine.run")  # DOCSIG trap: doc names n, mode; signature has n, strict
    assert run["params"] == ["self", "n", "strict"] and run["arity"] == 2
    assert run["doc"]["style"] == "docstring" and run["doc"]["explicit_params"]
    assert list(run["doc"]["params"]) == ["n", "mode"]
    assert run["doc"]["returns"] == "Number of rows stored."
    step = sym(r, "Engine.step")  # NumPy
    assert step["doc"]["params"] == {"i": "Sample index."}
    build = sym(r, "Engine.build")  # Sphinx
    assert build["doc"]["params"] == {"store": "target store"} and build["doc"]["raises"]
    assert sym(r, "Engine.version")["static"] and "@staticmethod" in sym(r, "Engine.version")["sig"]
    assert "@classmethod" in build["sig"] and "@property" in sym(r, "Engine.ready")["sig"]
    assert sym(r, "Engine.drain")["sig"].startswith("async def drain(self, timeout")
    assert calls_from(r, "Engine.__init__")[0] == ("__init__", "super", None, "call")
    assert ("step", "self", None, "call") in calls_from(r, "Engine.run")
    assert ("add", "self.store", None, "call") in calls_from(r, "Engine.step")
    assert {"text": "traced", "style": "func", "line": 104, "from": "Engine.flush"} in r["refs"]
    assert {"kind": "sql", "value": "samples", "op": "INSERT", "line": 124, "from": "Store.add"} in r["strings"]
    assert "demo.v1.Sample" in r["mentions"]
    assert sym(r, "FIELDS")["sig"].startswith("FIELDS = (")
    assert "_LIMIT" not in quals(r) or not sym(r, "_LIMIT")["pub"]


def test_python_imports_and_levels():
    init = fx("svc/pkg/src/pkg/__init__.py")
    assert init["symbols"] == [] and init["file_doc"]["brief"].startswith("Sample processing package")
    assert [(m["target"], m["names"], m["level"]) for m in init["imports"]] == [("core", ["Engine"], 1)]
    sib = fx("svc/pkg/src/pkg/sub/sibling.py")
    assert [(m["target"], m["names"], m["level"]) for m in sib["imports"]] == [("core", ["Engine"], 2)]
    hl = fx("svc/pkg/src/pkg/sub/helpers.py")
    assert [(m["target"], m["names"], m["alias"], m["level"]) for m in hl["imports"]] == [
        ("", ["sibling"], None, 1), ("sibling", ["make_engine"], "build", 1)]
    assert calls_from(hl, "twice") == [("build", None, None, "call"), ("make_engine", "sibling", None, "call")]


def test_app_py_golden():
    r = fx("svc/pkg/src/app.py")
    assert quals(r) == ["main"]
    assert [(m["target"], m["alias"], m["kind"]) for m in r["imports"]] == [
        ("pkg.core", "c", "import"), ("pkg", None, "from")]
    mc = calls_from(r, "main")
    assert ("Engine", "c", None, "call") in mc and ("Engine", None, None, "call") in mc
    assert ("run", "eng", "c.Engine", "call") in mc
    assert any(c["from"] is None and c["name"] == "main" for c in r["calls"])  # __main__ guard


def test_evil_docstring_kept_verbatim():
    r = fx("svc/pkg/src/evil.py")
    assert "<script>alert(1)</script>" in r["file_doc"]["text"]
    d = sym(r, "render")["doc"]
    assert "<img src=x onerror=alert(1)>" in d["text"] and "<script>alert(1)</script>" in d["text"]


def test_broken_py_falls_back_to_regex():
    r = fx("svc/pkg/src/broken.py")
    assert r["ok"] is False and r["conf"] == "low"
    assert quals(r) == ["fine", "broken"]
    assert r["errors"]


def test_python_test_file():
    r = fx("svc/pkg/test/test_core.py")
    t = sym(r, "test_engine_runs")
    assert t["test"]
    assert {"id": "REQ-PKG-001", "line": 7, "from": "test_engine_runs"} in r["reqs"]
    assert ("Engine", None, None, "call") in calls_from(r, "test_engine_runs")
    assert not sym(fx("svc/pkg/src/pkg/core.py"), "Engine.run")["test"]


def test_python_all_limits_pub():
    r = src("m.py", '__all__ = ["a"]\ndef a():\n    pass\ndef b():\n    pass\n')
    assert sym(r, "a")["pub"] and not sym(r, "b")["pub"]


# --- JS / TS --------------------------------------------------------------------------------

def test_entry_ts_imports_calls_routes():
    r = fx("web/src/entry.ts")
    assert r["lang"] == "ts" and quals(r) == ["start"]
    imps = [(m["target"], m["names"], m["alias"], m["kind"]) for m in r["imports"]]
    for want in [("./math.js", ["*"], "m", "import"), ("./widget.js", ["default"], "Widget", "import"),
                 ("./widget.js", ["Base"], "B", "import"), ("./y", ["greet"], None, "import"),
                 ("node:fs", ["default"], "fs", "import"),
                 ("../../tools/fmt/src/fmt.js", ["fmt"], None, "import"),
                 ("./lib", ["helper"], None, "import"), ("./y", ["greet"], "hello", "reexport"),
                 ("./lazy", [], None, "dynamic")]:
        assert want in imps, want
    assert next(m for m in r["imports"] if m["target"] == "node:fs")["system"]
    assert not next(m for m in r["imports"] if m["target"] == "./y")["system"]
    sc = calls_from(r, "start")
    for want in [("Widget", None, None, "new"), ("mul", "m", None, "call"), ("add", "m", None, "call"),
                 ("fmt", None, None, "call"), ("render", "w", "Widget", "call"), ("later", "lazy", None, "call")]:
        assert want in sc, want
    assert {"kind": "route", "value": "/v1/latest", "op": "GET", "line": 14, "from": "start"} in r["strings"]
    assert sym(r, "start")["pub"] and brief(sym(r, "start")) == "Start the app."


def test_math_ts_golden():
    r = fx("web/src/math.ts")
    got = [(s["qual"], s["kind"], s["line"], s["pub"]) for s in r["symbols"]]
    assert got == [("mul", "function", 7, True), ("add", "function", 12, True), ("Vec", "interface", 15, True),
                   ("Num", "type", 21, True), ("Mode", "enum", 24, True), ("internal", "function", 29, False)]
    mul = sym(r, "mul")
    assert mul["doc"]["style"] == "jsdoc" and mul["doc"]["params"] == {"a": "first factor", "b": "second factor"}
    assert mul["params"] == ["a", "b"] and mul["doc"]["explicit_params"]
    assert sym(r, "add")["params"] == ["a", "b"]
    assert sym(r, "Vec")["members"] == {"x": "number", "y": "number"}
    assert {"text": "add", "style": "link", "line": 5, "from": "mul"} in r["refs"]
    assert calls_from(r, "internal") == [("mul", None, None, "call")]


def test_widget_js_golden():
    r = fx("web/src/widget.js")
    got = [(s["qual"], s["kind"], s["pub"]) for s in r["symbols"]]
    assert ("Widget", "class", True) in got
    assert ("Widget.#format", "method", False) in got
    assert ("Widget.render", "method", True) in got and ("Widget.create", "method", True) in got
    w = sym(r, "Widget")
    assert w["bases"] == ["Base"] and (w["line"], w["end"]) == (8, 42)  # regex /}/g does not close a brace
    assert sym(r, "Widget.create")["static"]
    assert ("render", "this", None, "call") in calls_from(r, "Widget.refresh")
    assert ("#format", "this", None, "call") in calls_from(r, "Widget.render")
    assert ("render", "w", "Widget", "call") in calls_from(r, "Widget.create")
    assert sym(r, "Widget.constructor")["doc"]["params"] == {"el": "mount point"}


def test_fmt_and_base_js():
    f = sym(fx("tools/fmt/src/fmt.js"), "fmt")
    assert f["pub"] and f["doc"]["params"] == {"x": "value to format"}
    assert f["doc"]["returns"].startswith("the formatted text") or "formatted" in f["doc"]["returns"]
    b = fx("web/src/base.js")
    assert quals(b) == ["Base", "Base.constructor", "Base.render"]


def test_generated_index_ts(poly):
    r = extract("web/src/lib/index.ts", (poly / "web/src/lib/index.ts").read_bytes())
    assert quals(r) == ["helper"] and sym(r, "helper")["pub"]


def test_js_test_calls_and_callbacks():
    r = src("web/t/a.test.js", 'import {x} from "./x";\ntest("REQ-WEB-001 adds", () => { expect(x(1)).toBe(2); });\n'
                               'it("works", function () { x(); });\ndescribe("g", () => { it("inner", () => {}); });\n')
    assert quals(r) == ["REQ-WEB-001 adds", "works", "inner"]  # callback functions are no symbols
    assert all(s["test"] and s["kind"] == "test" for s in r["symbols"])
    assert {"id": "REQ-WEB-001", "line": 2, "from": "REQ-WEB-001 adds"} in r["reqs"]
    assert ("x", None, None, "call") in calls_from(r, "works")


def test_js_require_and_commonjs():
    r = src("a.cjs", 'const fs = require("fs");\nconst u = require("./u");\nfunction f() { return u.go(); }\n'
                     'module.exports = { f };\n')
    assert [(m["target"], m["alias"], m["kind"]) for m in r["imports"]] == [("fs", "fs", "require"),
                                                                         ("./u", "u", "require")]
    assert sym(r, "f")["pub"]


# --- misc -----------------------------------------------------------------------------------

def test_proto_golden():
    r = fx("proto/demo.proto")
    got = [(s["qual"], s["kind"], s["line"]) for s in r["symbols"]]
    assert ("demo.v1.Sample", "message", 6) in got
    assert ("demo.v1.Feed.Push", "method", 16) in got
    assert sym(r, "demo.v1.Sample")["members"] == {"station_id": "uint32", "seq": "uint32", "value_mv": "int32",
                                                   "ts_s": "uint64"}
    assert brief(sym(r, "demo.v1.Sample")) == "One reading from a station."
    assert any(s["qual"] == "demo.v1.Feed" for s in r["symbols"])


def test_sql_golden():
    r = fx("svc/db/migrations/001.sql")
    t = sym(r, "samples")
    assert t["kind"] == "table" and t["line"] == 2
    assert list(t["members"]) == ["station_id", "seq", "value_mv", "ts_s"]


def test_go_golden():
    r = fx("extra/src/x.go")
    got = [(s["qual"], s["kind"], s["pub"]) for s in r["symbols"]]
    assert got == [("Greeter", "struct", True), ("Hello", "function", True), ("Greeter.Greet", "method", True),
                   ("helper", "function", False)]
    assert brief(sym(r, "Hello")) == "Hello says hi."
    assert sym(r, "Greeter.Greet")["end"] == 25  # backtick string with } does not close the body
    assert r["file_doc"]["brief"].startswith("Package extra")
    assert ("Hello", None, None, "call") in calls_from(r, "Greeter.Greet")
    assert [(m["target"], m["alias"]) for m in r["imports"]] == [("fmt", None), ("strings", "str")]


def test_rust_golden():
    r = fx("extra/src/lib.rs")
    add = sym(r, "add")
    assert add["pub"] and brief(add) == "Adds." and (add["line"], add["end"]) == (8, 11)
    assert not sym(r, "helper")["pub"] and sym(r, "helper")["end"] == 15
    assert sym(r, "Thing")["kind"] == "struct"
    assert ("helper", None, None, "call") in calls_from(r, "add")
    assert "Thing::show" in quals(r) and "Thing::fmt" in quals(r)


def test_shell_functions():
    r = src("a.sh", "greet() {\n  echo hi\n}\nfunction other {\n  greet\n}\n")
    assert quals(r) == ["greet", "other"] and r["calls"] == []


def test_clike_generic():
    r = src("A.java", "/** Adds. */\npublic class A {\n  public int add(int a, int b) { return helper(a) + b; }\n"
                      "  private int helper(int a) { return a; }\n}\n")
    assert r["lang"] == "clike" and r["ok"]
    assert any(s["name"] == "add" and s["pub"] for s in r["symbols"])
    assert any(s["name"] == "helper" and not s["pub"] for s in r["symbols"])


# --- comments controls ----------------------------------------------------------------------

def test_wiki_ignore_and_skip():
    r = src("a.py", "def f():  # wiki: ignore UNDOC, DOCSIG\n    pass\n\n# wiki: ignore UNDOC\ndef g():\n    pass\n"
                    "\ndef h():\n    pass\n")
    assert sym(r, "f")["ignore"] == ["UNDOC", "DOCSIG"]
    assert sym(r, "g")["ignore"] == ["UNDOC"]
    assert sym(r, "h")["ignore"] == []
    r = src("a.c", "// wiki: skip\nint f(void) { return 0; }\n")
    assert sym(r, "f")["ignore"] == ["UNDOC", "DOCSIG"]


# --- hashes ---------------------------------------------------------------------------------

CPP_FN = "/// Doc.\nint add(int a, int b) {\n  return a + b; // sum\n}\n"
PY_FN = 'def add(a, b):\n    """Doc."""\n    return a + b  # sum\n'
JS_FN = "/** Doc. */\nexport function add(a, b) {\n  return a + b; // sum\n}\n"


@pytest.mark.parametrize("rel,base,reformat,token_edit,renamed", [
    ("a.cpp", CPP_FN, "/// Doc.\nint add(int a,int b){return a+b;/* other */}\n",
     CPP_FN.replace("a + b", "a - b"), CPP_FN.replace("add", "plus")),
    ("a.py", PY_FN, 'def add(a, b):\n    """Doc."""\n\n    # explain\n    return a  +  b\n',
     PY_FN.replace("a + b", "a - b"), PY_FN.replace("add", "plus")),
    ("a.js", JS_FN, "/** Doc. */\nexport function add(a, b) { return a+b; /* c */ }\n",
     JS_FN.replace("a + b", "a - b"), JS_FN.replace("add", "plus")),
])
def test_hash_stability(rel, base, reformat, token_edit, renamed):
    def one(text):
        r = src(rel, text)
        assert len(r["symbols"]) == 1, r["symbols"]
        return r["symbols"][0]
    b = one(base)
    assert one(reformat)["body_hash"] == b["body_hash"]
    assert one(reformat)["sig_hash"] == b["sig_hash"]
    assert one(token_edit)["body_hash"] != b["body_hash"]
    assert one(token_edit)["sig_hash"] == b["sig_hash"]
    assert one(renamed)["sig_hash"] == b["sig_hash"]
    assert one(base.replace("(a, b)", "(a, c)").replace("int b", "int c"))["sig_hash"] != b["sig_hash"]
    assert one(base.replace("Doc.", "Doc  ."))["doc"]["hash"] != b["doc"]["hash"]
    assert one(base.replace("Doc.", "Other doc."))["doc"]["hash"] != b["doc"]["hash"]


def test_body_hash_keeps_string_contents():
    a = sym(src("a.py", 'def f():\n    return "x"\n'), "f")
    b = sym(src("a.py", 'def f():\n    return "y"\n'), "f")
    assert a["body_hash"] != b["body_hash"]


def test_extraction_is_deterministic():
    for rel in ALL_CODE:
        assert fx(rel) == fx(rel), rel


# --- example files (spec §9 WP1 acceptance) ------------------------------------------------

def _example(rel: str) -> dict:
    p = EXAMPLE / rel
    if not p.is_file():
        pytest.skip(f"example file {rel} missing")
    return extract(rel, p.read_bytes())


def test_example_uplink_calls_put_varint_field_five_times():
    r = _example("firmware/comms/src/uplink.cpp")
    n = [c for c in r["calls"] if c["from"] == "comms::encode_reading" and c["name"] == "put_varint_field"]
    assert len(n) == 5


def test_example_battery_monitor_member_type():
    r = _example("firmware/sensing/battery_monitor/include/battery_monitor/battery_monitor.hpp")
    bm = sym(r, "battery_monitor::BatteryMonitor")
    assert bm["members"]["adc_"] == "hal::Adc"
    assert sym(r, "battery_monitor::BatteryMonitor::sample")["decl"]


def test_example_decode_calls_varint_twice():
    r = _example("backend/ingest/src/ingest/decode.py")
    assert len([c for c in r["calls"] if c["from"] == "decode" and c["name"] == "_varint"]) == 2


def test_example_tree_extracts_cleanly():
    if not EXAMPLE.is_dir():
        pytest.skip("example missing")
    for p in sorted(EXAMPLE.rglob("*")):
        rel = p.relative_to(EXAMPLE).as_posix()
        if not p.is_file() or any(part.startswith(".") for part in rel.split("/")) or lang_of(rel) is None:
            continue
        r = extract(rel, p.read_bytes())
        check_shape(r)
        assert r["ok"] and r["conf"] == "high", (rel, r["errors"])


def test_module_api_reexports():
    import wikimap.lang as lang
    mod = importlib.import_module("wikimap.lang.extract")
    assert lang.extract is extract and lang.lang_of is lang_of and mod.ADAPTER_VERSION == lang.ADAPTER_VERSION


def test_python_fallback_scanner_is_linear_on_long_dotted_lines():
    import time
    text = "def ok():\n    return 1\n" + "x = 1\n" * 21 + "y = " + "a." * 100000 + "\ndef broken(:\n    x.y.z(1)\n"
    t = time.perf_counter()
    r = extract("pkg/gen.py", text.encode())
    assert time.perf_counter() - t < 1.0
    assert r["ok"] is False and {(c["recv"], c["name"]) for c in r["calls"]} == {("x.y", "z")}

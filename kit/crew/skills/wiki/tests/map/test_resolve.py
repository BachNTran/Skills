"""Resolution rules (spec §5) on the example, the poly fixture and small synthetic repos."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import EXAMPLE_SRC, make_poly
from wikimap import build_map

UPLINK = "firmware/comms/src/uplink.cpp"
BATMON = "firmware/sensing/battery_monitor"
ADC_READ = "firmware/ports/hal_ports/include/hal/adc.hpp#hal::Adc::read_mv"


@pytest.fixture(scope="module")
def ex(tmp_path_factory):
    if not EXAMPLE_SRC.is_dir():
        pytest.skip("example/weather-station missing")
    base = tmp_path_factory.mktemp("ex")
    root = base / "weather-station"
    shutil.copytree(EXAMPLE_SRC, root, ignore=shutil.ignore_patterns(".wiki", ".wikimap", "__pycache__"))
    return build_map(root, base / "data", exact=True)


@pytest.fixture(scope="module")
def pm(tmp_path_factory):
    base = tmp_path_factory.mktemp("poly")
    return build_map(make_poly(base / "poly"), base / "data", exact=True)


def edge(m, s, t, k="call"):
    hits = [e for e in m.edges if e["s"] == s and e["t"] == t and e["k"] == k]
    assert hits, f"no {k} edge {s} -> {t}"
    return hits[0]


def edges_from(m, s, k="call"):
    return {e["t"]: e for e in m.edges if e["s"] == s and e["k"] == k}


# ---------- example acceptance ----------

def test_encode_reading_calls_put_varint_field_five_times(ex):
    e = edge(ex, f"{UPLINK}#comms::encode_reading", f"{UPLINK}#comms::(anon)::put_varint_field")
    assert e["why"] == "file" and e["w"] == 5 and e["conf"] == 0.85


def test_sample_reaches_update_brownout_through_the_header(ex):
    sample = f"{BATMON}/src/battery_monitor.cpp#battery_monitor::BatteryMonitor::sample"
    target = f"{BATMON}/src/brownout.cpp#battery_monitor::BatteryMonitor::update_brownout"
    e = edge(ex, sample, target)
    assert e["why"] == "self" and e["conf"] == 0.9
    t = ex.nodes[target]
    assert t["decl"] == [f"{BATMON}/include/battery_monitor/battery_monitor.hpp", 21]
    assert t["key"] == f"cpp:{BATMON}:battery_monitor::BatteryMonitor::update_brownout~1"


def test_member_type_and_virtual_dispatch(ex):
    sample = f"{BATMON}/src/battery_monitor.cpp#battery_monitor::BatteryMonitor::sample"
    e = edge(ex, sample, ADC_READ)
    assert e["why"] == "member-type" and e["conf"] == 0.85
    impls = ex.nodes[ADC_READ]["impls"]
    assert "firmware/adapters/hal_linux_sim/src/file_adc.cpp#hal_linux_sim::FileAdc::read_mv" in impls
    assert "firmware/ports/hal_ports/fakes/fake_adc.hpp#FakeAdc::read_mv" in impls
    edge(ex, "firmware/ports/hal_ports/fakes/fake_adc.hpp#FakeAdc",
         "firmware/ports/hal_ports/include/hal/adc.hpp#hal::Adc", "inherit")


def test_decode_calls_varint_twice(ex):
    d = "backend/ingest/src/ingest/decode.py"
    e = edge(ex, f"{d}#decode", f"{d}#_varint")
    assert e["w"] == 2 and e["why"] == "file"


def test_storage_guard_tick_calls_recorder_stop(ex):
    e = edge(ex, "firmware/storage/src/storage_guard.cpp#storage::StorageGuard::tick",
             "firmware/storage/recorder/src/recorder.cpp#recorder::Recorder::stop")
    assert e["conf"] >= 0.8 and e["why"] == "member-type"


def test_contracts_and_data(ex):
    msg = "protocol/weather.proto#weather.v1.Reading"
    for src in ("firmware/comms/include/comms/uplink.hpp", "backend/ingest/src/ingest/decode.py"):
        e = edge(ex, src, msg, "contract")
        assert e["conf"] == 0.6 and e["why"] == "mention"
    e = edge(ex, "firmware/comms/include/comms/uplink.hpp#comms::Reading", msg, "contract")
    assert e["why"] == "fields"
    e = edge(ex, "backend/ingest/src/ingest/store.py#Store.add",
             "backend/telemetry_db/migrations/001_init.sql#readings", "data")
    assert e["conf"] == 0.8 and e["why"] == "sqlname"


def test_includes_through_deps_closure_and_basename(ex):
    e = edge(ex, f"{BATMON}/include/battery_monitor/battery_monitor.hpp",
             "firmware/ports/hal_ports/include/hal/adc.hpp", "import")
    assert e["why"] == "include" and e["conf"] == 0.8
    gt = [e for e in ex.edges if e["k"] == "import" and e["t"].endswith("gtest_shim/gtest/gtest.h")
          and not e["s"].startswith("firmware/targets/")]  # <gtest/gtest.h> from other modules
    assert gt and all(e["why"] == "basename" and e["conf"] == 0.6 for e in gt)


def test_declaration_definition_merge(ex):
    sample = ex.nodes[f"{BATMON}/src/battery_monitor.cpp#battery_monitor::BatteryMonitor::sample"]
    assert sample["src"][0] == f"{BATMON}/src/battery_monitor.cpp"
    assert sample["decl"][0].endswith("battery_monitor.hpp")
    assert sample["doc_src"] == "decl" and sample["doc"]["brief"].startswith("Call every 100 ms")
    assert sample["pub"] is True  # from the public header declaration
    assert sample["name"] == "BatteryMonitor::sample"  # out-of-line: child of the .cpp file
    assert sample["parent"] == f"{BATMON}/src/battery_monitor.cpp"
    hdr = f"{BATMON}/include/battery_monitor/battery_monitor.hpp"
    assert f"{hdr}#battery_monitor::BatteryMonitor::sample" not in ex.nodes  # merged away
    assert ex.nodes[f"{hdr}#battery_monitor::BatteryMonitor"]["kind"] == "class"  # classes stay in headers
    pure = ex.nodes[ADC_READ]  # declaration without definition lives in its header
    assert pure["decl"] is None and pure["src"][0].endswith("hal/adc.hpp")


# ---------- poly fixture ----------

def test_poly_virtual_call_through_base_pointer(pm):
    area = "core/geo/include/geo/shape.hpp#geo::Shape::area"
    e = edge(pm, "core/geo/src/app.cpp#run_app", area)
    assert e["why"] == "member-type"
    assert pm.nodes[area]["impls"] == ["core/geo/src/circle.cpp#geo::Circle::area"]
    edge(pm, "core/geo/include/geo/circle.hpp#geo::Circle", "core/geo/include/geo/shape.hpp#geo::Shape", "inherit")


def test_poly_python_imports(pm):
    core = "svc/pkg/src/pkg/core.py"
    e = edge(pm, "svc/pkg/src/app.py#main", f"{core}#Engine")  # import pkg.core as c; c.Engine()
    assert e["why"] == "import" and e["conf"] == 0.8
    e = edge(pm, "svc/pkg/src/pkg/sub/sibling.py#make_engine", f"{core}#Engine")  # from ..core import Engine
    assert e["why"] == "import"
    edge(pm, "svc/pkg/src/pkg/sub/sibling.py", core, "import")
    edge(pm, "svc/pkg/src/pkg/sub/helpers.py", "svc/pkg/src/pkg/sub/sibling.py", "import")  # from . import sibling
    edge(pm, "svc/pkg/test/test_core.py", core, "import")  # pyproject pythonpath = ["src"]
    assert edge(pm, f"{core}#Engine.run", f"{core}#Engine.step")["why"] == "self"
    assert edge(pm, f"{core}#Engine.step", f"{core}#Store.add")["why"] == "member-type"  # self.store: Store
    assert edge(pm, f"{core}#Engine.__init__", f"{core}#Base.__init__")["why"] == "self"  # super().__init__()
    assert edge(pm, "svc/pkg/src/app.py#main", f"{core}#Engine.run")["why"] == "member-type"  # eng: c.Engine


def test_poly_js_imports(pm):
    edge(pm, "web/src/entry.ts", "web/src/math.ts", "import")  # './math.js' resolves to math.ts
    edge(pm, "web/src/entry.ts", "web/src/lib/index.ts", "import")  # './lib' probes /index.ts
    assert edge(pm, "web/src/entry.ts#start", "web/src/math.ts#mul")["why"] == "import"  # m.mul via * as m
    assert edge(pm, "web/src/entry.ts#start", "web/src/widget.js#Widget")["why"] == "import"  # default import
    assert edge(pm, "web/src/entry.ts#start", "web/src/widget.js#Widget.render")["why"] == "member-type"
    assert edge(pm, "web/src/widget.js#Widget.refresh", "web/src/widget.js#Widget.render")["why"] == "self"
    e = edge(pm, "web/src/entry.ts", "tools/fmt/src/fmt.js", "import")
    assert e["x"] is True  # web does not depend on fmt: XCALL edge
    assert not any(e["t"].startswith("node:") for e in pm.edges)


def test_poly_c_and_data(pm):
    edge(pm, "core/c/src/main.c", "core/c/include/util.h", "import")
    assert edge(pm, "core/c/src/main.c#report", "core/c/src/util.c#util_sum")["why"] == "import"
    assert edge(pm, "core/geo/src/circle.cpp#geo::Circle::area",
                "core/geo/include/geo/shape.hpp#geo::detail::square")["why"] == "import"
    edge(pm, "svc/pkg/src/pkg/core.py#Store.add", "svc/db/migrations/001.sql#samples", "data")
    edge(pm, "svc/pkg/src/pkg/core.py", "proto/demo.proto#demo.v1.Sample", "contract")


def test_poly_vendor_and_hidden_not_extracted(pm):
    assert not any(r.startswith(("vendor/thirdparty/", ".hidden/")) for r in pm.files)
    assert not any(n.startswith(("vendor/thirdparty/lib.c#", ".hidden")) for n in pm.nodes)
    assert pm.nodes["vendor"]["vendor"] is True


# ---------- synthetic repos ----------

def write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def _ambig_repo(root: Path, n: int) -> Path:
    files = {"main.py": "from helper import nothing\n\ndef run():\n    return work()\n"}
    for i in range(n):
        files[f"m{i}/w{i}.py"] = "def work():\n    return 1\n"
    return write(root, files)


def test_ambiguous_capped_at_five(tmp_path):
    m = build_map(_ambig_repo(tmp_path / "three", 3), tmp_path / "d3", exact=True)
    hits = edges_from(m, "main.py#run")
    assert len(hits) == 3 and all(e["why"] == "ambiguous" and e["conf"] == 0.1 for e in hits.values())
    m = build_map(_ambig_repo(tmp_path / "six", 6), tmp_path / "d6", exact=True)
    assert edges_from(m, "main.py#run") == {}
    assert m.stats["unresolved"] >= 1


def test_unique_and_method_name_rules(tmp_path):
    root = write(tmp_path / "r", {
        "a/pyproject.toml": "", "b/pyproject.toml": "",
        "a/lib.py": "class Pump:\n    def prime(self):\n        return 1\n\ndef solo():\n    return 2\n",
        "b/use.py": "def go(x):\n    x.prime()\n    return solo()\n",
    })
    m = build_map(root, tmp_path / "d", exact=True)
    out = edges_from(m, "b/use.py#go")
    assert out["a/lib.py#solo"]["why"] == "unique" and out["a/lib.py#solo"]["conf"] == 0.5
    assert out["a/lib.py#Pump.prime"]["why"] == "method-name" and out["a/lib.py#Pump.prime"]["conf"] == 0.4


def test_broken_file_halves_call_confidence(tmp_path):
    root = write(tmp_path / "r", {"x.py": "def a():\n    return b()\n\ndef b():\n    return 1\n\ndef (:\n"})
    m = build_map(root, tmp_path / "d", exact=True)
    assert m.files["x.py"]["rec"]["ok"] is False
    for e in m.edges:
        if e["k"] == "call":
            assert e["conf"] <= 0.45


def test_overloads_get_arity_suffix(tmp_path):
    root = write(tmp_path / "r", {"o.cpp": "int f(int a) { return a; }\nint f(int a, int b) { return a + b; }\n"
                                         "int g() { return f(1) + f(1, 2); }\n"})
    m = build_map(root, tmp_path / "d", exact=True)
    assert "o.cpp#f~1" in m.nodes and "o.cpp#f~2" in m.nodes and "o.cpp#g" in m.nodes


# ---------- regressions from review ----------

def _calls(root: Path, tmp_path: Path, files: dict[str, str]):
    m = build_map(write(root, files), tmp_path / ("d-" + root.name), exact=True)
    return m, {(e["s"], e["t"]): e for e in m.edges if e["k"] == "call"}


def test_cpp_qualified_static_method_call(tmp_path):
    m, calls = _calls(tmp_path / "q", tmp_path, {
        "include/w.hpp": "namespace ui { class Widget { public: static Widget* create(); };"
                         " class Other { public: static Other* create(); }; }\n",
        "src/w.cpp": '#include "../include/w.hpp"\nnamespace ui { Widget* Widget::create(){ return nullptr; }'
                     " Other* Other::create(){ return nullptr; } }\n",
        "src/main.cpp": '#include "../include/w.hpp"\nint main(){ auto* w = ui::Widget::create(); }\n'
                        "void h(){ using namespace ui; Widget::create(); }\n"})
    for f in ("main", "h"):
        e = calls[(f"src/main.cpp#{f}", "src/w.cpp#ui::Widget::create")]
        assert e["why"] == "qual" and e["conf"] == 0.8
    assert not any(t.endswith("Other::create") for s, t in calls if s.startswith("src/main.cpp"))


def test_expression_receivers_never_bind_to_free_functions(tmp_path):
    m, calls = _calls(tmp_path / "x", tmp_path, {
        "src/svc.py": 'def join(x): pass\ndef add(x): pass\ndef get_list(): return []\nclass Svc:\n'
                      '    def run(self, parts, t):\n        ", ".join(parts)\n        get_list().add(t)\n',
        "src/app.js": 'function map(){}\nfunction render(){}\nfunction getView(){}\n'
                      'export function main(f){ [1,2].map(f); getView().render(); }\n',
        "src/dev.cpp": "struct Adc { int read(); };\nAdc& adc();\nint read(){return 0;}\n"
                       "struct Dev { int read(){return 1;} void poll(){ adc().read(); } };\n"})
    bad = [(s, t) for (s, t), e in calls.items() if e["conf"] >= 0.5
           and t.rsplit("#", 1)[-1] in ("join", "add", "map", "render", "read", "Dev::read")]
    assert bad == []


def test_cpp_global_scope_call_is_not_a_member_call(tmp_path):
    m, calls = _calls(tmp_path / "g", tmp_path, {
        "src/file.cpp": "struct File { int fd_; void close(){ ::close(fd_); } void reset(){ ::close(fd_); }"
                        " long read(char*b,long n){ return ::read(fd_,b,n); } };\n"})
    assert calls == {}
    names = {c["name"] for c in m.files["src/file.cpp"]["rec"]["calls"]}
    assert names == {"::close", "::read"}


def test_cpp_make_unique_gives_the_receiver_type(tmp_path):
    m, calls = _calls(tmp_path / "mu", tmp_path, {
        "src/a.cpp": "struct Circle{void draw(){}};\nstruct Square{void paint(){}};\n"
                     "void a(){ auto p = std::make_unique<Circle>(3); p->draw(); }\n"
                     "void b(){ auto q = std::make_shared<Square>(); q->paint(); }\n"})
    assert calls[("src/a.cpp#a", "src/a.cpp#Circle::draw")]["why"] == "member-type"
    assert calls[("src/a.cpp#b", "src/a.cpp#Square::paint")]["why"] == "member-type"


def test_pascal_namespace_definition_stays_a_function(tmp_path):
    m, calls = _calls(tmp_path / "geo", tmp_path, {
        "include/geo.hpp": "namespace Geo { int area(int r); }\n",
        "src/geo.cpp": '#include "../include/geo.hpp"\nint Geo::area(int r){ return r; }\n',
        "src/main.cpp": '#include "../include/geo.hpp"\nint main(){ return Geo::area(2); }\n'})
    assert m.nodes["src/geo.cpp#Geo::area"]["kind"] == "function"
    assert ("src/main.cpp#main", "src/geo.cpp#Geo::area") in calls


def test_ts_constructor_parameter_properties_are_typed_members(tmp_path):
    m, calls = _calls(tmp_path / "di", tmp_path, {
        "web/store.ts": "export class Store { put(x){} }\nexport class Other { put(x){} }\n",
        "web/svc.ts": 'import { Store } from "./store";\nexport class Svc {'
                      " constructor(private readonly store: Store, public name: string) {} run(){ this.store.put(2); } }\n"})
    out = {t: e for (s, t), e in calls.items() if s == "web/svc.ts#Svc.run"}
    assert set(out) == {"web/store.ts#Store.put"} and out["web/store.ts#Store.put"]["why"] == "member-type"


def test_static_call_on_a_same_file_class(tmp_path):
    m, calls = _calls(tmp_path / "sf", tmp_path, {
        "pkg/m.py": "class A:\n    @classmethod\n    def make(cls): pass\nclass B:\n    def make(self): pass\n"
                    "def run():\n    return A.make()\n",
        "web/m.js": "class A{static make(){}} class B{make(){}} export function run(){ return A.make(); }\n"})
    for f, a in (("pkg/m.py", "A.make"), ("web/m.js", "A.make")):
        out = {t: e for (s, t), e in calls.items() if s == f"{f}#run"}
        assert set(out) == {f"{f}#{a}"} and out[f"{f}#{a}"]["why"] == "file"


def test_js_default_import_follows_the_marked_default_export(tmp_path):
    m, calls = _calls(tmp_path / "jd", tmp_path, {
        "w/lib.ts": "export default function mkDef(){}\nexport function bar(){}\nexport function qux(){}\n",
        "w/main.js": 'import Def from "./lib.js";\nexport function run(){ Def(); }\n',
        "v/lib.ts": "export function other(){}\nexport default (() => 1);\n",
        "v/main.js": 'import Def from "./lib.js";\nexport function run(){ Def(); }\n'})
    assert ("w/main.js#run", "w/lib.ts#mkDef") in calls
    assert not any(s == "v/main.js#run" for s, _ in calls)


def test_commonjs_namespace_require_and_destructured_rename(tmp_path):
    m, calls = _calls(tmp_path / "cj", tmp_path, {
        "src/cj.js": "function req1(){}\nfunction req2(){}\nmodule.exports = { req1, req2 };\n",
        "src/main.js": 'const cj = require("./cj");\nconst { req2: r2 } = require("./cj");\n'
                       "function useA(){ cj.req1(); }\nfunction useB(){ r2(); }\n"})
    assert ("src/main.js#useA", "src/cj.js#req1") in calls
    assert ("src/main.js#useB", "src/cj.js#req2") in calls


def test_relational_expression_is_not_a_generic_call(tmp_path):
    m, calls = _calls(tmp_path / "rl", tmp_path, {
        "src/b.cpp": "struct Buf { int size() const; bool fits(int size,int cap,int n) const"
                     " { return size < cap && n > (cap - 1); } };\n",
        "src/a.js": "function lo(){} function f(x,z,y){ return lo < x && z > (y + 1); }\n"})
    assert calls == {}


def test_base_class_through_a_submodule_binding_does_not_crash(tmp_path):
    m, _ = _calls(tmp_path / "sub", tmp_path, {
        "pkg/__init__.py": "from . import sub\n", "pkg/sub.py": "class Base:\n    pass\n",
        "app.py": "import pkg\n\nclass K(pkg.sub):\n    pass\n\nclass L(pkg.sub.Base):\n    pass\n"})
    assert "app.py#K" in m.nodes

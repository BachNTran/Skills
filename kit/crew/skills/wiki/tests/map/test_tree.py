"""wikimap.tree: hierarchy (§2.3), module docs, config, and Mermaid node matching (§4.3)."""
import hashlib
import json
import os
import shutil
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[2] / "scripts"
FIXTURE = HERE.parents[1] / "fixtures" / "poly"
EXAMPLE = HERE.parents[6] / "example" / "weather-station"


def _load():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    try:
        from wikimap import tree
    except Exception:  # package __init__ may be mid-build elsewhere: load the package shell without running it
        for k in [k for k in sys.modules if k == "wikimap" or k.startswith("wikimap.")]:
            del sys.modules[k]
        pkg = types.ModuleType("wikimap")
        pkg.__path__ = [str(SCRIPTS / "wikimap")]
        sys.modules["wikimap"] = pkg
        from wikimap import tree
    return tree


T = _load()

# Code files the extractor package owns in the fixture; stubbed in the tmp copy only when absent there.
CODE_STUBS = [
    "core/c/include/util.h", "core/c/src/util.c", "core/c/src/main.c", "core/geo/include/geo/shape.hpp",
    "core/geo/include/geo/circle.hpp", "core/geo/src/circle.cpp", "core/geo/src/app.cpp",
    "core/geo/test/test_geo.cpp", "svc/pkg/pyproject.toml", "svc/pkg/src/pkg/__init__.py", "svc/pkg/src/pkg/core.py",
    "svc/pkg/src/pkg/sub/__init__.py", "svc/pkg/src/pkg/sub/sibling.py", "svc/pkg/src/pkg/sub/helpers.py",
    "svc/pkg/src/app.py", "svc/pkg/src/evil.py", "svc/pkg/src/broken.py", "svc/pkg/test/test_core.py",
    "svc/db/migrations/001.sql", "web/package.json", "web/src/math.ts", "web/src/base.js", "web/src/widget.js",
    "web/src/entry.ts", "web/src/y.ts", "web/src/lazy.ts", "proto/demo.proto", "tools/fmt/src/fmt.js",
    "extra/src/x.go", "extra/src/lib.rs", "vendor/thirdparty/lib.c", ".hidden/ignored.py",
]
SKIP = shutil.ignore_patterns(".wiki", ".wikimap", ".modgate", "__pycache__")


def _write(root: Path, rel: str, text: str = "x\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _copy_poly(dst: Path) -> Path:
    shutil.copytree(FIXTURE, dst, ignore=SKIP)
    for rel in CODE_STUBS:
        if not (dst / rel).exists():
            _write(dst, rel, "{}\n" if rel.endswith(".json") else "\n")
    return dst


@pytest.fixture(scope="module")
def example_tree(tmp_path_factory):
    root = tmp_path_factory.mktemp("ex") / "weather-station"
    shutil.copytree(EXAMPLE, root, ignore=SKIP)
    return T.load_tree(root, modgate=True)


@pytest.fixture()
def poly_repo(tmp_path):
    return _copy_poly(tmp_path / "poly")


@pytest.fixture()
def plain_repo(tmp_path):
    root = _copy_poly(tmp_path / "plain")
    (root / "modgate.yaml").unlink()
    (root / "poly.md").unlink()
    for p in sorted(root.rglob("*.md")):
        if p.stem == p.parent.name:
            p.unlink()
    for d in sorted(root.rglob("docs"), reverse=True):
        if d.is_dir():
            shutil.rmtree(d)
    _write(root, "README.md", "# Plain poly\n\nPlain-mode fixture.\n\n## Architecture\n```mermaid\nflowchart LR\n"
                              "  WEB[\"web\"] --> PKG[\"svc/pkg\"]\n  PKG --> DB[\"db\"]\n```\n")
    _write(root, "svc/README.md", "# Service\n\nThe service group.\n")
    return root


def _ids(tree, type_):
    return {i for i, n in tree["nodes"].items() if n["type"] == type_}


def _walk_hash(root: Path) -> dict:
    out = {}
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = Path(dp, f)
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ---------- find_root / load_config ----------

def test_find_root(tmp_path):
    mg = tmp_path / "mg"
    _write(mg, "modgate.yaml", "project: mg\n")
    _write(mg, "a/b/c.py")
    assert T.find_root(mg / "a" / "b") == (mg.resolve(), True)
    assert T.find_root(mg / "a" / "b" / "c.py") == (mg.resolve(), True)
    git = tmp_path / "g"
    (git / ".git").mkdir(parents=True)
    (git / "x" / "y").mkdir(parents=True)
    found, modgate = T.find_root(git / "x" / "y")
    assert (found, modgate) == (git.resolve(), False)


def test_load_config(tmp_path):
    assert T.load_config(tmp_path) == T.DEFAULT_CONFIG
    _write(tmp_path, ".wikimap/config.json", json.dumps({"ignore": ["gen/*"], "violations": ["XCALL"],
                                                          "max_hook_lines": 5, "macros": {"MY_TEST": "test"}}))
    cfg = T.load_config(tmp_path)
    assert cfg["ignore"] == ["gen/*"] and cfg["violations"] == ["XCALL"] and cfg["max_hook_lines"] == 5
    assert cfg["undoc"] == "public" and cfg["macros"] == {"MY_TEST": "test"}
    for bad in ("{not json", "[1, 2]", json.dumps({"ignore": "x"}), json.dumps({"undoc": "maybe"})):
        _write(tmp_path, ".wikimap/config.json", bad)
        with pytest.raises(T.ConfigError):
            T.load_config(tmp_path)


# ---------- the example (acceptance) ----------

EXAMPLE_MODULES = {
    "weather-station", "firmware", "sensing", "battery_monitor", "humidity_sensor", "study_adc_noise_floor",
    "storage", "recorder", "sd_storage", "comms", "hal_ports", "osal_ports", "hal_linux_sim", "osal_posix",
    "linux-sim", "backend", "ingest", "telemetry_db", "dashboard", "prod", "probe_access", "protocol"}


def test_example_modules_and_groups(example_tree):
    t = example_tree
    assert len(t["modules"]) == 22 and set(t["modules"]) == EXAMPLE_MODULES
    assert _ids(t, "group") == {"firmware/ports", "firmware/adapters", "firmware/targets", "deploy", "host"}
    assert t["modgate"] is True and t["project"] == "weather-station"
    root = t["nodes"]["."]
    assert root["type"] == "root" and root["kind"] == "system" and root["name"] == "weather-station"
    assert root["item"] == "weather-station.md" and root["parent"] is None
    assert t["children"]["."][:6] == ["backend", "dashboard", "deploy", "firmware", "host", "protocol"]
    assert t["children"]["."][-1] == "modgate.yaml"  # sys tier first, then code tier
    assert t["nodes"]["firmware/ports/hal_ports"]["parent"] == "firmware/ports"
    assert t["nodes"]["firmware/ports"]["parent"] == "firmware" and t["nodes"]["firmware/ports"]["name"] == "ports"
    assert t["nodes"]["deploy/prod"]["parent"] == "deploy"
    assert t["files"]["firmware/ports/hal_ports/include/hal/adc.hpp"]["mod"] == "hal_ports"
    assert t["files"]["firmware/ports/hal_ports/fakes/fake_adc.hpp"]["insrc"] is True  # sources: [include, fakes]
    for n in t["nodes"].values():
        assert n["tier"] == ("sys" if n["type"] in ("root", "module", "group") else "code")
        if n["parent"] is not None:
            assert n["id"] in t["children"][n["parent"]]
        assert n["children_n"] == len(t["children"][n["id"]])


def test_example_interior_dirs_and_flags(example_tree):
    t = example_tree
    bm = "firmware/sensing/battery_monitor"
    inc = t["nodes"][f"{bm}/include/battery_monitor"]
    assert inc["type"] == "dir" and inc["name"] == "include/battery_monitor" and inc["parent"] == bm
    assert t["nodes"]["backend/ingest/src/ingest"]["name"] == "src/ingest"
    f = t["files"][f"{bm}/test/test_brownout.cpp"]
    assert f == {"node": f"{bm}/test/test_brownout.cpp", "mod": "battery_monitor", "lang": "cpp", "insrc": False,
                 "test": True, "vendor": False}
    assert t["files"][f"{bm}/src/brownout.cpp"]["insrc"] is True
    assert t["files"]["dashboard/test/lowBatteryBanner.test.ts"]["test"] is True
    assert t["files"]["backend/telemetry_db/backup.sh"]["insrc"] is True  # sources names a file
    assert t["files"]["deploy/prod/config/prod.env"]["lang"] == "text"
    assert not any(r.endswith((".md", ".bind.yaml")) for r in t["files"])
    assert not any("/docs" in i or i.startswith("docs") for i in t["nodes"])


def test_example_docs_state_bind_reqs(example_tree):
    t = example_tree
    root = t["modules"]["weather-station"]
    assert [(d["item"], d["role"]) for d in root["docs"]] == [
        ("weather-station.md", "overview"), ("docs/weather-station.brief.md", "brief"),
        ("docs/weather-station.req.md", "req"), ("docs/weather-station.icd.md", "icd"),
        ("docs/weather-station.tests.md", "tests")]
    assert root["icd"] == "docs/weather-station.icd.md" and set(root["reqs"]) == {"REQ-WS-001", "REQ-WS-002", "REQ-WS-003"}
    bm = t["nodes"]["firmware/sensing/battery_monitor"]
    assert bm["state"] == "unreviewed change" and t["nodes"]["."]["state"] == "verified"
    assert bm["reqs"] == ["REQ-BATMON-001", "REQ-BATMON-002"] and bm["crit"] == "L2"
    assert bm["icd"]["item"].endswith("battery_monitor.icd.md")
    m = t["modules"]["battery_monitor"]
    assert m["reqs"]["REQ-BATMON-002"]["parents"] == ["FEAT-BATMON-002", "REQ-SENS-002"]
    assert m["bind"]["REQ-BATMON-002"] == [
        "firmware/sensing/battery_monitor/include/battery_monitor/battery_monitor.hpp",
        "firmware/sensing/battery_monitor/src/brownout.cpp", "firmware/sensing/battery_monitor/test/test_brownout.cpp"]
    assert t["modules"]["prod"]["bind"]["REQ-PROD-001"] == [
        "deploy/prod/compose.yaml", "deploy/prod/config/prod.env", "deploy/prod/smoke-test.sh"]  # dir entry expanded
    assert m["sources"] == ["firmware/sensing/battery_monitor/src", "firmware/sensing/battery_monitor/include"]
    assert t["modules"]["prod"]["closure"] == ["ingest", "protocol", "telemetry_db"]
    assert t["nodes"]["firmware/sensing/study_adc_noise_floor"]["crit"] == "L0"  # own override
    assert t["nodes"]["host/probe_access"]["crit"] == "L1" and t["nodes"]["firmware/storage/recorder"]["crit"] == "L2"
    assert t["nodes"]["firmware"]["status"] == "approved" and t["nodes"]["firmware"]["version"] == 1
    assert t["nodes"]["firmware/sensing"]["summary"].startswith("Sensing subsystem")
    assert "firmware/sensing/battery_monitor/docs/battery_monitor.bind.yaml" in t["read"]
    assert "weather-station.md" in t["read"]


STORAGE_GUARD = "firmware/storage/include/storage/storage_guard.hpp#storage::StorageGuard"
EXPECTED_REFS = {
    ".": {"SENS": "firmware/sensing", "STOR": "firmware/storage", "COMMS": "firmware/comms", "ING": "backend/ingest",
          "DB": "backend/telemetry_db", "DASH": "dashboard", "PROD": "deploy/prod", "PROBE": "host/probe_access",
          "FW": "firmware", "BE": "backend"},
    "firmware": {"SENS": "firmware/sensing", "STOR": "firmware/storage", "COMMS": "firmware/comms",
                 "PORTS": "firmware/ports", "ADP": "firmware/adapters"},
    "firmware/sensing": {"HUM": "firmware/sensing/humidity_sensor", "BAT": "firmware/sensing/battery_monitor",
                         "STUDY": "firmware/sensing/study_adc_noise_floor", "OUT": None},
    "firmware/storage": {"A": "firmware/storage/sd_storage", "B": "firmware/storage/recorder", "G": STORAGE_GUARD,
                         "P": None},
    "backend": {"ST": "firmware/comms", "ING": "backend/ingest", "DB": "backend/telemetry_db", "DASH": "dashboard"},
}


def test_example_every_resolution(example_tree):
    t = example_tree
    assert set(t["diagrams"]) == set(EXPECTED_REFS)
    own = {"StorageGuard": STORAGE_GUARD}
    for container, want in EXPECTED_REFS.items():
        flow = t["diagrams"][container]["flow"]
        labels = {**{k: v["label"] for k, v in flow["nodes"].items()}, **{k: v["label"] for k, v in flow["subgraphs"].items()}}
        got = {mid: T.resolve_ref(t, container, labels[mid], mid, own) for mid in labels}
        assert got == want, container
    assert T.resolve_ref(t, "firmware/storage", labels_of(t, "firmware/storage")["G"], "G", {}) is None


def labels_of(t, container):
    return {k: v["label"] for k, v in t["diagrams"][container]["flow"]["nodes"].items()}


def test_example_resolved_edges_and_actors(example_tree):
    t = example_tree
    root = T.resolve_diagram(t, ".")
    pairs = {(e["s"], e["t"]): e for e in root["edges"]}
    assert pairs[("firmware/comms", "backend/ingest")]["label"] == "protocol: weather.v1.Reading over HTTPS"
    assert ("backend/telemetry_db", "dashboard") in pairs
    assert pairs[("deploy/prod", "backend")]["dash"] is True
    assert pairs[("host/probe_access", "firmware")]["dash"] is True
    fw = T.resolve_diagram(t, "firmware")
    ports = [e for e in fw["edges"] if e["t"] == "firmware/ports" and e["s"] != "firmware/adapters"]
    assert sorted(e["s"] for e in ports) == ["firmware/comms", "firmware/sensing", "firmware/storage"]
    assert all(e["dash"] for e in ports)
    sens = T.resolve_diagram(t, "firmware/sensing")
    assert sens["nodes"]["OUT"]["id"] == "firmware/sensing#m:OUT" and sens["nodes"]["OUT"]["kind"] == "actor"
    stor = T.resolve_diagram(t, "firmware/storage", {"StorageGuard": STORAGE_GUARD})
    assert stor["nodes"]["P"]["kind"] == "req" and stor["nodes"]["G"]["ref"] == STORAGE_GUARD
    assert T.resolve_diagram(t, "firmware/comms") is None


def test_self_named_node_and_subgraph_resolve_to_the_container(example_tree):
    t = example_tree
    assert T.resolve_ref(t, "firmware/storage", "storage", "ST", {}) == "firmware/storage"
    assert T.resolve_ref(t, "firmware/comms", "comms", "C", {}) == "firmware/comms"
    assert T.resolve_ref(t, "firmware", "sensing", "S", {}) == "firmware/sensing"  # descendants still first


def test_example_zero_diagnode(example_tree):
    for container in example_tree["diagrams"]:
        for own in ({}, {"StorageGuard": STORAGE_GUARD}):
            assert T.resolve_diagram(example_tree, container, own)["diagnode"] == [], container


def test_load_tree_is_read_only_and_deterministic(tmp_path):
    root = tmp_path / "weather-station"
    shutil.copytree(EXAMPLE, root, ignore=SKIP)
    before = _walk_hash(tmp_path)
    a = T.load_tree(root, modgate=True)
    b = T.load_tree(root, modgate=True)
    assert _walk_hash(tmp_path) == before
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------- the poly fixture, modgate mode ----------

def test_poly_modules_vendor_and_skips(poly_repo):
    _write(poly_repo, "core/c/src/scratch.tmp")
    _write(poly_repo, "node_modules/x/y.js")
    _write(poly_repo, "web/build/out.js")
    _write(poly_repo, "web/src/__pycache__/m.cpython-312.pyc")
    _write(poly_repo, "svc/pkg/src/pkg.egg-info/top_level.txt")
    _write(poly_repo, "web/cache.nosync/z.js")
    t = T.load_tree(poly_repo, modgate=True)
    assert set(t["modules"]) == {"poly", "core", "c", "geo", "svc", "pkg", "db", "web", "proto", "fmt", "extra"}
    assert _ids(t, "group") == {"tools"} and t["nodes"]["tools/fmt"]["parent"] == "tools"
    assert t["nodes"]["tools/fmt"]["kind"] == "tool" and t["nodes"]["proto"]["kind"] == "protocol"
    v = t["nodes"]["vendor"]
    assert v["type"] == "dir" and v["vendor"] is True and t["children"]["vendor"] == [] and v["parent"] == "."
    assert not any(r.startswith("vendor/") for r in t["files"])
    assert t["vendor"] == ["vendor"] and "*.tmp" in t["ignore"]
    for rel in t["files"]:
        assert not rel.startswith((".hidden", "node_modules")) and "/build/" not in rel
        assert not rel.endswith((".tmp", ".pyc")) and "egg-info" not in rel and "nosync" not in rel
    assert "modgate.yaml" in t["files"]


def test_poly_flags_docs_and_closure(poly_repo):
    t = T.load_tree(poly_repo, modgate=True)
    f = t["files"]
    assert f["core/geo/test/test_geo.cpp"]["test"] is True and f["core/geo/test/test_geo.cpp"]["insrc"] is False
    assert f["core/geo/include/geo/shape.hpp"]["insrc"] is True and f["core/geo/include/geo/shape.hpp"]["mod"] == "geo"
    assert f["svc/pkg/pyproject.toml"]["insrc"] is False and f["svc/pkg/src/pkg/core.py"]["insrc"] is True
    assert f["svc/pkg/test/test_core.py"]["test"] is True and f["svc/db/migrations/001.sql"]["insrc"] is True
    assert f["proto/demo.proto"]["insrc"] is True and f["web/src/math.ts"]["lang"] == "ts"
    assert t["nodes"]["core/geo/include/geo"]["name"] == "include/geo"
    geo = t["modules"]["geo"]
    assert geo["bind"] == {"REQ-GEO-001": ["core/geo/include/geo/shape.hpp", "core/geo/src/circle.cpp",
                                           "core/geo/test/test_geo.cpp"]}
    assert list(geo["reqs"]) == ["REQ-GEO-001"] and geo["closure"] == ["c"]
    assert t["nodes"]["core/geo"]["icd"] == {"item": "core/geo/docs/geo.icd.md", "head": "Public API"}
    assert t["nodes"]["core/geo"]["state"] == "verified" and t["nodes"]["core/geo"]["crit"] == "L1"
    assert t["modules"]["pkg"]["closure"] == ["db", "proto"]
    assert t["modules"]["poly"]["icd"] == "docs/poly.icd.md"


def test_poly_diagrams(poly_repo):
    t = T.load_tree(poly_repo, modgate=True)
    root = T.resolve_diagram(t, ".")
    refs = {m: n["ref"] for m, n in root["nodes"].items()}
    assert refs == {"CORE": "core", "SVC": "svc", "WEB": "web", "PROTO": "proto", "EXTRA": "extra", "GHOST": None,
                    "OP": None}
    assert root["diagnode"] == ["GHOST"]
    assert root["nodes"]["OP"]["kind"] == "ext" and root["nodes"]["OP"]["id"] == ".#m:OP"
    assert ("svc", "proto") in {(e["s"], e["t"]) for e in root["edges"] if e["dash"]}
    drawn = {n["ref"] for n in root["nodes"].values()}
    assert "tools" not in drawn  # the UNDRAWN trap
    core = T.resolve_diagram(t, "core")
    assert [(e["s"], e["t"], e["label"]) for e in core["edges"]] == [("core/geo", "core/c", "uses util")]
    svc = T.resolve_diagram(t, "svc")
    assert [(e["s"], e["t"]) for e in svc["edges"]] == [("svc/pkg", "svc/db")]


def test_nested_project_symlinks_and_ignore_globs(poly_repo, tmp_path):
    _write(poly_repo, "core/nested/modgate.yaml", "project: nested\n")
    _write(poly_repo, "core/nested/nested.md", "---\nkind: system\n---\n# nested\n")
    _write(poly_repo, "core/nested/src/a.c")
    outside = _write(tmp_path, "outside/secret.c")
    os.symlink(outside, poly_repo / "core" / "c" / "src" / "link_out.c")
    os.symlink(outside.parent, poly_repo / "core" / "c" / "src" / "dir_out")
    os.symlink(poly_repo / "core" / "c" / "src" / "util.c", poly_repo / "core" / "c" / "src" / "link_in.c")
    _write(poly_repo, "web/src/gen/skip.ts")
    _write(poly_repo, "web/src/keep.ts")
    cfg = (poly_repo / "modgate.yaml").read_text().replace('ignore: ["*.tmp"]', 'ignore: ["*.tmp", "web/src/gen", "keep.ts"]')
    (poly_repo / "modgate.yaml").write_text(cfg)
    t = T.load_tree(poly_repo, modgate=True, config={"ignore": ["core/c/src/main.c"]})
    p = t["nodes"]["core/nested"]
    assert p["type"] == "group" and p["kind"] == "project" and p["tier"] == "sys" and p["parent"] == "core"
    assert t["children"]["core/nested"] == [] and "nested" not in t["modules"]
    assert not any(r.startswith("core/nested/") for r in t["files"])
    assert "core/c/src/link_out.c" not in t["files"] and not any("dir_out" in r for r in t["files"])
    assert "core/c/src/link_in.c" in t["files"]
    assert "web/src/gen/skip.ts" not in t["files"] and "web/src/keep.ts" not in t["files"]
    assert "core/c/src/main.c" not in t["files"] and "core/c/src/util.c" in t["files"]


def test_group_chain_collapse(tmp_path):
    r = tmp_path / "chain"
    _write(r, "modgate.yaml", "project: chain\n")
    _write(r, "chain.md", "---\nkind: system\n---\n# chain\n")
    for m in ("a/b/m", "a/b/n", "x/y/z/k"):
        name = m.rsplit("/", 1)[-1]
        _write(r, f"{m}/{name}.md", "---\nkind: code\n---\n")
        _write(r, f"{m}/src/{name}.c")
    _write(r, "x/own.c")  # x has its own file: no collapse at x
    t = T.load_tree(r, modgate=True)
    assert _ids(t, "group") == {"a/b", "x", "x/y/z"}
    assert t["nodes"]["a/b"]["name"] == "a/b" and t["nodes"]["a/b"]["parent"] == "."
    assert t["nodes"]["x/y/z"]["name"] == "y/z" and t["nodes"]["x/y/z"]["parent"] == "x"
    assert t["nodes"]["a/b/m"]["parent"] == "a/b" and t["files"]["x/own.c"]["mod"] == "chain"
    assert t["files"]["x/own.c"]["node"] == "x/own.c" and t["nodes"]["x/own.c"]["parent"] == "x"


def test_synthetic_root_and_duplicate_names(tmp_path):
    r = tmp_path / "noroot"
    _write(r, "modgate.yaml", "project: proj\ncriticality: L3\n")
    _write(r, "a/m/m.md", "---\nkind: code\n---\n")
    _write(r, "b/m/m.md", "---\nkind: code\n---\n")
    _write(r, "c/notmod/notmod.md", "---\ntitle: no kind\n---\n")
    _write(r, "c/notmod/x.py")
    _write(r, "s/s.md", "---\nkind: code\nsources: lib\n---\n")
    _write(r, "s/lib/y.py")
    t = T.load_tree(r, modgate=True)
    assert t["modules"]["s"]["sources"] == ["s/lib"] and t["files"]["s/lib/y.py"]["insrc"] is True
    assert t["nodes"]["."]["name"] == "proj" and t["nodes"]["."]["kind"] == "system" and t["nodes"]["."]["item"] is None
    assert set(t["modules"]) == {"proj", "m", "b/m", "s"} and t["nodes"]["b/m"]["crit"] == "L3"
    assert t["files"]["c/notmod/x.py"]["mod"] == "proj"


def test_buckets(tmp_path):
    r = tmp_path / "big"
    _write(r, "modgate.yaml", "project: big\n")
    _write(r, "big.md", "---\nkind: code\n---\n")
    for i in range(151):
        _write(r, f"gen/f{i:03d}.c")
    for i in range(150):
        _write(r, f"ok/f{i:03d}.c")
    t = T.load_tree(r, modgate=True)
    kids = t["children"]["gen"]
    assert kids == ["gen/~f000.c-f099.c", "gen/~f100.c-f150.c"]
    b = t["nodes"][kids[0]]
    assert b["type"] == "bucket" and b["tier"] == "code" and b["name"] == "f000.c–f099.c" and b["parent"] == "gen"
    assert len(t["children"][kids[0]]) == 100 and len(t["children"][kids[1]]) == 51 and b["children_n"] == 100
    assert t["nodes"]["gen/f150.c"]["parent"] == kids[1] and t["files"]["gen/f150.c"]["node"] == "gen/f150.c"
    assert len(t["children"]["ok"]) == 150 and not any(i.startswith("ok/~") for i in t["nodes"])


# ---------- plain mode ----------

def test_plain_units(plain_repo):
    t = T.load_tree(plain_repo, modgate=False)
    assert t["modgate"] is False
    kinds = {n["id"]: n["kind"] for n in t["nodes"].values() if n["type"] == "module"}
    assert kinds == {"core": "dir", "proto": "dir", "tools": "dir", "web": "node", "svc/pkg": "python",
                     "svc/db": "dir", "extra": "dir", "vendor": "dir"}
    assert _ids(t, "group") == {"svc"} and t["nodes"]["svc/pkg"]["parent"] == "svc"
    root = t["nodes"]["."]
    assert root["type"] == "root" and root["name"] == "plain" and root["item"] == "README.md"
    assert root["docs"] == [{"item": "README.md", "role": "overview", "title": "Plain poly"}]
    assert t["nodes"]["svc"]["item"] == "svc/README.md" and t["nodes"]["svc"]["summary"] == "The service group."
    assert t["nodes"]["tools/fmt/src"]["name"] == "fmt/src" and t["nodes"]["tools/fmt/src"]["parent"] == "tools"
    assert t["files"]["web/src/math.ts"] == {"node": "web/src/math.ts", "mod": "web", "lang": "ts", "insrc": True,
                                             "test": False, "vendor": False}
    assert t["files"]["svc/pkg/test/test_core.py"]["insrc"] is False
    assert t["modules"]["pkg"]["sources"] == ["svc/pkg"]
    d = T.resolve_diagram(t, ".")
    assert [(e["s"], e["t"]) for e in d["edges"]] == [("web", "svc/pkg"), ("svc/pkg", "svc/db")]
    assert d["diagnode"] == []


def test_plain_manifests_and_root_unit(tmp_path):
    r = tmp_path / "mono"
    _write(r, "package.json", "{}")
    _write(r, "src/a.ts")
    for d, m in (("rs", "Cargo.toml"), ("goapp", "go.mod"), ("jv", "pom.xml"), ("gr", "build.gradle.kts"),
                 ("cm", "CMakeLists.txt"), ("net", "app.csproj"), ("py2", "setup.py")):
        _write(r, f"pkgs/{d}/{m}")
        _write(r, f"pkgs/{d}/main.c")
    t = T.load_tree(r, modgate=False)
    root = t["nodes"]["."]
    assert root["type"] == "root" and root["kind"] == "node" and "mono" in t["modules"]
    assert t["files"]["src/a.ts"]["mod"] == "mono"
    assert _ids(t, "group") == {"pkgs"}
    kinds = {n["name"]: n["kind"] for n in t["nodes"].values() if n["type"] == "module"}
    assert kinds == {"rs": "cargo", "goapp": "go", "jv": "maven", "gr": "gradle", "cm": "cmake", "net": "dotnet",
                     "py2": "python"}
    bare = tmp_path / "bare"
    _write(bare, "lib/x.py")
    t2 = T.load_tree(bare, modgate=False)
    assert t2["nodes"]["."]["kind"] == "dir" and t2["files"]["lib/x.py"]["mod"] == "bare"

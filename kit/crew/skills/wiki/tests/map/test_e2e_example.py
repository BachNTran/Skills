"""End-to-end map of example/weather-station (spec §9 WP3 acceptance: levels, ghosts, hand-off, text)."""
from __future__ import annotations

import random
import shutil

import pytest

from conftest import EXAMPLE_SRC
from wikimap import build_map

ROOT_IDS = {"firmware", "backend", "dashboard", "protocol", "deploy", "host"}

GOLDEN_ROOT = """\
weather-station  system  [systems]  at .
  backend    module/system  L2  approved  verified  ▸2  cov 0/9
  dashboard  module/code  L2  approved  verified  ▸3  cov 0/3
  deploy     group/group  ▸1
  firmware   module/system  L2  approved  verified  ▸6  cov 17/53
  host       group/group  ▸1
  protocol   module/protocol  L2  approved  verified  ▸3  cov 1/1
edges:
  backend → dashboard   flow  "read API"  declared
  backend → protocol    dep contract×4  declared
  dashboard → backend   flow  "GET /v1/latest"  declared
  dashboard → protocol  dep  declared
  deploy → backend      flow dep×2  "deploys"  declared
  firmware → backend    flow×2  "weather.v1.Reading · protocol: weather.v1.Reading over HTTPS"  declared
  firmware → protocol   dep contract×3  declared
  host → firmware       flow  "flashing / debug"  declared
ghosts:
  (none)
"""


@pytest.fixture(scope="module")
def m(tmp_path_factory):
    if not EXAMPLE_SRC.is_dir():
        pytest.skip("example/weather-station missing")
    base = tmp_path_factory.mktemp("e2e")
    root = base / "weather-station"
    shutil.copytree(EXAMPLE_SRC, root, ignore=shutil.ignore_patterns(".wiki", ".wikimap", "__pycache__"))
    return build_map(root, base / "data", exact=True)


def by_pair(lv):
    return {(e["s"], e["t"]): e for e in lv["edges"]}


def test_counts_and_no_diagnode(m):
    assert len(m.modules) == 22
    assert all(d["diagnode"] == [] for d in m.diagrams.values())  # zero DIAGNODE on the example
    assert m.stats["symbols"] > 100 and m.stats["resolved_hi"] >= 0.8


def test_systems_root(m):
    lv = m.level("systems", ".")
    assert {n["id"] for n in lv["nodes"]} == ROOT_IDS
    e = by_pair(lv)
    assert "protocol: weather.v1.Reading over HTTPS" in e[("firmware", "backend")]["labels"]
    dep = e[("deploy", "backend")]
    assert dep["dash"] is True and set(dep["kinds"]) == {"flow", "dep"}
    assert e[("host", "firmware")]["dash"] is True
    assert e[("backend", "dashboard")]["labels"] == ["read API"]
    assert lv["ghosts"] == []


def test_systems_firmware(m):
    lv = m.level("systems", "firmware")
    assert {n["name"] for n in lv["nodes"]} == {"sensing", "storage", "comms", "ports", "adapters", "targets"}
    e = by_pair(lv)[("firmware/sensing", "firmware/storage")]
    assert e["labels"] == ["Reading every 60 s", "LOW_BATTERY"] and e["state"] == "declared"
    g = {g["id"]: g for g in lv["ghosts"]}["ghost:backend/ingest"]
    assert g["side"] == "out" and g["at"] == "backend" and g["path"] == "backend › ingest" and g["name"] == "ingest"
    assert ("firmware/comms", "ghost:backend/ingest") in by_pair(lv)
    ports = by_pair(lv)[("firmware/sensing", "firmware/ports")]
    assert ports["state"] == "both" and ports["kinds"]["flow"] >= 1 and ports["kinds"]["call"] >= 1
    assert [c["id"] for c in lv["crumbs"]] == [".", "firmware"]


def test_systems_sensing_and_storage(m):
    sens = m.level("systems", "firmware/sensing")
    assert "firmware/sensing#m:OUT" in {n["id"] for n in sens["nodes"]}  # "Reading" is an actor
    stor = m.level("systems", "firmware/storage")
    ids = {n["id"] for n in stor["nodes"]}
    assert "firmware/storage/:own" in ids
    own = next(n for n in stor["nodes"] if n["id"] == "firmware/storage/:own")
    assert own["drill"] == "code" and own["type"] == "own"
    assert m.nodes["firmware/storage#m:P"]["kind"] == "req"
    assert by_pair(stor)[("firmware/storage/:own", "firmware/storage/recorder")]["state"] == "both"
    assert ("firmware/storage#m:P", "firmware/storage/:own") in by_pair(stor)  # P → G (StorageGuard symbol)


def test_code_storage_guard_edges_both(m):
    lv = m.level("code", "firmware/storage")
    e = by_pair(lv)
    for target in ("firmware/storage/recorder", "firmware/storage/sd_storage"):
        for src in ("firmware/storage/src", "firmware/storage/include/storage"):
            assert e[(src, target)]["state"] == "both", (src, target)
    assert m.level("code", "firmware/storage/:own")["nodes"]
    assert "firmware/storage/:own" not in {n["id"] for n in lv["nodes"]}  # the Code lens never shows :own


def test_code_root_contracts(m):
    lv = m.level("code", ".")
    contracts = [e for e in lv["edges"] if e["t"] == "protocol" and "contract" in e["kinds"]]
    assert {e["s"] for e in contracts} >= {"firmware", "backend"}
    assert "modgate.yaml" in {n["id"] for n in lv["nodes"]}  # text files show in the Code lens only
    assert "modgate.yaml" not in {n["id"] for n in m.level("systems", ".")["nodes"]}


def test_systems_leaf_hands_off(m):
    assert m.level("systems", "firmware/comms") is None
    idx = {n["id"]: n for n in m.index()["nodes"]}
    assert idx["firmware/comms"]["drill"] == {"systems": "code", "code": "code"}
    assert m.level("code", "firmware/comms") is not None
    assert idx["firmware/ports"]["type"] == "group" and idx["firmware/ports"]["drill"]["systems"] == "systems"


def test_search_decode_first(m):
    hits = m.search("decode")
    assert hits[0]["id"] == "backend/ingest/src/ingest/decode.py#decode"
    assert hits[0]["path"] == "backend › ingest › src/ingest › decode.py › decode"


def test_node_reqs_and_tests(m):
    nid = "firmware/sensing/battery_monitor/src/brownout.cpp#battery_monitor::BatteryMonitor::update_brownout"
    got = m.node(nid)
    assert any(r["id"] == "REQ-BATMON-002" and r["item"].endswith("battery_monitor.req.md") for r in got["reqs"])
    assert any("REQ_BATMON_002" in t["name"] for t in got["tests"])
    assert any(c["id"].endswith("#battery_monitor::BatteryMonitor::sample") for c in got["callers"])
    assert {d["role"] for d in got["docs"]} >= {"overview", "req", "icd"}


def test_show_text_golden(m):
    assert m.show_text("systems", ".") == GOLDEN_ROOT


def test_show_text_depth_and_trace_text(m):
    text = m.show_text("systems", "firmware", 2)
    assert "\n    battery_monitor  " in text and text.startswith("firmware  system  [systems]  at firmware\n")
    assert "  ingest  backend › ingest  out" in text
    tt = m.trace_text("firmware/sensing/battery_monitor/src/battery_monitor.cpp#battery_monitor::BatteryMonitor::sample",
                      "out", 2)
    assert "weather-station › firmware: sensing → ports (call ×" in tt


def test_lifting_conservation_on_example(m):
    from test_graph import _lca, _strict_copy  # same oracle as the fixture test
    rng = random.Random(11)
    containers = sorted(n for n in m.nodes if m.level("code", n) is not None)
    for c in rng.sample(containers, 20):
        sm = _strict_copy(m, drop=c)
        lv = sm.level("code", c)
        want: dict = {}
        one = 0
        for e in sm.edges:
            l, a, b = _lca(sm, e["s"], e["t"])
            if l == c:
                want[(a, b)] = want.get((a, b), 0) + 1
            one += (c in sm.chain(e["s"])) != (c in sm.chain(e["t"]))
        inner = {(e["s"], e["t"]): e["n"] for e in lv["edges"] if "ghost:" not in e["id"]}
        assert inner == want, c
        assert sum(e["n"] for e in lv["edges"] if "ghost:" in e["id"]) == one, c

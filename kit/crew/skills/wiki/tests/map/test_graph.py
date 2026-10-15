"""Map model (spec §2.4–§2.7, §6): lifting, determinism, cache, search, trace, source_path, buckets, no writes."""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from pathlib import Path

import pytest

from conftest import make_plain, make_poly
import wikimap
from wikimap import build_map, open_map
from wikimap.graph import Map, default_data_dir, is_own


@pytest.fixture(scope="module")
def pm(tmp_path_factory):
    base = tmp_path_factory.mktemp("polyg")
    return build_map(make_poly(base / "poly"), base / "data", exact=True)


def tree_hash(root: Path) -> dict[str, str]:
    out = {}
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = Path(dp) / f
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest() if not p.is_symlink() else "L"
    return out


# ---------- lifting conservation (oracle) ----------

def _strict_copy(m: Map, drop: str | None = None) -> Map:
    """Same map without edges between a node and its own ancestor (those have no LCA child pair), and
    without edges touching `drop` (a container's own edges are attributed to its code, not conserved)."""
    c = Map()
    c.__dict__.update(m.__dict__)
    keep = []
    for e in m.edges:
        cs, ct = m.chain(e["s"]), m.chain(e["t"])
        if e["s"] in ct or e["t"] in cs or drop in (e["s"], e["t"]):
            continue
        keep.append(e)
    c.edges = keep
    c._init()
    return c


def _lca(m, s, t):
    cs, ct = m.chain(s), m.chain(t)
    i = 0
    while i < len(cs) and i < len(ct) and cs[i] == ct[i]:
        i += 1
    return cs[i - 1], cs[i], ct[i]


def test_lifting_conservation_code_lens(pm):
    m = _strict_copy(pm)
    containers = sorted(n for n in m.nodes if m.level("code", n) is not None)
    total = 0
    for c in containers:
        lv = m.level("code", c)
        total += sum(e["n"] for e in lv["edges"] if not e["s"].startswith("ghost:") and not e["t"].startswith("ghost:"))
    assert total == len(m.edges)  # every base edge appears exactly once, at its LCA

    rng = random.Random(7)
    for c in rng.sample(containers, min(25, len(containers))):
        m = _strict_copy(pm, drop=c)
        lv = m.level("code", c)
        want: dict[tuple, int] = {}
        inside_one = 0
        for e in m.edges:
            l, a, b = _lca(m, e["s"], e["t"])
            if l == c:
                want[(a, b)] = want.get((a, b), 0) + 1
            in_s, in_t = c in m.chain(e["s"]), c in m.chain(e["t"])
            if in_s != in_t:
                inside_one += 1
        got = {(e["s"], e["t"]): e["n"] for e in lv["edges"]
               if not e["s"].startswith("ghost:") and not e["t"].startswith("ghost:")}
        assert got == want, c
        ghost_n = sum(e["n"] for e in lv["edges"] if e["s"].startswith("ghost:") or e["t"].startswith("ghost:"))
        assert ghost_n == inside_one, c  # counts conserved on the ghost side too
        sides = {g["id"]: g["side"] for g in lv["ghosts"]}
        for e in lv["edges"]:
            if e["t"].startswith("ghost:"):
                assert sides[e["t"]] in ("out", "both")
            if e["s"].startswith("ghost:"):
                assert sides[e["s"]] in ("in", "both")


def test_lifting_code_kinds_counted_once_per_pair(pm):
    """Code edges touching the container itself are never pinned onto sibling pairs (counts stay exact)."""
    from wikimap.graph import CODE_KINDS
    for c in sorted(n for n in pm.nodes if pm.level("code", n) is not None):
        want: dict[tuple, int] = {}
        for e in pm.edges:
            if e["k"] not in CODE_KINDS or c in (e["s"], e["t"]):
                continue
            cs, ct = pm.chain(e["s"]), pm.chain(e["t"])
            if c not in cs or c not in ct:
                continue
            a, b = cs[cs.index(c) + 1], ct[ct.index(c) + 1]
            if a != b:
                want[(a, b)] = want.get((a, b), 0) + 1
        got = {}
        for e in pm.level("code", c)["edges"]:
            n = sum(v for k, v in e["kinds"].items() if k in CODE_KINDS)
            if n and not e["s"].startswith("ghost:") and not e["t"].startswith("ghost:"):
                got[(e["s"], e["t"])] = n
        assert got == want, c


def test_trace_both_is_union_of_in_and_out(tmp_path):
    root = tmp_path / "r"
    (root / "app").mkdir(parents=True)
    (root / "app" / "mut.py").write_text("def a():\n    return b()\n\ndef b():\n    return a()\n\n"
                                         "def c():\n    return b()\n")
    m = build_map(root, tmp_path / "d", exact=True)
    a = "app/mut.py#a"
    both, i, o = (set(m.trace(a, d, 2)["nodes"]) for d in ("both", "in", "out"))
    assert both == i | o and "app/mut.py#c" in both


def test_self_named_diagram_node_keeps_systems_leaf(tmp_path):
    from conftest import EXAMPLE_SRC
    import shutil
    root = tmp_path / "ws"
    shutil.copytree(EXAMPLE_SRC, root, ignore=shutil.ignore_patterns(".wiki", ".wikimap", "__pycache__"))
    doc = root / "firmware" / "comms" / "comms.md"
    doc.write_text(doc.read_text() + '\n## Subsystems and interactions\n\n```mermaid\nflowchart LR\n'
                   '  C["comms"] -- "HTTPS POST" --> I["ingest"]\n```\n')
    m = build_map(root, tmp_path / "d", exact=True)
    assert m.diagrams["firmware/comms"]["nodes"]["C"]["ref"] == "firmware/comms"
    assert m.level("systems", "firmware/comms") is None
    assert not any(n.endswith("#m:C") for n in m.nodes)


def test_lifting_systems_lens_maps_code_to_own(pm):
    m = _strict_copy(pm)
    for c in sorted(n for n in m.nodes if m.level("systems", n) is not None):
        lv = m.level("systems", c)
        ids = {n["id"] for n in lv["nodes"]}
        assert all(m.nodes[i]["tier"] == "sys" for i in ids if not is_own(i))
        for e in lv["edges"]:
            for end in (e["s"], e["t"]):
                assert end in ids or end.startswith("ghost:")


def test_container_own_deps_attach_to_observing_code(pm):
    # svc/pkg declares deps [db, proto]; its own code (src) both depends on and touches db
    lv = pm.level("code", "svc/pkg")
    e = next(e for e in lv["edges"] if e["s"] == "svc/pkg/src" and e["t"] == "ghost:svc/db")
    assert "dep" in e["kinds"] and "data" in e["kinds"] and e["state"] == "both"


# ---------- determinism and cache ----------

def test_two_builds_identical_except_built(tmp_path):
    root = make_poly(tmp_path / "poly")
    build_map(root, tmp_path / "d1", exact=True)
    build_map(root, tmp_path / "d2", exact=True)
    a = json.loads((tmp_path / "d1" / "map" / "map.json").read_text())
    b = json.loads((tmp_path / "d2" / "map" / "map.json").read_text())
    assert a.pop("built") and b.pop("built")
    assert a == b
    assert a["v"] == 1 and a["modgate"] is True and len(a["rev"]) == 12
    cache = json.loads((tmp_path / "d1" / "map" / "cache.json").read_text())
    assert cache["v"] == 1 and cache["adapter"].startswith(wikimap.graph.ADAPTER_VERSION)
    ent = cache["files"]["core/geo/src/app.cpp"]
    assert isinstance(ent[0], int) and isinstance(ent[1], int) and len(ent[2]) == 12 and ent[3]["lang"] == "cpp"


def test_warm_rebuild_reextracts_nothing_then_one(tmp_path):
    root = make_poly(tmp_path / "poly")
    m1 = build_map(root, tmp_path / "d", exact=True)
    assert m1.cache_stats["extracted"] > 10
    m2 = build_map(root, tmp_path / "d", exact=True)
    assert m2.cache_stats["extracted"] == 0 and m2.rev == m1.rev
    p = root / "web" / "src" / "y.ts"
    os.utime(p)  # touch only: same content, no re-extraction
    assert build_map(root, tmp_path / "d", exact=True).cache_stats["extracted"] == 0
    p.write_text(p.read_text() + "\nexport function extra(): number { return 1; }\n")
    m3 = build_map(root, tmp_path / "d", exact=True)
    assert m3.cache_stats["extracted"] == 1 and m3.rev != m1.rev
    assert "web/src/y.ts#extra" in m3.nodes


def test_doc_edit_changes_rev(tmp_path):
    root = make_poly(tmp_path / "poly")
    r1 = build_map(root, tmp_path / "d", exact=True).rev
    (root / "core" / "core.md").write_text((root / "core" / "core.md").read_text() + "\nMore.\n")
    assert build_map(root, tmp_path / "d", exact=True).rev != r1


def test_refresh(tmp_path):
    root = make_poly(tmp_path / "poly")
    m = open_map(root, tmp_path / "d", exact=True)
    assert m.refresh() is False
    old = m.rev
    (root / "web" / "src" / "lazy.ts").write_text("/** Later. */\nexport function later2(): number { return 2; }\n")
    assert m.refresh() is True and m.rev != old
    assert "web/src/lazy.ts#later2" in m.nodes and m.level("code", "web/src") is not None


# ---------- API shapes ----------

def test_index_shape(pm):
    idx = pm.index()
    assert {"v", "rev", "repo", "modgate", "built", "root", "nodes", "counts", "stats"} <= set(idx)
    assert idx["repo"] == "poly" and idx["root"] == "."
    assert not any("#" in n["id"] for n in idx["nodes"])
    by = {n["id"]: n for n in idx["nodes"]}
    assert by["."]["drill"] == {"systems": "systems", "code": "code"}
    assert by["proto"]["drill"]["systems"] == "code"
    assert by["core/geo/src/app.cpp"]["drill"] == {"systems": "code", "code": "code"}
    assert set(idx["counts"]) == {"modules", "groups", "files", "symbols", "edges", "findings", "debt"}
    assert idx["counts"]["modules"] == len(pm.modules)


def test_level_errors(pm):
    assert pm.level("systems", "no/such") is None
    assert pm.level("bogus", ".") is None
    assert pm.level("systems", "proto") is None  # Systems leaf: only code inside
    assert pm.level("code", "proto") is not None
    leaf = "core/geo/src/app.cpp#run_app"
    assert pm.level("code", leaf) is None and pm.level("systems", leaf) is None


def test_level_shape_and_payload_size(pm):
    lv = pm.level("systems", ".")
    assert {"v", "rev", "lens", "at", "crumbs", "nodes", "ghosts", "edges", "overflow"} <= set(lv)
    assert lv["crumbs"] == [{"id": ".", "name": "poly"}]
    for n in lv["nodes"]:
        assert {"id", "type", "tier", "kind", "name", "title", "brief", "drill", "n", "item", "src", "sig",
                "badges"} <= set(n)
    for e in lv["edges"]:
        assert e["id"] == f"{e['s']}>{e['t']}"
        assert {"kinds", "n", "conf", "hist", "labels", "dash", "state", "x", "prov", "samples"} <= set(e)
        assert e["state"] in ("both", "declared", "observed", "undeclared")
    xs = [e for e in lv["edges"] if e["s"] == "web" and e["t"] == "tools"]
    assert xs and xs[0]["x"] is True and xs[0]["state"] == "undeclared"
    for lens, at in (("code", "."), ("code", "extra/src"), ("code", "extra/src/long.c")):
        assert len(json.dumps(pm.level(lens, at))) <= 200_000


def test_symbol_buckets(pm):
    kids = pm.children["extra/src/long.c"]
    assert kids and all(pm.nodes[k]["type"] == "bucket" for k in kids)
    assert all(len(pm.children[k]) <= 100 for k in kids)
    assert sum(len(pm.children[k]) for k in kids) == 1000
    assert all(k.startswith("extra/src/long.c#~") for k in kids)
    assert len(pm.level("code", "extra/src/long.c")["nodes"]) <= 150


def test_actor_nodes_and_diagnode(pm):
    assert pm.nodes[".#m:GHOST"]["type"] == "actor" and pm.nodes[".#m:GHOST"]["kind"] == "actor"
    assert pm.nodes[".#m:OP"]["kind"] == "ext"
    assert pm.diagrams["."]["diagnode"] == ["GHOST"]
    assert pm.diagrams["."]["nodes"]["CORE"]["ref"] == "core"


def test_node_payload(pm):
    nid = "core/geo/include/geo/shape.hpp#geo::Shape::area"
    got = pm.node(nid)
    assert {"node", "chain", "docs", "callers", "callees", "impls", "implements", "reqs", "tests", "findings"} <= set(got)
    assert got["chain"][0]["id"] == "." and got["chain"][-1]["id"] == "core/geo/include/geo/shape.hpp#geo::Shape"
    assert [i["id"] for i in got["impls"]] == ["core/geo/src/circle.cpp#geo::Circle::area"]
    assert any(c["id"] == "core/geo/src/app.cpp#run_app" for c in got["callers"])
    assert {r["id"] for r in got["reqs"]} == {"REQ-GEO-001"}  # shape.hpp is bound to REQ-GEO-001
    assert any(t["id"].endswith("#Geo.REQ_GEO_001_area") for t in got["tests"])
    circ = pm.node("core/geo/src/circle.cpp#geo::Circle::area")
    assert any(i["id"] == nid for i in circ["implements"])
    assert pm.node("no/such") is None
    assert pm.node("core/:own") is None or pm.node("core/:own")["node"]["type"] == "own"


def test_search_ranking(pm):
    hits = pm.search("Engine")
    assert hits[0]["id"] == "svc/pkg/src/pkg/core.py#Engine"
    assert {"id", "name", "type", "kind", "path", "at", "lens"} <= set(hits[0])
    assert hits[0]["lens"] == "code" and hits[0]["at"] == "svc/pkg/src/pkg/core.py"
    assert pm.search("svc")[0]["id"] == "svc" and pm.search("svc")[0]["lens"] == "systems"
    assert len(pm.search("e", limit=3)) == 3
    assert pm.search("zzzz-nothing") == []


def test_trace_depth_bound(pm):
    root = "svc/pkg/src/app.py#main"
    one = pm.trace(root, "out", 1)
    two = pm.trace(root, "out", 2)
    assert one["root"] == root and set(one["nodes"]) < set(two["nodes"])
    assert "svc/pkg/src/pkg/core.py#Engine.step" in two["nodes"] and "svc/pkg/src/pkg/core.py#Engine.step" not in one["nodes"]
    assert all(e["k"] in ("call", "inherit") and e["conf"] >= 0.5 for e in two["edges"])
    assert two["nodes"][root][0] == "."
    back = pm.trace("svc/pkg/src/pkg/core.py#Engine.step", "in", 4)
    assert root in back["nodes"]
    assert pm.trace("nope", "in", 1) is None
    text = pm.trace_text(root, "out", 2)
    assert text.startswith("trace main") and "→" in text and "conf" in text


def test_source_path_rejections(tmp_path):
    root = make_poly(tmp_path / "poly")
    src = root / "svc" / "pkg" / "src"
    (src / "huge.py").write_text("x = 1\n" * 200_000)
    (src / "bin.py").write_bytes(b"x = 1\n" + b"\0" * 64)
    (tmp_path / "outside.py").write_text("SECRET = 1\n")
    linked = True
    try:
        os.symlink(tmp_path / "outside.py", src / "link.py")
        os.symlink(src / "app.py", src / "inside_link.py")
        (root / ".env").write_text("API_KEY=DOTENV_SECRET\n")
        os.symlink(root / ".env", src / "env_link.yaml")
    except OSError:
        linked = False
    m = build_map(root, tmp_path / "d", exact=True)
    if linked:
        assert "svc/pkg/src/env_link.yaml" not in m.files and m.source_path("svc/pkg/src/env_link.yaml") is None
    assert m.source_path("svc/pkg/src/app.py") == (src / "app.py").resolve()
    for bad in ("../x", "/etc/passwd", str(root / "svc/pkg/src/app.py"), "svc/svc.md", "poly.md",
                "svc/pkg/src/huge.py", "svc/pkg/src/bin.py", ".hidden/ignored.py", "vendor/thirdparty/lib.c",
                "svc/pkg/src/link.py", None, 5):
        assert m.source_path(bad) is None, bad
    assert m.files["svc/pkg/src/bin.py"]["rec"]["skip"] == "binary"
    if linked:
        assert m.source_path("svc/pkg/src/inside_link.py") == (src / "app.py").resolve()


# ---------- no writes, annotate, plain mode ----------

def test_open_map_writes_nothing_in_repo_and_no_baseline(tmp_path, monkeypatch):
    root = make_poly(tmp_path / "poly")
    before = tree_hash(root)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    m = open_map(root)  # default data dir: the user cache, since poly does not ignore .wiki
    assert tree_hash(root) == before
    assert not (root / ".wikimap").exists() and not (root / ".wiki").exists()
    assert (default_data_dir(root) / "map" / "map.json").is_file()
    assert str(default_data_dir(root)).startswith(str(tmp_path / "xdg"))
    assert isinstance(m.findings, list)


def test_open_map_calls_fresh_annotate_when_present(tmp_path):
    pytest.importorskip("wikimap.fresh")
    m = open_map(make_poly(tmp_path / "poly"), tmp_path / "d", exact=True)
    codes = {f.code for f in m.findings}
    assert "DIAGNODE" in codes and "UNDRAWN" in codes
    assert m.nodes["."]["badges"]["findings"] >= 2
    assert not (tmp_path / "poly" / ".wikimap").exists()


def test_open_map_without_fresh(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "wikimap.fresh", None)  # import now raises ImportError
    monkeypatch.delattr(wikimap, "fresh", raising=False)
    m = open_map(make_poly(tmp_path / "poly"), tmp_path / "d", exact=True)
    assert m.findings == [] and m.level("systems", ".") is not None


def test_open_map_finds_root_and_tolerates_bad_config(tmp_path):
    root = make_poly(tmp_path / "poly")
    (root / ".wikimap").mkdir()
    (root / ".wikimap" / "config.json").write_text("{not json")
    m = open_map(root / "core" / "geo", tmp_path / "d")  # exact=False walks up to modgate.yaml
    assert Path(m.root) == root.resolve() and m.modgate is True


def test_default_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    r = tmp_path / "r"
    r.mkdir()
    d = default_data_dir(r)
    assert d.parent == tmp_path / "xdg" / "wiki" and len(d.name) == 12
    (r / ".gitignore").write_text("node_modules\n.wiki/\n")
    assert default_data_dir(r) == r.resolve() / ".wiki"
    assert not (r / ".wiki").exists()


def test_plain_mode(tmp_path):
    m = build_map(make_plain(tmp_path / "plain"), tmp_path / "d", exact=True)
    assert m.modgate is False
    lv = m.level("systems", ".")
    names = {n["name"] for n in lv["nodes"]}
    assert {"core", "proto", "tools", "web", "svc"} <= names
    assert not any(e.get("x") for e in m.edges)  # XCALL is modgate-only
    assert any(e["k"] == "flow" for e in m.edges)  # README diagram
    assert m.module_of("svc/pkg/src/pkg/core.py#Engine") == "pkg"


def test_module_of_and_anc(pm):
    assert pm.module_of("core/geo/src/app.cpp#run_app") == "geo"
    assert pm.module_of("core/geo") == "geo" and pm.module_of(".") == "poly"
    assert pm.module_of("ghost:svc/db") == "db"
    assert pm.anc("core/geo/src/app.cpp") == [".", "core", "core/geo", "core/geo/src"]
    assert pm.anc(".") == []


def test_big_indexed_file_is_never_read_whole(tmp_path):
    import tracemalloc
    root = tmp_path / "big"
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.py").write_text("def f():\n    return 1\n")
    for name in ("data.csv", "a/blob.py"):
        with open(root / name, "wb") as f:
            f.truncate(64 << 20)  # sparse 64 MB
    tracemalloc.start()
    try:
        m = build_map(root, tmp_path / "d", exact=True)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 16 << 20
    assert m.files["a/blob.py"]["rec"]["skip"] == "size" and m.files["data.csv"]["rec"]["skip"] == "size"
    assert m.source_path("data.csv") is None

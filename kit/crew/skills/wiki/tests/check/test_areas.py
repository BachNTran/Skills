"""Logical areas (config `systems.areas`): open boxes at the Systems root, members re-parented in the Systems
lens only, edges on real modules, area diagrams and checks, boundary-edge continuity, determinism."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import make_poly
from wikimap import build_map, open_map
from wikimap import tree as T

AREAS = {"systems": {"areas": [
    {"id": "platform", "title": "Platform", "doc": "docs/poly.system_map.md#Platform", "members": ["core", "web"]},
    {"id": "backend", "title": "Backend", "doc": "docs/poly.system_map.md#Backend", "members": ["svc", "fmt"]},
]}}
MAP_DOC = """---
title: poly system map
---
# poly system map

## Platform

What the user touches.

```mermaid
flowchart LR
  CORE["core"] -- "Sample" --> WEB["web"]
```

## Backend

Serves the data.

```mermaid
flowchart LR
  SVC["svc"]
```
"""


def _areas_repo(base: Path, config: dict | None = AREAS) -> Path:
    root = make_poly(base / "poly")
    (root / "docs" / "poly.system_map.md").write_text(MAP_DOC, encoding="utf-8")
    if config is not None:
        (root / ".wikimap").mkdir(exist_ok=True)
        (root / ".wikimap" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def am(tmp_path_factory):
    base = tmp_path_factory.mktemp("areas")
    return open_map(_areas_repo(base), base / "data", exact=True)


def by_pair(lv):
    return {(e["s"], e["t"]): e for e in lv["edges"]}


def test_areas_open_at_the_systems_root(am):
    lv = am.level("systems", ".")
    ids = {n["id"] for n in lv["nodes"]}
    assert {"core", "web", "svc", "tools/fmt", "extra", "proto"} <= ids
    assert not ids & {"platform", "backend", "tools"}  # boxes are not blocks; the emptied dir group is gone
    tags = {n["id"]: n.get("area") for n in lv["nodes"]}
    assert tags["core"] == tags["web"] == "platform" and tags["svc"] == tags["tools/fmt"] == "backend"
    assert tags["extra"] is None
    assert [(a["id"], a["title"], sorted(a["members"])) for a in lv["areas"]] == [
        ("backend", "Backend", ["svc", "tools/fmt"]), ("platform", "Platform", ["core", "web"])]


def test_root_edges_join_members_never_boxes(am):
    lv = am.level("systems", ".")
    for e in lv["edges"]:
        assert e["s"] not in am.areas and e["t"] not in am.areas
    e = by_pair(lv)
    assert e[("core", "svc")]["labels"] == ["Sample · call · 1/s"]  # poly.md's edge, across two boxes
    assert e[("core", "web")]["labels"] == ["Sample"]  # the Platform area's own diagram


def test_members_reparent_in_systems_only(am):
    assert am.parent_of("core", "systems") == "platform" and am.parent_of("core", "code") == "."
    assert am.chain("core/geo", "systems") == [".", "platform", "core", "core/geo"]
    assert am.chain("core/geo", "code") == [".", "core", "core/geo"]
    assert "platform" not in am.children["."]
    code_root = {n["id"] for n in am.level("code", ".")["nodes"]}
    assert "tools" in code_root and "platform" not in code_root  # the Code lens keeps the physical tree
    assert am.level("code", "platform") is None and am.level("systems", "tools") is None
    assert am.level("code", "tools")["nodes"]  # the emptied group's code is still reachable
    row = next(n for n in am.index()["nodes"] if n["id"] == "core")
    assert row["sp"] == "platform" and row["parent"] == "."


def test_area_level_and_crumbs(am):
    lv = am.level("systems", "platform")
    assert {n["id"] for n in lv["nodes"]} == {"core", "web"}
    assert [c["id"] for c in lv["crumbs"]] == [".", "platform"]
    assert [c["id"] for c in am.level("systems", "core")["crumbs"]] == [".", "platform", "core"]
    assert "ghost:svc" in {g["id"] for g in lv["ghosts"]}
    assert am.nodes["platform"]["summary"] == "What the user touches."


def test_root_diagram_names_areas_and_undrawn(am):
    t = T.load_tree(am.root, modgate=True, config=T.load_config(am.root))
    assert T.resolve_ref(t, ".", "platform", "P") == "platform"
    lines = [f.line() for f in am.findings if f.code == "UNDRAWN"]
    assert any(" fmt " in x and "poly.system_map.md" in x for x in lines)  # a member missing from its area diagram
    assert any("Platform" in x and "poly.md" in x for x in lines)  # the root diagram should draw the areas


def test_boundary_edges_continue_into_the_child(am):
    """core → svc at the root lands, inside svc, on the child that takes it (never dropped, never own code)."""
    lv = am.level("systems", "svc")
    e = by_pair(lv)
    assert e[("ghost:core", "svc/pkg")]["labels"] == ["Sample · call · 1/s"]
    assert e[("ghost:web", "svc/pkg")]["labels"] == ["GET /v1/latest"]
    assert {"core", "web"} <= {g["peer"] for g in lv["ghosts"]}


def test_no_systems_key_is_unchanged(tmp_path):
    plain = build_map(_areas_repo(tmp_path / "a", None), tmp_path / "da", exact=True)
    empty = build_map(_areas_repo(tmp_path / "b", {"systems": {}}), tmp_path / "db", exact=True)
    for lens, at in (("systems", "."), ("systems", "svc"), ("code", "."), ("code", "core")):
        a, b = plain.level(lens, at), empty.level(lens, at)
        a.pop("rev"), b.pop("rev")
        assert a == b, (lens, at)
    assert not plain.sparent and not plain.areas and "areas" not in plain.level("systems", ".")


def test_two_builds_give_the_same_levels(tmp_path):
    one = open_map(_areas_repo(tmp_path / "a"), tmp_path / "da", exact=True)
    two = open_map(_areas_repo(tmp_path / "b"), tmp_path / "db", exact=True)
    for lens, at in (("systems", "."), ("systems", "platform"), ("systems", "svc"), ("code", ".")):
        a, b = one.level(lens, at), two.level(lens, at)
        a.pop("rev"), b.pop("rev")
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), (lens, at)


def test_show_text_groups_by_area(am):
    text = am.show_text("systems", ".")
    assert "  [Backend]  area/backend\n    fmt " in text and "  [Platform]  area/platform\n    core " in text


def test_bad_area_specs_are_ignored(tmp_path):
    cfg = {"systems": {"areas": [{"id": "Bad Id", "members": ["core"]}, {"id": "core", "members": ["web"]},
                                 {"id": "ok", "members": ["nope", "web"]}, "junk"]}}
    m = open_map(_areas_repo(tmp_path / "r", cfg), tmp_path / "d", exact=True)
    assert set(m.areas) == {"ok"} and m.areas["ok"]["members"] == ["web"] and m.areas["ok"]["missing"] == ["nope"]

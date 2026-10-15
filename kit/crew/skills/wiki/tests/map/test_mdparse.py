"""wikimap.mdparse: YAML subset, Markdown structure, Mermaid flowcharts, module doc readers."""
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[2] / "scripts"
EXAMPLE = HERE.parents[6] / "example" / "weather-station"


def _load():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    try:
        from wikimap import mdparse
    except Exception:  # package __init__ may be mid-build elsewhere: load the package shell without running it
        for k in [k for k in sys.modules if k == "wikimap" or k.startswith("wikimap.")]:
            del sys.modules[k]
        pkg = types.ModuleType("wikimap")
        pkg.__path__ = [str(SCRIPTS / "wikimap")]
        sys.modules["wikimap"] = pkg
        from wikimap import mdparse
    return mdparse


md = _load()


# ---------- YAML subset and frontmatter ----------

def test_frontmatter_scalars_lists_and_body_line():
    text = "---\ntitle: \"A: b\"\nkind: code   # comment\ndeps: [x, 'y', z]\nsources:\n  - src\n  - include/\nversion: 3\n" \
           "status: approved\nempty:\n---\n# Head\n"
    fm, body = md.frontmatter(text)
    assert fm == {"title": "A: b", "kind": "code", "deps": ["x", "y", "z"], "sources": ["src", "include/"],
                  "version": 3, "status": "approved", "empty": None}
    assert body == 12
    assert text.split("\n")[body - 1] == "# Head"


def test_frontmatter_absent_bom_crlf_and_empty():
    assert md.frontmatter("# no fm\n") == ({}, 1)
    fm, body = md.frontmatter("﻿---\r\nkind: system\r\ndeps: []\r\n---\r\nbody\r\n")
    assert fm == {"kind": "system", "deps": []} and body == 5
    assert md.frontmatter("---\n---\nx") == ({}, 3)
    assert md.frontmatter("---\nnot closed\n") == ({}, 1)


def test_yaml_lite_modgate_shapes():
    text = ("project: poly\ncriticality: L1\nvendor: [vendor, \"third/party\"]   # opaque\nignore: [\"*.tmp\"]\n"
            "targets:\n  linux-sim: \"sh {root}/run.sh # not a comment\"\n  host: python3 -m pytest -q  # yes\n"
            "presets:\n  L1:\n    ai_may_approve: [icd, tests]\nlist:\n- a\n- b: 1\n  c: 2\n")
    y = md.yaml_lite(text)
    assert y["project"] == "poly" and y["criticality"] == "L1"
    assert y["vendor"] == ["vendor", "third/party"] and y["ignore"] == ["*.tmp"]
    assert y["targets"] == {"linux-sim": "sh {root}/run.sh # not a comment", "host": "python3 -m pytest -q"}
    assert y["presets"] == {"L1": {"ai_may_approve": ["icd", "tests"]}}
    assert y["list"] == ["a", {"b": 1, "c": 2}]
    assert md.yaml_lite("") == {} and md.yaml_lite("- just\n- a list\n") == {}
    assert md.yaml_lite(":::\n\t\tweird: [\n") is not None  # never raises


# ---------- Markdown structure ----------

DOC = """---
title: t
---
# Title

## Subsystems and interactions
```mermaid
flowchart LR
  A --> B
```

~~~python
# not a heading
x = 1
~~~

### API
````cpp
int f();
```
still inside
````
"""


def test_headings_and_fences():
    assert md.headings(DOC) == [(1, "Title", 4), (2, "Subsystems and interactions", 6), (3, "API", 17)]
    fences = md.code_fences(DOC)
    assert [(f["lang"], f["line"], f["heading"]) for f in fences] == [
        ("mermaid", 7, "Subsystems and interactions"), ("python", 12, "Subsystems and interactions"), ("cpp", 18, "API")]
    assert fences[1]["body"] == "# not a heading\nx = 1"
    assert fences[2]["body"] == "int f();\n```\nstill inside"
    blocks = md.mermaid_blocks(DOC)
    assert blocks == [{"line": 7, "heading": "Subsystems and interactions", "src": "flowchart LR\n  A --> B"}]
    assert md.code_fences("```js\nunterminated\n")[0]["body"] == "unterminated"


def test_summary_title_and_first_heading():
    text = "---\ntitle: From FM\n---\n# Head\n\n> quote\n\n| t |\n|---|\n\nFirst **real** [para](x.md)\nwraps `here`.\n\nNext.\n"
    assert md.summary(text) == "First real para wraps here."
    assert md.doc_title(text, "fb") == "From FM"
    assert md.doc_title("## Only h2\n", "fb") == "Only h2"
    assert md.doc_title("plain\n", "fb") == "fb"
    assert md.summary("x" * 300).endswith("…") and len(md.summary("x" * 300)) == 200


# ---------- Mermaid ----------

ARROWS = """flowchart LR
  A1 --> B1
  A2 --- B2
  A3 -.-> B3
  A4 ==> B4
  A5 -- "quoted label" --> B5
  A6 -- plain label --> B6
  A7 -->|pipe label| B7
  A8 -. dotted label .-> B8
  A9 -. "dotted quoted" .-> B9
  A10 -->|"pipe quoted"| B10
  A11 == thick label ==> B11
  A12 ---> B12
"""


def test_every_arrow_form():
    f = md.parse_flowchart(ARROWS)
    got = {(e["s"], e["t"]): (e["label"], e["dash"], e["thick"]) for e in f["edges"]}
    assert got == {
        ("A1", "B1"): ("", False, False), ("A2", "B2"): ("", False, False), ("A3", "B3"): ("", True, False),
        ("A4", "B4"): ("", False, True), ("A5", "B5"): ("quoted label", False, False),
        ("A6", "B6"): ("plain label", False, False), ("A7", "B7"): ("pipe label", False, False),
        ("A8", "B8"): ("dotted label", True, False), ("A9", "B9"): ("dotted quoted", True, False),
        ("A10", "B10"): ("pipe quoted", False, False), ("A11", "B11"): ("thick label", False, True),
        ("A12", "B12"): ("", False, False)}
    assert f["skipped"] == 0 and f["dir"] == "LR"
    assert [e["line"] for e in f["edges"]] == list(range(2, 14))


def test_node_shapes_quotes_and_labels():
    src = """graph TD
  A[box] --> B(round)
  C[(cyl db)] --> D{decide}
  E{{hex}} --> F((circle))
  G>flag] --> H["quoted (with parens)"]
  I["a &amp; b<br/>second <b>bold</b>"] --> J[("telemetry_db · SQLite")]
  K([stadium]) --> L[[sub]]
  M[/para/] --> N(("dbl"))
"""
    f = md.parse_flowchart(src)
    labels = {k: v["label"] for k, v in f["nodes"].items()}
    assert labels == {"A": "box", "B": "round", "C": "cyl db", "D": "decide", "E": "hex", "F": "circle",
                      "G": "flag", "H": "quoted (with parens)", "I": "a & b\nsecond bold",
                      "J": "telemetry_db · SQLite", "K": "stadium", "L": "sub", "M": "para", "N": "dbl"}
    assert f["skipped"] == 0 and f["dir"] == "TD" and len(f["edges"]) == 7


def test_chains_cartesian_and_semicolons():
    f = md.parse_flowchart("flowchart LR\n  A --> B -- x --> C\n  P & Q -. uses .-> R & S\n  X --> Y; Y --> Z\n")
    pairs = [(e["s"], e["t"], e["label"]) for e in f["edges"]]
    assert pairs == [("A", "B", ""), ("B", "C", "x"), ("P", "R", "uses"), ("P", "S", "uses"), ("Q", "R", "uses"),
                     ("Q", "S", "uses"), ("X", "Y", ""), ("Y", "Z", "")]
    assert all(e["dash"] for e in f["edges"][2:6])


def test_subgraphs_members_and_endpoints():
    src = """flowchart LR
  subgraph FW["firmware (system)"]
    S1["sensing"] --> S2
    subgraph IN [inner box]
      S3
    end
  end
  subgraph BE
    ING
  end
  subgraph Free text title
    Z
  end
  X -.-> FW
  ING --> BE
"""
    f = md.parse_flowchart(src, 10)
    assert set(f["subgraphs"]) == {"FW", "IN", "BE", "Free text title"}
    assert f["subgraphs"]["FW"] == {"label": "firmware (system)", "members": ["S1", "S2", "IN"], "line": 12, "ext": False}
    assert f["subgraphs"]["IN"]["label"] == "inner box" and f["subgraphs"]["IN"]["members"] == ["S3"]
    assert f["subgraphs"]["BE"]["label"] == "BE" and f["subgraphs"]["BE"]["members"] == ["ING"]
    assert "FW" not in f["nodes"] and "BE" not in f["nodes"]
    assert ("X", "FW") in [(e["s"], e["t"]) for e in f["edges"]]
    assert f["nodes"]["S1"]["line"] == 13 and f["nodes"]["S2"]["label"] == "S2"


def test_ext_classes_ignored_lines_and_skipped():
    src = """flowchart LR
  %% a comment
  OP["Operator"]:::ext -.-> WEB["web"]
  U["User"] --> WEB
  class U,V ext
  V
  classDef ext stroke-dasharray: 4 3
  style WEB fill:#fff
  linkStyle 0 stroke:#f00
  click WEB "https://example.com"
  this is not mermaid !!
  A -->
  end
"""
    f = md.parse_flowchart(src)
    assert {k for k, v in f["nodes"].items() if v["ext"]} == {"OP", "U", "V"}
    assert f["nodes"]["WEB"]["ext"] is False
    assert f["skipped"] == 3
    assert len(f["edges"]) == 2


def test_pick_diagram_prefers_interaction_heading():
    text = ("# M\n\n## Sequence\n```mermaid\nsequenceDiagram\n  A->>B: hi\n```\n\n## Detail\n```mermaid\nflowchart LR\n"
            "  A --> B\n```\n\n## Architecture\n```mermaid\n%% note\ngraph TB\n  C --> D\n```\n")
    flow, line = md.pick_diagram(text)
    assert line == 16 and [(e["s"], e["t"]) for e in flow["edges"]] == [("C", "D")]
    assert flow["edges"][0]["line"] == 19
    flow, line = md.pick_diagram(text.replace("## Architecture", "## Other"))
    assert line == 10 and flow["edges"][0]["s"] == "A"
    assert md.pick_diagram("# none\n") == (None, 0)
    assert md.pick_diagram("```mermaid\npie\n  \"a\": 1\n```\n") == (None, 0)


def test_label_candidates_and_norm():
    assert md.norm("Deploy-Prod / X!") == "deploy_prod/x"
    assert md.label_head("adapters: hal_linux_sim · osal_posix") == "adapters"
    assert md.label_head("sensing<br/>humidity_sensor") == "sensing"
    assert md.label_head("telemetry_db · SQLite") == "telemetry_db"
    assert md.label_candidates("station (firmware/comms)", "ST") == ["station", "firmware/comms", "stationfirmware/comms", "st"]
    assert md.label_candidates("StorageGuard (this module)\nwires the two", "G") == [
        "storageguard", "thismodule", "storageguardthismodule", "g"]
    assert md.label_candidates("deploy/prod", "PROD") == ["deploy/prod", "prod"]
    assert md.label_candidates("ports", "PORTS") == ["ports"]


# ---------- module doc readers ----------

def test_bind_req_and_trace_readers():
    assert md.bind_yaml("REQ-A-001: [src/a.c, config/]\nREQ-A-002:\n  - test/t.c\nREQ-A-003: []\n# c\n") == {
        "REQ-A-001": ["src/a.c", "config"], "REQ-A-002": ["test/t.c"], "REQ-A-003": []}
    text = ("---\ntitle: r\n---\n# r\n\n- **REQ-X-001** (parents: FEAT-X-001, REQ-S-002) — Raise `LOW` when **low**.\n"
            "  continuation\n- **REQ-X-002** — No parents.\n```\n- **REQ-X-003** — in a fence\n```\n")
    r = md.req_lines(text)
    assert r == {"REQ-X-001": {"title": "Raise LOW when low.", "parents": ["FEAT-X-001", "REQ-S-002"], "line": 6},
                 "REQ-X-002": {"title": "No parents.", "parents": [], "line": 8}}
    assert md.trace_state("# t\n\nState: **unreviewed change** · module `x`\n") == "unreviewed change"
    assert md.trace_state("nothing") is None


# ---------- the example's diagrams ----------

@pytest.mark.parametrize("rel", ["weather-station.md", "firmware/firmware.md", "backend/backend.md",
                                 "firmware/sensing/sensing.md", "firmware/storage/storage.md"])
def test_example_diagrams_parse_cleanly(rel):
    flow, line = md.pick_diagram((EXAMPLE / rel).read_text(encoding="utf-8"))
    assert flow is not None and line > 0 and flow["skipped"] == 0 and flow["edges"]


def test_example_firmware_cartesian_and_labels():
    flow, _ = md.pick_diagram((EXAMPLE / "firmware/firmware.md").read_text(encoding="utf-8"))
    to_ports = [e for e in flow["edges"] if e["t"] == "PORTS"]
    assert sorted(e["s"] for e in to_ports) == ["ADP", "COMMS", "SENS", "STOR"]
    amp = [e for e in to_ports if e["s"] != "ADP"]
    assert len(amp) == 3 and all(e["dash"] and e["label"] == "hal_ports · osal_ports" for e in amp)
    labels = [e["label"] for e in flow["edges"] if (e["s"], e["t"]) == ("SENS", "STOR")]
    assert labels == ["Reading every 60 s", "LOW_BATTERY"]


# ---------- untrusted input stays cheap ----------

def _fast(fn, limit=1.0):
    import time
    t = time.perf_counter()
    out = fn()
    assert time.perf_counter() - t < limit
    return out


def test_ampersand_fan_out_is_capped():
    left = " & ".join(f"N{i}" for i in range(1500))
    right = " & ".join(f"M{i}" for i in range(1500))
    f = _fast(lambda: md.parse_flowchart(f"flowchart LR\n  A & B --> C & D\n  {left[:4000]} --> X\n"
                                         f"  {' & '.join(f'K{i}' for i in range(300))} --> {' & '.join(f'L{i}' for i in range(300))}\n"))
    assert len(f["edges"]) <= 4 + 16 + md.MAX_FAN * md.MAX_FAN and f["skipped"] >= 1
    assert {(e["s"], e["t"]) for e in f["edges"]} >= {("A", "C"), ("A", "D"), ("B", "C"), ("B", "D")}
    huge = _fast(lambda: md.parse_flowchart(f"flowchart LR\n  {left} --> {right}\n"))
    assert huge["edges"] == [] and huge["skipped"] == 1


def test_long_heading_and_parents_lines_are_linear():
    assert md.headings("## a" + " " * 60000 + "x\n") == [(2, "a" + " " * 60000 + "x", 1)]
    assert _fast(lambda: md.headings("## a" + " " * 60000 + "x\n## b ##\n# c#\n"))[1:] == [(2, "b", 2), (1, "c#", 3)]
    _fast(lambda: md.req_lines("- **REQ-A-001** " + "(parents:" * 10000 + "\n"))
    assert md.req_lines("- **REQ-A-002** (parents: REQ-B-001, REQ-B-002) — text\n")["REQ-A-002"]["parents"] == \
        ["REQ-B-001", "REQ-B-002"]
    _fast(lambda: md.code_fences("```" + "a" * 50000 + "`\n"))

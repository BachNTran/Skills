import pytest

from modgate.analyze import Project
from modgate.approve import Rejected, approve
from modgate.project import read_frontmatter
from modgate.trace import load_state

from conftest import write

BY = "Tess Ter"


def codes(p: Project, name: str) -> list[str]:
    return [f"{f.code}:{f.id}" for f in p.analyze(p.modules[name]).pending]


def approved_project(proj) -> Project:
    p = Project(proj)
    p.sync(None, "unit")
    approve(p, "lib", "all", BY)
    approve(Project(proj), "app", "all", BY)
    return Project(proj)


@pytest.mark.req("REQ-MG-016")
def test_approve_all_round_trip(proj):
    p = approved_project(proj)
    lib = p.modules["lib"]
    fm = read_frontmatter(lib.doc("req.md"))
    assert fm["status"] == "approved" and fm["approved_by"] == BY
    assert str(fm["approved"]).startswith("1 sha256:")
    st = load_state(lib.trace_path)
    assert st["module_hash"] == p.module_hash(lib)
    assert set(st["reqs"]) == {"REQ-LIB-001", "REQ-LIB-002"}
    assert "src/add.py" in st["files"]
    assert p.analyze(lib).status == "verified"
    assert p.analyze(p.modules["app"]).status == "verified"
    log = lib.doc("changelog.md").read_text()
    assert "· all · Tess Ter" in log and "APPROVED lib.req.md v1" in log


@pytest.mark.req("REQ-MG-016")
def test_default_approver_is_git_user(git_proj):
    p = Project(git_proj)
    out = approve(p, "lib", "brief", None)
    assert out[0].endswith("by Tess Ter")


@pytest.mark.req("REQ-MG-016")
def test_approving_one_doc_clears_only_that_draft(proj):
    p = Project(proj)
    approve(p, "lib", "brief", BY)
    pend = codes(Project(proj), "lib")
    assert "DRAFT:lib.brief.md v1" not in pend
    assert "DRAFT:lib.req.md v1" in pend


@pytest.mark.req("REQ-MG-007")
def test_code_change_without_req_change_is_drift(proj):
    p = approved_project(proj)
    write(proj, {"lib/src/check.py": "def check(a):\n    return a > 0\n"})
    p = Project(proj)
    a = p.analyze(p.modules["lib"])
    drift = [f for f in a.pending if f.code == "DRIFT"]
    assert [(f.id, f.files) for f in drift] == [("REQ-LIB-002", ["src/check.py"])]
    assert not [f for f in a.pending if f.code == "STALE"]
    assert a.status == "unreviewed change"


@pytest.mark.req("REQ-MG-007")
def test_drift_cleared_by_req_review(proj):
    approved_project(proj)
    write(proj, {"lib/src/check.py": "def check(a):\n    return a > 0\n"})
    approve(Project(proj), "lib", "REQ-LIB-002", BY)
    p = Project(proj)
    assert "DRIFT:REQ-LIB-002" not in codes(p, "lib")
    st = load_state(p.modules["lib"].trace_path)
    assert st["module_hash"] == p.module_hash(p.modules["lib"])
    assert "REVIEWED REQ-LIB-002" in p.modules["lib"].doc("changelog.md").read_text()


@pytest.mark.req("REQ-MG-007")
def test_drift_cleared_by_revisiting_the_requirement(proj):
    approved_project(proj)
    write(proj, {"lib/src/check.py": "def check(a):\n    return a > 0\n"})
    req = proj / "lib/docs/lib.req.md"
    req.write_text(req.read_text().replace("Reject negative input.", "Reject zero and negative input.")
                   .replace("status: approved", "status: draft").replace("version: 1", "version: 2"))
    p = Project(proj)
    pend = codes(p, "lib")
    assert "DRIFT:REQ-LIB-002" not in pend and "DRAFT:lib.req.md v2" in pend
    approve(p, "lib", "req", BY)
    p = Project(proj)
    assert codes(p, "lib") == ["UNTESTED:unit", "BACKLOG:FEAT-LIB-002"]


@pytest.mark.req("REQ-MG-008")
def test_unbound_source(proj):
    write(proj, {"lib/src/orphan.py": "x = 1\n"})
    p = Project(proj)
    a = p.analyze(p.modules["lib"])
    assert [f.files for f in a.findings if f.code == "UNBOUND"] == [["src/orphan.py"]]


@pytest.mark.req("REQ-MG-008")
def test_bind_directory_entry_and_bad_bind(proj):
    write(proj, {
        "lib/docs/lib.bind.yaml": "REQ-LIB-001: [src/]\nREQ-LIB-009: [src/gone.py]\n",
    })
    p = Project(proj)
    a = p.analyze(p.modules["lib"])
    assert not [f for f in a.findings if f.code == "UNBOUND"]
    assert {f.id for f in a.findings if f.code == "BADBIND"} == {"REQ-LIB-009"}


@pytest.mark.req("REQ-MG-023")
def test_unexplained_change_is_stale(proj):
    approved_project(proj)
    write(proj, {"lib/src/check.py": "def check(a):\n    return a >= 0\n", "lib/notes.txt": "extra\n"})
    p = Project(proj)
    a = p.analyze(p.modules["lib"])
    stale = [f for f in a.pending if f.code == "STALE"]
    assert stale and stale[0].files == ["notes.txt"]
    assert a.status == "stale"


@pytest.mark.req("REQ-MG-023")
def test_dependency_change_then_retest_rebaselines(proj):
    approved_project(proj)
    write(proj, {"app/app.md": (proj / "app/app.md").read_text().replace("\nkind: code", "\nkind: code\ntargets: [unit]")})
    p = Project(proj)
    p.sync(["app"], "unit")
    write(proj, {"lib/src/add.py": "def add(a, b):\n    return b + a\n"})
    p = Project(proj)
    a = p.analyze(p.modules["app"])
    assert a.status == "dependency changed"
    dep = [f for f in a.pending if f.code == "DEPCHANGED"][0]
    assert dep.id == "lib" and "ICD unchanged" in dep.action
    p.sync(["app"], "unit")
    p = Project(proj)
    assert p.analyze(p.modules["app"]).status == "verified"


@pytest.mark.req("REQ-MG-023")
def test_dependency_icd_change_needs_deep_review(proj):
    write(proj, {"lib/docs/lib.icd.md": "---\nversion: 1\nstatus: draft\n---\n# ICD\nadd(a, b)\n"})
    approved_project(proj)
    write(proj, {"lib/docs/lib.icd.md": "---\nversion: 2\nstatus: draft\n---\n# ICD\nadd(a, b, c)\n"})
    p = Project(proj)
    dep = [f for f in p.analyze(p.modules["app"]).pending if f.code == "DEPCHANGED"][0]
    assert "deep review" in dep.action


@pytest.mark.req("REQ-MG-015")
def test_ai_reviewer_rejected_above_allowed_level(proj):
    p = Project(proj)
    with pytest.raises(Rejected, match="E:APPROVER"):
        approve(p, "lib", "req", "ai-reviewer:some-model")
    assert approve(p, "lib", "bind", "ai-reviewer:some-model")


@pytest.mark.req("REQ-MG-009")
def test_trace_regenerated_state_preserved_and_stable(proj):
    p = approved_project(proj)
    trace = p.modules["lib"].trace_path
    text = trace.read_text()
    approved_hash = load_state(trace)["module_hash"]
    assert text.startswith("# lib · trace\n\nState: **verified**")
    assert "| FEAT-LIB-001 | REQ-LIB-001 | `test/test_add.py::test_adds` | ✓ pass (3 passed) |" in text
    assert "modgate-state:" in text
    mtime = trace.stat().st_mtime_ns
    Project(proj).sync(None)
    assert trace.stat().st_mtime_ns == mtime
    write(proj, {"lib/src/check.py": "def check(a):\n    return a > 0\n"})
    Project(proj).sync(None)
    assert "**unreviewed change**" in trace.read_text()
    assert load_state(trace)["module_hash"] == approved_hash and "unit" in load_state(trace)["tests"]

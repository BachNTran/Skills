import re

import pytest

from modgate.trace import load_state

from conftest import write

LINE = re.compile(r"^(E:)?[A-Z]+\s+\S+(\s{2}.*)?$")


def approve_all(run):
    assert run("sync", "--test", "unit").code == 0
    assert run("approve", "lib", "all", "--by", "T").code == 0
    assert run("approve", "app", "all", "--by", "T").code == 0


@pytest.mark.req("REQ-MG-018")
def test_sync_is_silent_on_success(proj, run):
    r = run("sync")
    assert (r.code, r.out) == (0, "")


@pytest.mark.req("REQ-MG-018")
def test_exit_codes_findings_violations_strict(proj, run):
    write(proj, {"lib/src/orphan.py": "x = 1\n"})
    r = run("sync")
    assert r.code == 1 and r.lines == ["UNBOUND     lib  src/orphan.py  → bind to a REQ in lib.bind.yaml"]
    assert run("sync", "--strict").code == 2
    write(proj, {"lib/README.md": "x\n"})
    assert run("sync").code == 2


@pytest.mark.req("REQ-MG-018")
def test_error_exit_3_outside_project(tmp_path, monkeypatch, run):
    monkeypatch.chdir(tmp_path)
    r = run("pending")
    assert r.code == 3 and "E:ERROR" in r.err


@pytest.mark.req("REQ-MG-018")
def test_json_only_when_asked(proj, run):
    write(proj, {"lib/src/orphan.py": "x = 1\n"})
    data = run("sync", "--json").json()
    assert data["findings"][0]["code"] == "UNBOUND" and data["findings"][0]["severity"] == "finding"
    sets = run("pending", "--json").json()["sets"]
    assert {f["code"] for s in sets for f in s} >= {"DRAFT", "UNTESTED", "BACKLOG"}


@pytest.mark.req("REQ-MG-017")
def test_pending_lines_and_codes(proj, run):
    r = run("pending")
    assert r.code == 1
    body = [x for x in r.lines if not x.startswith("#")]
    assert all(LINE.match(x) for x in body), body
    assert "DRAFT       lib  lib.req.md v1  → approve (developer, L2)" in body
    assert "BACKLOG     lib  FEAT-LIB-002  → multiply · after: approve" in body


@pytest.mark.req("REQ-MG-017")
def test_pending_groups_dependency_disjoint_sets(proj, run):
    write(proj, {
        "solo/solo.md": "---\nkind: code\ndeps: []\n---\n# solo\n",
        "solo/docs/solo.activity.md": "- [ ] FEAT-SOLO-001 · build it\n",
    })
    approve_all(run)
    write(proj, {"lib/src/check.py": "def check(a):\n    return a > 0\n"})
    r = run("pending")
    headers = [x for x in r.lines if x.startswith("# set")]
    assert headers == ["# set 1 · app lib", "# set 2 · solo"]
    assert any(x.startswith("DRIFT       lib  REQ-LIB-002  src/check.py") for x in r.lines)
    assert any(x.startswith("DEPCHANGED  app  lib") for x in r.lines)


@pytest.mark.req("REQ-MG-017")
def test_pending_clean_project(proj, run):
    approve_all(run)
    (proj / "lib/docs/lib.activity.md").write_text("# lib · activity\n\n- [x] FEAT-LIB-002 · done\n")
    r = run("pending")
    assert (r.code, r.out.strip()) == (0, "nothing open")


@pytest.mark.req("REQ-MG-011")
def test_test_target_records_latest_pass_with_env(proj, run):
    assert run("sync", "lib", "--test", "unit").code == 0
    rec = load_state(proj / "lib/docs/lib.trace.md")["tests"]["unit"]
    assert rec["result"] == "pass (3 passed)"
    assert {"os", "arch", "endianness", "python"} <= set(rec["env"])
    assert rec["module_hash"].startswith("sha256:") and len(rec["module_hash"]) == 71


@pytest.mark.req("REQ-MG-011")
def test_failing_target_keeps_previous_record(proj, run):
    write(proj, {"lib/lib.md": (proj / "lib/lib.md").read_text().replace("targets: [unit]", "targets: [unit, broken]")})
    r = run("sync", "lib", "--test", "broken")
    assert r.code == 1 and r.lines[0].startswith("TESTFAIL    lib  broken  → fail (exit 4)")
    assert "broken" not in (load_state(proj / "lib/docs/lib.trace.md").get("tests") or {})
    assert (proj / ".modgate/logs/lib.broken.log").is_file()


@pytest.mark.req("REQ-MG-011")
def test_unknown_target_is_an_error(proj, run):
    assert run("sync", "--test", "nope").code == 3


@pytest.mark.req("REQ-MG-020")
def test_report_written(proj, run):
    r = run("pending", "--report")
    path = proj / ".modgate/report.html"
    assert r.lines[-1] == str(path)
    html = path.read_text()
    assert "REQ-LIB-001" in html and "<code>app</code>" in html and "draft" in html


@pytest.mark.req("REQ-MG-016")
def test_approve_rejects_ai_reviewer_with_exit_2(proj, run):
    r = run("approve", "lib", "req", "--by", "ai-reviewer:model-x")
    assert r.code == 2 and r.out.startswith("E:APPROVER")
    assert run("approve", "lib", "nope", "--by", "T").code == 3

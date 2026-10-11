import json

import pytest

from conftest import write


def post_tool_use(path, cwd) -> str:
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "cwd": str(cwd),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(path)},
    })


@pytest.mark.req("REQ-MG-019")
def test_post_tool_use_reports_via_additional_context(proj, run):
    write(proj, {"lib/src/orphan.py": "x = 1\n"})
    r = run("sync", "--hook", stdin=post_tool_use(proj / "lib/src/orphan.py", proj))
    assert r.code == 0
    out = json.loads(r.out)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    assert "UNBOUND     lib  src/orphan.py" in out["additionalContext"]


@pytest.mark.req("REQ-MG-019")
def test_post_tool_use_only_syncs_the_edited_module(proj, run):
    write(proj, {"lib/src/orphan.py": "x = 1\n", "app/src/other.py": "y = 1\n"})
    r = run("sync", "--hook", stdin=post_tool_use(proj / "app/src/main.py", proj))
    ctx = json.loads(r.out)["hookSpecificOutput"]["additionalContext"]
    assert "app" in ctx and "lib" not in ctx
    assert (proj / "app/docs/app.trace.md").is_file()


@pytest.mark.req("REQ-MG-019")
def test_post_tool_use_silent_when_clean_or_outside(proj, tmp_path, run):
    assert run("sync", "--hook", stdin=post_tool_use(proj / "lib/src/add.py", proj)).out == ""
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x")
    r = run("sync", "--hook", stdin=post_tool_use(outside, tmp_path))
    assert (r.code, r.out) == (0, "")
    assert run("sync", "--hook", stdin="not json").code == 0


@pytest.mark.req("REQ-MG-019")
def test_stop_blocks_only_on_violations(proj, run):
    stop = json.dumps({"hook_event_name": "Stop", "cwd": str(proj), "stop_hook_active": False})
    write(proj, {"lib/src/orphan.py": "x = 1\n"})
    r = run("sync", "--hook", stdin=stop)
    assert (r.code, r.err) == (0, "")
    write(proj, {"lib/README.md": "x\n"})
    r = run("sync", "--hook", stdin=stop)
    assert r.code == 2 and "E:NAMING" in r.err and "UNBOUND" not in r.err
    again = json.dumps({"hook_event_name": "Stop", "cwd": str(proj), "stop_hook_active": True})
    assert run("sync", "--hook", stdin=again).code == 0


@pytest.mark.req("REQ-MG-019")
def test_session_start_context(proj, run):
    r = run("pending", "--hook", stdin=json.dumps({"hook_event_name": "SessionStart", "cwd": str(proj)}))
    assert r.code == 0
    out = json.loads(r.out)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    assert out["additionalContext"].startswith("modgate pending:\n# set 1")

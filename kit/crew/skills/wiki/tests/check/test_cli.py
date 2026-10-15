"""wikimap.cli: root/data dir, exit codes, check/map/sync/pending/ack/show/trace, install-hooks
(spec §7.3–§7.4, overrides O2/O3). FakeMap tests run now; real-Map tests skip until WP3 lands."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_fresh import FakeMap, PY, _isolate, mkdoc, run, std_map  # noqa: E402,F401

from wikimap import cli, fresh  # noqa: E402

ROOT_ERR = "E:ERROR     (root)  "
KIT_HOOKS = Path(__file__).resolve().parents[5] / "hooks.json"  # kit/hooks.json (modgate)


@pytest.fixture
def repo(tmp_path):
    r = (tmp_path / "repo").resolve()
    r.mkdir()
    (r / "modgate.yaml").write_text("project: demo\n")
    return r


@pytest.fixture
def fake(repo, monkeypatch):
    fm = std_map(repo)
    calls = []
    monkeypatch.setattr(cli, "_open", lambda root, data, **kw: calls.append((root, data)) or fm)
    fm.calls = calls
    return fm


def W(*argv):
    return run(cli, [str(a) for a in argv])


# ---- root and data dir ---------------------------------------------------------------------

def test_find_root_and_opt_in(tmp_path):
    g = tmp_path / "g"
    (g / ".git").mkdir(parents=True)
    (g / "a" / "b").mkdir(parents=True)
    assert cli.find_root(g / "a" / "b") == (g.resolve(), False)
    assert not cli.opted_in(g)
    (g / "a" / "modgate.yaml").write_text("project: a\n")
    assert cli.find_root(g / "a" / "b") == ((g / "a").resolve(), True)
    assert cli.opted_in(g / "a")
    (g / ".wikimap").mkdir()
    assert cli.opted_in(g)
    lone = tmp_path / "lone"
    lone.mkdir()
    assert cli.find_root(lone) == (lone.resolve(), False)


def test_data_dir_rules(tmp_path, monkeypatch):
    r = tmp_path / "r"
    r.mkdir()
    sha = hashlib.sha256(str(r.resolve()).encode()).hexdigest()[:12]
    cache = Path(str(tmp_path / "home" / ".cache"))
    assert cli.data_dir(r) == cache / "wiki" / sha
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert cli.data_dir(r) == tmp_path / "xdg" / "wiki" / sha
    assert cli.data_dir(r, str(tmp_path / "d")) == (tmp_path / "d").resolve()
    (r / ".gitignore").write_text("node_modules/\n.wiki/\n")
    assert cli.data_dir(r) == r / ".wiki"
    (r / ".gitignore").write_text("x\n")
    assert cli.data_dir(r) != r / ".wiki"
    (r / ".wiki").mkdir()
    assert cli.data_dir(r) == r / ".wiki"
    assert not (tmp_path / "xdg").exists()          # never creates anything


# ---- argument errors -----------------------------------------------------------------------

@pytest.mark.parametrize("extra", [[], ["--unchanged", "short"], ["--unchanged", "       x       "]])
def test_ack_needs_reason(repo, monkeypatch, extra):
    monkeypatch.setattr(cli, "_open", lambda *a: pytest.fail("ack validated after building"))
    code, out, err = W("ack", f"{PY}#area", repo, *extra)
    assert (code, out) == (3, "")
    assert err == ROOT_ERR + 'ack needs --unchanged "<reason>" (8+ chars)\n'


@pytest.mark.parametrize("argv", [["nope"], ["check", "--bogus"], ["show"], ["trace", "x", "--depth", "9"],
                                  ["check", ".", "--codes", "UNDOC,NOPE"]])
def test_bad_arguments_exit_3(repo, fake, monkeypatch, argv):
    monkeypatch.chdir(repo)
    code, out, err = W(*argv)
    assert code == 3 and err.startswith(ROOT_ERR)


def test_help_exits_0(capsys):
    assert cli.main(["check", "--help"]) == 0


# ---- commands on the fake map --------------------------------------------------------------

def test_check_without_baseline_shows_all_and_writes_nothing(repo, fake):
    code, out, err = W("check", repo)
    assert code == 1 and err == ""
    assert out.splitlines() == [f.line() for f in fresh.compute(fake, None)]
    assert not (repo / ".wikimap").exists()
    assert fake.calls[0][0] == repo


def test_check_exit_codes_and_filters(repo, fake):
    assert W("check", repo, "--strict")[0] == 2
    code, out, _ = W("check", repo, "--codes", "undoc")
    assert code == 1 and out.startswith("UNDOC       lib  helper")
    assert W("check", repo, "--codes", "ICDSYM")[:2] == (0, "")
    assert W("check", repo, "--codes", "ICDSYM", "--strict")[0] == 0
    out = W("check", repo, "--module", "app")[1]
    assert {ln.split()[0] for ln in out.splitlines()} == {"XCALL"}
    out = W("check", repo, "--module", "lib", "--file", PY, "--codes", "DOCSIG")[1]
    assert out.splitlines() == [next(f.line() for f in fresh.compute(fake, None) if f.code == "DOCSIG")]
    (repo / ".wikimap").mkdir()
    (repo / ".wikimap" / "config.json").write_text('{"violations": ["XCALL"]}')
    code, out, _ = W("check", repo)
    assert code == 2 and "E:XCALL     app  lib" in out


def test_check_json_shape(repo, fake):
    code, out, _ = W("check", repo, "--json")
    data = json.loads(out)
    assert code == 1 and isinstance(data, list) and len(data) == 7
    assert set(data[0]) == {"code", "severity", "module", "id", "files", "action", "node", "key"}
    assert W("check", repo, "--json", "--codes", "ICDSYM")[1].strip() == "[]"


def test_map_creates_baseline_once(repo, fake):
    code, out, _ = W("map", repo)
    lines = out.splitlines()
    assert code == 0 and lines[0] == "wiki: baseline created (11 symbols, 7 findings recorded as debt)"
    assert re.fullmatch(r"wiki: 4 modules · 0 files · 0 symbols · 0 edges \(75% ≥0\.8\) · 0 findings · \d+\.\d s",
                        lines[1])
    before = (repo / ".wikimap" / "baseline.json").read_text()
    code, out, _ = W("map", repo)
    assert code == 0 and len(out.splitlines()) == 1
    assert (repo / ".wikimap" / "baseline.json").read_text() == before
    assert W("check", repo)[:2] == (0, "")
    assert len(W("check", repo, "--all")[1].splitlines()) == 7


def test_corrupt_baseline_is_error(repo, fake):
    (repo / ".wikimap").mkdir()
    (repo / ".wikimap" / "baseline.json").write_text("<<<<<<< ours\n")
    for argv in (["check", repo], ["map", repo], ["sync", repo], ["pending", repo],
                 ["ack", f"{PY}#area", repo, "--unchanged", "reason long enough"]):
        code, out, err = W(*argv)
        assert (code, out, err) == (3, "", ROOT_ERR + ".wikimap/baseline.json unreadable: resolve the conflict\n")
    assert (repo / ".wikimap" / "baseline.json").read_text() == "<<<<<<< ours\n"


def test_sync_advances_and_check_changed(repo, fake):
    assert W("sync", repo)[1].startswith("wiki: baseline created")
    fake.edit(f"{PY}#area", body="b2")
    code, out, _ = W("check", repo, "--changed")
    assert code == 1 and out.startswith("DOCREVIEW   lib  area")
    assert W("check", repo, "--changed", "--file", "app/src/main.py")[:2] == (0, "")
    fake.edit(f"{PY}#area", doc=mkdoc("Area, checked.", {"w": "m", "h": "m"}, True))
    assert W("sync", repo)[:2] == (0, "")
    assert fresh.load_baseline(repo)["symbols"][f"{PY}#area"][1] == "b2"
    assert W("check", repo, "--changed")[:2] == (0, "")


def test_ack_flow(repo, fake):
    area = f"{PY}#area"
    code, _, err = W("ack", area, repo, "--unchanged", "reason long enough")
    assert code == 3 and err == ROOT_ERR + "no baseline yet  → run wiki map\n"
    W("map", repo)
    fake.edit(area, body="b3")
    assert W("check", repo)[1].startswith("DOCREVIEW")
    assert W("ack", "lib/src/calc.py:4", repo, "--unchanged", "renamed a local only")[:2] == (0, "wiki: acked area\n")
    acks = (repo / ".wikimap" / "acks.jsonl").read_text().splitlines()
    rec = json.loads(acks[0])
    assert len(acks) == 1 and set(rec) == {"ts", "key", "reason", "hashes"}
    assert rec["key"] == area and rec["hashes"][1] == "b3" and rec["reason"] == "renamed a local only"
    assert W("check", repo)[:2] == (0, "")
    code, _, err = W("ack", f"{PY}#helper", repo, "--unchanged", "reason long enough")
    assert (code, err) == (3, ROOT_ERR + "helper has no doc; write one\n")
    code, _, err = W("ack", "no_such_thing", repo, "--unchanged", "reason long enough")
    assert (code, err) == (3, ROOT_ERR + "no_such_thing matches no symbol\n")


def test_pending_lines(repo, fake):
    code, out, _ = W("pending", repo)
    lines = out.splitlines()
    assert code == 1 and lines[0].startswith("XCALL       app  lib") and lines[1].startswith("DOCSIG      lib")
    assert "UNDOC       lib  1 symbols  → wiki check --module lib" in lines
    assert "UNDRAWN     demo  2 findings  → wiki check --module demo" in lines
    many = [fresh.Finding("UNDOC", "finding", f"m{i}", "x", [], "") for i in range(12)]
    cut = cli.pending_lines(many)
    assert len(cut) == 8 and cut[-1] == "… 5 more  → wiki check"


def test_show_and_trace_delegate(repo, fake):
    code, out, _ = W("show", ".", repo)
    assert code == 0 and out.startswith("demo  [systems]  at .")
    code, out, _ = W("show", PY, repo)               # file with children: its own code level
    assert code == 0 and out.startswith("calc.py  [code]")
    code, out, _ = W("show", f"{PY}#area", repo)     # leaf: parent level, leaf marked
    assert code == 0 and "* area  symbol" in out.splitlines()
    assert W("show", "nowhere", repo)[0] == 3
    assert W("trace", "area", repo, "--in", "--depth", "3")[1] == f"trace {PY}#area in 3\n"
    assert W("trace", f"{PY}#area", repo)[1] == f"trace {PY}#area both 2\n"


# ---- install-hooks -------------------------------------------------------------------------

def _modgate_settings() -> dict:
    data = json.loads(KIT_HOOKS.read_text()) if KIT_HOOKS.is_file() else {
        "hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "modgate sync --hook"}]}]},
        "permissions": {"ask": ["Bash(modgate approve:*)"]}}
    data["model"] = "sonnet"
    data["env"] = {"Ü": "ß"}
    return data


def test_install_hooks_plan_write_idempotent(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    st = proj / ".claude" / "settings.json"
    before = _modgate_settings()
    st.write_text(json.dumps(before, indent=2, ensure_ascii=False) + "\n")
    raw = st.read_bytes()
    cmd = f'python3 "{cli.WIKI_PY}"'
    code, out, _ = W("install-hooks", proj)
    assert code == 0 and out.splitlines() == [f"would add: SessionStart {cmd} pending --hook",
                                              f"would add: PostToolUse {cmd} sync --hook"]
    assert st.read_bytes() == raw
    code, out, _ = W("install-hooks", proj, "--write")
    assert (code, out) == (0, f"wiki: hooks installed in {st}\n")
    after = json.loads(st.read_text())
    expect = json.loads(raw)
    snippet = json.loads(cli.HOOKS_JSON.read_text())
    for event, groups in snippet["hooks"].items():
        for g in groups:
            for h in g["hooks"]:
                h["command"] = h["command"].replace(cli.PROJECT_CMD, cmd)
        expect["hooks"].setdefault(event, []).extend(groups)
    assert after == expect
    assert st.read_text() == json.dumps(expect, indent=2, ensure_ascii=False) + "\n"
    assert after["permissions"] == before["permissions"] and after["model"] == "sonnet"
    raw2 = st.read_bytes()
    assert W("install-hooks", proj, "--write")[:2] == (0, "wiki: hooks already installed\n")
    assert W("install-hooks", proj)[:2] == (0, "wiki: hooks already installed\n")
    assert st.read_bytes() == raw2
    assert [p.name for p in st.parent.iterdir()] == ["settings.json"]


def test_install_hooks_project_copy_and_user(tmp_path):
    proj = tmp_path / "proj2"
    local = proj / ".claude" / "skills" / "wiki" / "scripts" / "wiki.py"
    local.parent.mkdir(parents=True)
    local.write_text("# copy\n")
    W("install-hooks", proj, "--write")
    cmds = [h["command"] for gs in json.loads((proj / ".claude" / "settings.json").read_text())["hooks"].values()
            for g in gs for h in g["hooks"]]
    assert cmds == [f"{cli.PROJECT_CMD} pending --hook", f"{cli.PROJECT_CMD} sync --hook"]
    assert "permissions" not in json.loads((proj / ".claude" / "settings.json").read_text())
    user = Path.home() / ".claude" / "settings.json"
    assert str(Path.home()).startswith(str(tmp_path))     # tmp HOME
    # no current copy of the skill under ~/.claude/skills/wiki: refuse, write nothing
    code, _, err = W("install-hooks", "--user", "--write")
    assert code == 3 and "no wikimap" in err and not user.exists()
    copy = Path.home() / ".claude" / "skills" / "wiki" / "scripts" / "wikimap" / "cli.py"
    copy.parent.mkdir(parents=True)
    copy.write_text("# copy\n")
    code, out, _ = W("install-hooks", "--user", "--write")
    assert (code, out) == (0, f"wiki: hooks installed in {user}\n")
    data = json.loads(user.read_text())
    cmd = data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert cmd == cli.user_hook(" sync --hook") and '[ -f "$f" ]' in cmd and cmd.endswith("|| true")
    assert data["hooks"]["SessionStart"][0]["hooks"][0]["timeout"] == 30
    assert oct(user.stat().st_mode & 0o777) == "0o644"


def test_user_hook_command_is_silent_without_the_copy(tmp_path):
    import subprocess
    home = tmp_path / "nohome"
    home.mkdir()
    r = subprocess.run(["sh", "-c", cli.user_hook(" sync --hook")], env={"HOME": str(home), "PATH": os.environ["PATH"]},
                       input="{}", capture_output=True, text=True, timeout=30)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    old = home / ".claude" / "skills" / "wiki" / "scripts" / "wiki.py"   # an older wiki without the command
    old.parent.mkdir(parents=True)
    old.write_text("import sys\nprint('usage', file=sys.stderr)\nsys.exit(2)\n")
    r = subprocess.run(["sh", "-c", cli.user_hook(" sync --hook")], env={"HOME": str(home), "PATH": os.environ["PATH"]},
                       input="{}", capture_output=True, text=True, timeout=30)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_install_hooks_writes_through_a_symlink_and_keeps_mode(tmp_path):
    proj = tmp_path / "proj4"
    (proj / ".claude").mkdir(parents=True)
    real = tmp_path / "dotfiles" / "settings.json"
    real.parent.mkdir()
    real.write_text('{"model": "x"}\n')
    real.chmod(0o664)
    (proj / ".claude" / "settings.json").symlink_to(real)
    assert W("install-hooks", proj, "--write")[0] == 0
    assert (proj / ".claude" / "settings.json").is_symlink()
    data = json.loads(real.read_text())
    assert data["model"] == "x" and "PostToolUse" in data["hooks"]
    assert oct(real.stat().st_mode & 0o777) == "0o664"


def test_install_hooks_refuses_bad_settings(tmp_path):
    proj = tmp_path / "proj3"
    (proj / ".claude").mkdir(parents=True)
    st = proj / ".claude" / "settings.json"
    for bad in ("{oops", "[]", '{"hooks": []}'):
        st.write_text(bad)
        code, _, err = W("install-hooks", proj, "--write")
        assert code == 3 and err.startswith(ROOT_ERR) and st.read_text() == bad


# ---- real Map (waits for WP1–WP3) ----------------------------------------------------------

def _need_map():
    wm = pytest.importorskip("wikimap")
    if not hasattr(wm, "open_map"):
        pytest.skip("wikimap.open_map not landed")


def _fixture(request, name):
    _need_map()
    try:
        return Path(request.getfixturevalue(name))
    except pytest.FixtureLookupError:
        pytest.skip(f"conftest {name} fixture not landed")


CALC = '''"""Calc helpers."""


def area(w, h):
    """Return the area of a w by h rectangle.

    Args:
        w: width in m.
        h: height in m.
    """
    return w * h


def total(xs):
    """Sum xs."""
    return sum(xs)
'''


def mini_repo(root: Path) -> Path:
    (root / "calc" / "src").mkdir(parents=True)
    (root / "modgate.yaml").write_text("project: demo\n")
    (root / "demo.md").write_text("---\nkind: system\ntitle: Demo\n---\n# Demo\n")
    (root / "calc" / "calc.md").write_text("---\nkind: code\ntitle: calc\n---\n# calc\n")
    (root / "calc" / "src" / "calc.py").write_text(CALC)
    return root.resolve()


def _edit(p: Path, old: str, new: str):
    text = p.read_text()
    assert old in text
    p.write_text(text.replace(old, new))


def test_ratchet_on_real_map(tmp_path):
    _need_map()
    r = mini_repo(tmp_path / "mini")
    d = ["--data-dir", tmp_path / "data"]
    src = r / "calc" / "src" / "calc.py"
    code, out, _ = W("map", r, *d)
    assert code == 0 and out.startswith("wiki: baseline created (")
    assert W("check", r, *d)[:2] == (0, "")
    _edit(src, "    return w * h\n", "    # multiply\n    return w * h\n")          # comment only
    assert W("check", r, *d)[:2] == (0, "")
    _edit(src, "def area(w, h):", "def area(w, height):")
    _edit(src, "return w * h\n", "return w * height\n")
    code, out, _ = W("check", r, *d)
    assert code == 1 and any(ln.startswith("DOCSTALE    calc  area") for ln in out.splitlines())
    old_entry = fresh.load_baseline(r)["symbols"]["calc/src/calc.py#area"]
    _edit(src, "        h: height in m.", "        height: height in m.")             # doc edit clears it
    assert W("check", r, *d)[:2] == (0, "")
    W("sync", r, *d)
    assert fresh.load_baseline(r)["symbols"]["calc/src/calc.py#area"] != old_entry
    _edit(src, "return sum(xs)", "return sum(list(xs))")                              # body only
    code, out, _ = W("check", r, *d)
    assert code == 1 and out.startswith("DOCREVIEW   calc  total")
    assert W("ack", "calc/src/calc.py#total", r, *d)[0] == 3
    assert W("ack", "calc/src/calc.py#total", r, *d, "--unchanged", "short")[0] == 3
    assert W("ack", "calc/src/calc.py#total", r, *d, "--unchanged", "list() keeps the same sum")[:2] == (
        0, "wiki: acked total\n")
    assert len((r / ".wikimap" / "acks.jsonl").read_text().splitlines()) == 1
    assert W("check", r, *d)[:2] == (0, "")
    src.write_text(src.read_text() + "\n\ndef helper(x):\n    return x\n")              # new undocumented
    code, out, _ = W("check", r, *d)
    assert code == 1 and out.startswith("UNDOC       calc  helper")
    code, _, err = W("ack", "calc/src/calc.py#helper", r, *d, "--unchanged", "reason long enough")
    assert code == 3 and err.endswith("helper has no doc; write one\n")
    _edit(src, "def total(xs):", "def summed(xs):")                                   # rename
    assert W("check", r, *d, "--codes", "DOCSTALE,DOCREVIEW,DOCSIG")[:2] == (0, "")
    W("sync", r, *d)
    syms = fresh.load_baseline(r)["symbols"]
    assert "calc/src/calc.py#summed" in syms and "calc/src/calc.py#total" not in syms
    (r / ".wikimap" / "baseline.json").write_text("{bad")
    code, out, err = W("check", r, *d)
    assert (code, out, err) == (3, "", ROOT_ERR + ".wikimap/baseline.json unreadable: resolve the conflict\n")


def test_module_docstring_id_never_collides_with_a_symbol(tmp_path):
    _need_map()
    r = mini_repo(tmp_path / "mini")
    (r / "calc" / "src" / "decode.py").write_text('def decode(b):\n    """Decode b."""\n    return b\n')
    code, out, _ = W("check", r, "--data-dir", tmp_path / "data")
    assert code == 1 and out.splitlines() == [
        "UNDOC       calc  src/decode.py  src/decode.py:1  → add a module docstring: what it is for"]


def test_example_zero_false_alarms(request, tmp_path):
    ex = _fixture(request, "example")
    d = ["--data-dir", tmp_path / "data"]
    code, out, _ = W("map", ex, *d)
    assert code == 0 and out.startswith("wiki: baseline created (")
    assert W("check", ex, *d)[:2] == (0, "")
    assert W("check", ex, *d, "--all", "--codes", "XCALL,DIAGNODE,DEADLINK")[:2] == (0, "")
    code, out, _ = W("check", ex, *d, "--all", "--json")
    keys = {f["key"] for f in json.loads(out)}
    assert keys == set(fresh.load_baseline(ex)["debt"])
    lines = W("check", ex, *d, "--all", "--codes", "UNDRAWN")[1].splitlines()
    assert any(re.match(r"UNDRAWN\s+\S+\s+protocol\b", ln) for ln in lines)
    assert any(re.match(r"UNDRAWN\s+\S+\s+targets\b", ln) for ln in lines)
    code, out, _ = W("show", ".", ex, *d, "--lens", "systems")
    assert code == 0 and out.startswith("weather-station")
    code, out, _ = W("show", "firmware/comms", ex, *d, "--lens", "systems")
    assert code == 0 and any(ln.startswith("* comms") for ln in out.splitlines())
    assert W("trace", "update_brownout", ex, *d, "--in")[0] == 0


def _hash_tree(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if rel.split("/")[0] in (".wikimap", ".wiki") or not p.is_file():
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_example_no_write_guard(request, monkeypatch):
    ex = _fixture(request, "example")
    before = _hash_tree(ex)
    W("map", ex)
    W("sync", ex)
    W("check", ex)
    W("check", ex, "--changed")
    hook = json.dumps({"hook_event_name": "PostToolUse", "cwd": str(ex), "tool_input": {
        "file_path": str(ex / "firmware/sensing/battery_monitor/src/brownout.cpp")}})
    assert run(cli, ["sync", "--hook"], hook)[0] == 0
    assert run(cli, ["pending", "--hook"], json.dumps({"cwd": str(ex)}))[0] == 0
    assert _hash_tree(ex) == before


def test_poly_exit_codes(request, tmp_path):
    poly = _fixture(request, "poly")
    d = ["--data-dir", tmp_path / "data"]
    code, out, _ = W("check", poly, *d)
    assert code == 1 and out and not (poly / ".wikimap").exists()
    assert W("check", poly, *d, "--strict")[0] == 2
    data = json.loads(W("check", poly, *d, "--json")[1])
    assert data and all(set(f) == {"code", "severity", "module", "id", "files", "action", "node", "key"} for f in data)
    (poly / ".wikimap").mkdir()
    (poly / ".wikimap" / "config.json").write_text('{"violations": ["XCALL"]}')
    code, out, _ = W("check", poly, *d)
    assert code == 2 and any(ln.startswith("E:XCALL     web  fmt") for ln in out.splitlines())
    (poly / ".wikimap" / "config.json").write_text("{nope")
    assert W("check", poly, *d)[0] == 3

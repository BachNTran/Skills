"""Hook mode: ``sync --hook`` (PostToolUse) and ``pending --hook`` (SessionStart) — opt-in
gating, silence rules, output shape, caps, first-run baseline, cold-build guard (§7.5, O3)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_fresh import PY, SCRIPTS, _isolate, mkdoc, run, std_map  # noqa: E402,F401

from wikimap import cli, fresh  # noqa: E402


def post(root: Path, file_path, **extra) -> str:
    return json.dumps({"hook_event_name": "PostToolUse", "cwd": str(root), "tool_name": "Edit",
                       "tool_input": {"file_path": str(file_path)}, **extra})


def start(root: Path) -> str:
    return json.dumps({"hook_event_name": "SessionStart", "cwd": str(root), "source": "startup"})


def H(cmd: str, stdin: str):
    return run(cli, [cmd, "--hook"], stdin)


def context(out: str, event: str) -> str:
    data = json.loads(out)
    assert list(data) == ["hookSpecificOutput"]
    assert data["hookSpecificOutput"]["hookEventName"] == event
    return data["hookSpecificOutput"]["additionalContext"]


def snapshot(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


@pytest.fixture
def no_build(monkeypatch):
    def boom(*a):
        raise AssertionError("map built")
    calls = []
    monkeypatch.setattr(cli, "_open", lambda *a: calls.append(a) or boom())
    return calls


# ---- gating: nothing happens outside an opted-in repo --------------------------------------

def test_not_opted_in_is_silent_and_writes_nothing(tmp_path, no_build):
    r = tmp_path / "plain"
    (r / ".git").mkdir(parents=True)
    (r / "src").mkdir()
    (r / "src" / "a.py").write_text("def f():\n    return 1\n")
    before = snapshot(tmp_path)
    assert H("sync", post(r, r / "src" / "a.py")) == (0, "", "")
    assert H("pending", start(r)) == (0, "", "")
    assert snapshot(tmp_path) == before and no_build == []
    best = min(_timed(lambda: H("sync", post(r, r / "src" / "a.py"))) for _ in range(5))
    assert best < 0.05


def _timed(fn) -> float:
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def test_not_opted_in_subprocess(tmp_path):
    r = tmp_path / "plain2"
    (r / ".git").mkdir(parents=True)
    code = f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); from wikimap import cli; sys.exit(cli.main(['sync', '--hook']))"
    env = {**os.environ, "HOME": str(tmp_path / "home"), "XDG_CACHE_HOME": str(tmp_path / "home" / ".cache")}
    p = subprocess.run([sys.executable, "-I", "-B", "-c", code], input=post(r, r / "x.py"), capture_output=True,
                       text=True, cwd=r, env=env, timeout=30)
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")
    assert snapshot(tmp_path / "home") == []


@pytest.mark.parametrize("stdin", ["", "not json", "[1]", '{"tool_input": 5}', '{"cwd": 5}', "{"])
def test_malformed_stdin(stdin, no_build):
    assert H("sync", stdin) == (0, "", "")
    assert H("pending", stdin) == (0, "", "")


@pytest.fixture
def opted(tmp_path):
    r = (tmp_path / "repo").resolve()
    (r / ".wikimap").mkdir(parents=True)
    (r / ".git").mkdir()
    return r


@pytest.mark.parametrize("target", ["../outside.py", ".github/x.py", "docs-img/pic.png", "notes.txt",
                                    "lib/data.yaml", ".wikimap/baseline.json"])
def test_silent_paths(opted, no_build, target):
    assert H("sync", post(opted, opted / target)) == (0, "", "")
    assert H("sync", json.dumps({"cwd": str(opted), "tool_input": {}})) == (0, "", "")
    assert no_build == []


def test_corrupt_baseline_and_config_silent(opted, no_build):
    (opted / ".wikimap" / "baseline.json").write_text("{bad")
    assert H("sync", post(opted, opted / PY)) == (0, "", "")
    assert H("pending", start(opted)) == (0, "", "")
    (opted / ".wikimap" / "baseline.json").unlink()
    (opted / ".wikimap" / "config.json").write_text("{bad")
    assert H("sync", post(opted, opted / PY)) == (0, "", "")
    assert no_build == []


def test_cold_build_guard(opted, no_build):
    big = opted / "big"
    big.mkdir()
    for i in range(cli.COLD_LIMIT + 1):
        (big / f"m{i}.py").write_bytes(b"")
    code, out, _ = H("sync", post(opted, big / "m1.py"))
    assert code == 0 and context(out, "PostToolUse") == "wiki sync: map not built yet  → run W map once"
    code, out, _ = H("pending", start(opted))
    assert context(out, "SessionStart") == "wiki pending: map not built yet  → run W map once"
    assert no_build == []


# ---- behaviour on the fake map -------------------------------------------------------------

@pytest.fixture
def fm(opted, monkeypatch):
    m = std_map(opted)
    monkeypatch.setattr(cli, "_open", lambda root, data, **kw: m)
    return m


def test_first_run_prints_only_baseline_line(opted, fm):
    code, out, err = H("sync", post(opted, opted / PY))
    assert (code, err) == (0, "")
    assert context(out, "PostToolUse") == "wiki: baseline created (11 symbols, 7 findings recorded as debt)"
    assert fresh.load_baseline(opted) is not None


def test_first_run_session_start(opted, fm):
    assert context(H("pending", start(opted))[1], "SessionStart").startswith("wiki: baseline created (")


def test_post_tool_use_finding_round_trip(opted, fm):
    H("sync", post(opted, opted / PY))
    assert H("sync", post(opted, opted / PY)) == (0, "", "")          # clean: silent
    assert H("sync", post(opted, "app/src/main.py")) == (0, "", "")    # relative path, debt hidden
    fm.edit(f"{PY}#area", body="b1")
    code, out, _ = H("sync", post(opted, opted / PY))
    text = context(out, "PostToolUse")
    assert text.splitlines() == ["wiki sync:", fresh.compute(fm, fresh.load_baseline(opted))[0].line()]
    assert text.splitlines()[1].startswith("DOCREVIEW   lib  area  src/calc.py:3  → body changed")
    assert context(H("sync", post(opted, opted / PY))[1], "PostToolUse") == text   # persists


def test_hook_advances_baseline_for_the_file_only(opted, fm):
    H("sync", post(opted, opted / PY))
    new = fm.sym(PY, "fresh_one", line=60, doc=mkdoc("Fresh."))
    other = fm.sym("app/src/main.py", "other", line=9, doc=mkdoc("Other."))
    H("sync", post(opted, opted / PY))
    syms = fresh.load_baseline(opted)["symbols"]
    assert new in syms and other not in syms


def test_cap_and_more_line(opted, fm):
    H("sync", post(opted, opted / PY))
    rel = "lib/src/many.py"
    fm.file(rel, "lib")
    for i in range(14):
        fm.sym(rel, f"f{i:02d}", line=i * 3 + 1)
    lines = context(H("sync", post(opted, opted / rel))[1], "PostToolUse").splitlines()
    assert lines[0] == "wiki sync:" and len(lines) == 1 + 12 + 1
    assert lines[-1] == f"… 2 more  → wiki check --file {rel}"
    (opted / ".wikimap" / "config.json").write_text('{"max_hook_lines": 3}')
    lines = context(H("sync", post(opted, opted / rel))[1], "PostToolUse").splitlines()
    assert len(lines) == 5 and lines[-1] == f"… 11 more  → wiki check --file {rel}"


def test_module_doc_edit(opted, fm):
    H("sync", post(opted, opted / PY))
    assert H("sync", post(opted, opted / "demo.md")) == (0, "", "")   # existing gaps are debt
    fm.module("newmod", "newmod")
    text = context(H("sync", post(opted, opted / "demo.md"))[1], "PostToolUse")
    assert text == ('wiki sync:\nUNDRAWN     demo  newmod  demo.md:8  → add newmod to "Subsystems and '
                    'interactions" in demo.md with a labelled edge')


def test_session_start_summary(opted, fm):
    H("pending", start(opted))
    assert H("pending", start(opted)) == (0, "", "")
    fm.edit(f"{PY}#area", body="b1")
    fm.edit(f"{PY}#Engine.run", sig="s9")
    text = context(H("pending", start(opted))[1], "SessionStart").splitlines()
    assert text[0] == "wiki pending:"
    assert text[1].startswith("DOCSTALE    lib  Engine.run")
    assert text[2] == "DOCREVIEW   lib  1 symbols  → wiki check --module lib"
    for i in range(20):
        mid = fm.module(f"m{i:02d}", f"m{i:02d}")
        fm.sym(fm.file(f"{mid}/a.py", mid), "undocumented")
    text = context(H("pending", start(opted))[1], "SessionStart").splitlines()
    assert len(text) == 1 + 8 and text[-1].endswith("more  → wiki check")


def test_exception_inside_hook_is_swallowed(opted, monkeypatch):
    monkeypatch.setattr(cli, "_open", lambda *a: 1 / 0)
    assert H("sync", post(opted, opted / PY)) == (0, "", "")
    assert H("pending", start(opted)) == (0, "", "")


# ---- real Map (waits for WP1–WP3) ----------------------------------------------------------

def test_hook_on_real_map(tmp_path):
    wm = pytest.importorskip("wikimap")
    if not hasattr(wm, "open_map"):
        pytest.skip("wikimap.open_map not landed")
    from test_cli import mini_repo
    r = mini_repo(tmp_path / "mini")
    src = r / "calc" / "src" / "calc.py"
    code, out, _ = H("sync", post(r, src))
    assert context(out, "PostToolUse").startswith("wiki: baseline created (")
    assert H("sync", post(r, src)) == (0, "", "")
    src.write_text(src.read_text().replace("return sum(xs)", "return sum(list(xs))"))
    t = time.perf_counter()
    text = context(H("sync", post(r, src))[1], "PostToolUse")
    assert time.perf_counter() - t < 1.0
    assert text.splitlines()[0] == "wiki sync:" and text.splitlines()[1].startswith("DOCREVIEW   calc  total")
    assert H("pending", start(r))[0] == 0


def test_example_warm_post_tool_use_budget(request):
    """§7.5 / O3: one-file PostToolUse ≤ 300 ms warm on the example (in-process, after `W map`)."""
    wm = pytest.importorskip("wikimap")
    if not hasattr(wm, "open_map"):
        pytest.skip("wikimap.open_map not landed")
    try:
        ex = Path(request.getfixturevalue("example"))
    except pytest.FixtureLookupError:
        pytest.skip("conftest example fixture not landed")
    assert run(cli, ["map", str(ex)])[0] == 0
    src = ex / "firmware/sensing/battery_monitor/src/battery_monitor.cpp"
    assert H("sync", post(ex, src)) == (0, "", "")                     # warm, unchanged: silent
    src.write_text(src.read_text().replace("* kDividerRatio;", "* kDividerRatio + 1;"))
    t = time.perf_counter()
    code, out, _ = H("sync", post(ex, src))
    took = time.perf_counter() - t
    lines = context(out, "PostToolUse").splitlines()
    assert lines[0] == "wiki sync:" and len(lines) == 2
    assert lines[1].startswith("DOCREVIEW   battery_monitor  battery_monitor::BatteryMonitor::sample  "
                               "src/battery_monitor.cpp:5  → ")
    assert took < 0.3, f"warm PostToolUse took {took * 1000:.0f} ms"
    assert context(H("sync", post(ex, src))[1], "PostToolUse").splitlines() == lines  # code-only: persists
    assert "DOCREVIEW" in context(H("pending", start(ex))[1], "SessionStart")


def test_code_edit_chains_to_its_module_icd(request):
    """Renaming a function in code flags the module ICD that still names it, on that same edit."""
    wm = pytest.importorskip("wikimap")
    if not hasattr(wm, "open_map"):
        pytest.skip("wikimap.open_map not landed")
    try:
        ex = Path(request.getfixturevalue("example"))
    except pytest.FixtureLookupError:
        pytest.skip("conftest example fixture not landed")
    assert run(cli, ["map", str(ex)])[0] == 0
    mod = ex / "firmware/sensing/battery_monitor"
    hdr, src = mod / "include/battery_monitor/battery_monitor.hpp", mod / "src/battery_monitor.cpp"
    for p in (hdr, src):
        p.write_text(p.read_text().replace("sample()", "sample_now()"))
    lines = context(H("sync", post(ex, src))[1], "PostToolUse").splitlines()
    assert any(ln.startswith("ICDSYM      battery_monitor  sample  docs/battery_monitor.icd.md:") for ln in lines), lines


def test_gate_does_not_import_the_graph(tmp_path):
    """O3: the opt-in gate must stay under 50 ms, so `import wikimap.cli` must not pull in the
    graph, resolver or language adapters before the gate has passed."""
    code = (f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import wikimap.cli; "
            "bad = sorted(m for m in sys.modules if m.startswith(('wikimap.graph', 'wikimap.resolve', "
            "'wikimap.lang', 'wikimap.tree', 'wikimap.fresh'))); print(','.join(bad))")
    p = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, timeout=30)
    assert (p.returncode, p.stdout.strip()) == (0, "")


def test_unparseable_edit_pauses_checks_and_keeps_pending_review(request):
    """A half-typed edit (ast.parse fails) must not report UNDOC on documented symbols nor launder a
    pending DOCREVIEW: the file's baseline entries stay untouched until it parses again."""
    pytest.importorskip("wikimap")
    ex = Path(request.getfixturevalue("example"))
    src = ex / "backend/ingest/src/ingest/decode.py"
    text = src.read_text()
    text = text.replace("def decode(data: bytes) -> dict:\n",
                        'def decode(data: bytes) -> dict:\n    """Decode one Reading."""\n')
    src.write_text(text)
    assert run(cli, ["map", str(ex)])[0] == 0
    assert H("sync", post(ex, src)) == (0, "", "")
    src.write_text(text.replace("    out: dict = {}\n", "    out: dict = {}\n    out.clear()\n"))
    body = src.read_text()
    assert "DOCREVIEW   ingest  decode" in context(H("sync", post(ex, src))[1], "PostToolUse")
    src.write_text(body + "\ndef helper(x:\n")
    out = context(H("sync", post(ex, src))[1], "PostToolUse")
    assert "UNDOC" not in out and "does not parse" in out
    assert run(cli, ["check", str(ex), "--codes", "UNDOC"])[1] == ""
    src.write_text(body)
    assert "DOCREVIEW   ingest  decode" in context(H("sync", post(ex, src))[1], "PostToolUse")
    assert "DOCREVIEW   ingest  decode" in run(cli, ["check", str(ex), "--codes", "DOCREVIEW"])[1]


def test_slow_map_hook_prints_one_line_without_building(opted, no_build):
    data = opted / ".wiki" / "map"
    data.mkdir(parents=True)
    (opted / ".gitignore").write_text(".wiki/\n")
    (data / "cache.json").write_text("{}")
    (data / "build.json").write_text(json.dumps({"v": 1, "warm_s": cli.HOOK_MAX_S + 1}))
    code, out, _ = H("sync", post(opted, opted / PY))
    assert code == 0 and context(out, "PostToolUse") == f"wiki sync: map too large for hooks  → W check --file {PY}"
    assert context(H("pending", start(opted))[1], "SessionStart").startswith("wiki pending: map too large")
    assert no_build == []


def test_plain_markdown_edit_does_not_build(opted, no_build):
    for rel in ("notes/thoughts.md", "a/b/scratch.md"):
        assert H("sync", post(opted, opted / rel)) == (0, "", "")
    assert no_build == []


def test_build_records_warm_cost(tmp_path):
    from wikimap import build_map
    r = tmp_path / "r"
    (r / "a").mkdir(parents=True)
    (r / "a" / "x.py").write_text("def f():\n    return 1\n")
    build_map(r, tmp_path / "d", exact=True)
    info = json.loads((tmp_path / "d" / "map" / "build.json").read_text())
    assert info["v"] == 1 and info["warm_s"] >= 0 and info["files"] == 1

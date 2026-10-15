"""``W map|check|sync|pending|ack|show|trace|install-hooks`` — the text CLI and the hooks.

``wiki.py`` dispatches these commands to ``main(argv)`` (``argv[0]`` is the command). Exit codes:
0 clean · 1 findings · 2 violations (or ``--strict`` with findings) · 3 error. Hook mode
(``sync --hook``, ``pending --hook``) always exits 0 and stays silent outside an opted-in repo
(root holds ``.wikimap/`` or ``modgate.yaml``). Heavy imports happen only after that check.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path


class _LazyFresh:
    """Defers ``import fresh`` (dataclasses, tempfile, …) until after the hook's opt-in gate."""

    def __getattr__(self, name):
        from . import fresh as mod
        globals()["fresh"] = mod
        return getattr(mod, name)


fresh = _LazyFresh()

OK, FINDINGS, VIOLATIONS, ERROR = 0, 1, 2, 3
SKILL = Path(__file__).resolve().parents[2]
WIKI_PY = SKILL / "scripts" / "wiki.py"
HOOKS_JSON = SKILL / "assets" / "hooks.json"
PROJECT_CMD = 'python3 "$CLAUDE_PROJECT_DIR"/.claude/skills/wiki/scripts/wiki.py'
USER_CMD = 'python3 "$HOME"/.claude/skills/wiki/scripts/wiki.py'


def user_hook(args: str) -> str:
    """Global hook command: a no-op (exit 0, no stderr) when the user copy of the skill is missing or old."""
    return ('f="$HOME"/.claude/skills/wiki/scripts/wiki.py; '
            f'[ -f "$f" ] && python3 "$f"{args} 2>/dev/null || true')
COLD_LIMIT = 3000
COLD_LINE = "map not built yet  → run W map once"
HOOK_MAX_S = 5.0  # a map whose warm rebuild costs more than this is too large for per-edit hooks
BASELINE_BAD = ".wikimap/baseline.json unreadable: resolve the conflict"
# Code extensions (spec §3.1); used before wikimap.lang is imported.
CODE_EXT = {".py", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".ino", ".js", ".mjs", ".cjs",
            ".jsx", ".ts", ".tsx", ".mts", ".go", ".rs", ".java", ".kt", ".cs", ".swift", ".proto", ".sql",
            ".sh", ".bash"}
SKIP_DIRS = {"__pycache__", "node_modules", "build", "dist", "venv", ".venv"}


class CliError(Exception):
    pass


def err(msg: str) -> int:
    print(f"{'E:ERROR':<10}  (root)  {msg}", file=sys.stderr)
    return ERROR


# ---- root, opt-in, data dir ----------------------------------------------------------------

def find_root(start) -> tuple[Path, bool]:
    """Nearest ancestor with ``modgate.yaml`` (modgate mode), else nearest ``.git``, else start."""
    start = Path(start).expanduser().resolve()
    if not start.is_dir():
        start = start.parent
    chain = (start, *start.parents)
    for d in chain:
        if (d / "modgate.yaml").is_file():
            return d, True
    for d in chain:
        if (d / ".git").exists():
            return d, False
    return start, False


def opted_in(root: Path) -> bool:
    return (root / ".wikimap").is_dir() or (root / "modgate.yaml").is_file()


def _ignores_wiki(root: Path) -> bool:
    try:
        lines = (root / ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    return any(ln.strip() in (".wiki", ".wiki/", "/.wiki", "/.wiki/") for ln in lines)


def data_dir(root: Path, explicit: str | None = None) -> Path:
    """``--data-dir`` wins; else ``<root>/.wiki`` when it exists or is git-ignored; else the
    user cache ``$XDG_CACHE_HOME/wiki/<sha12 of root>``. Never creates anything."""
    import hashlib
    if explicit:
        return Path(explicit).expanduser().resolve()
    local = root / ".wiki"
    if local.is_dir() or _ignores_wiki(root):
        return local
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "wiki" / hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]


def _open(root: Path, data: Path, annotate: bool = True):
    """Build (incrementally) and return the Map. Tests monkeypatch this. Hooks pass annotate=False:
    they compute their own file-scoped findings, so the whole-map pass would be wasted."""
    from wikimap import open_map
    return open_map(root, data, exact=True, annotate=annotate)


def _count_code(root: Path, limit: int) -> int:
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS
                       and not d.endswith(".egg-info")]
        for f in filenames:
            if os.path.splitext(f)[1].lower() in CODE_EXT:
                n += 1
                if n > limit:
                    return n
    return n


def _cold(data: Path, root: Path) -> bool:
    return not (data / "map" / "cache.json").is_file() and _count_code(root, COLD_LIMIT) > COLD_LIMIT


def _slow(data: Path) -> bool:
    """True when the last build's warm cost (everything but extraction) is over the hook budget."""
    try:
        info = json.loads((data / "map" / "build.json").read_text(encoding="utf-8"))
        return float(info.get("warm_s") or 0) > HOOK_MAX_S
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _maybe_module_doc(root: Path, rel: str) -> bool:
    """Cheap pre-filter before a build: could `rel` be a module card, README or docs/ file?"""
    parts = rel.split("/")
    name = parts[-1]
    if name.endswith(".bind.yaml") or "docs" in parts[:-1] or len(parts) == 1:
        return True
    stem = name[:-3].lower() if name.lower().endswith(".md") else ""
    return stem in ("readme", "architecture", "index") or stem == parts[-2].lower()


def _to_rel(root: Path, s: str) -> str:
    p = Path(s).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p if (Path.cwd() / p).exists() else root / p
    try:
        return p.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return s.replace("\\", "/")


def _exit(fs: list, strict: bool = False) -> int:
    if any(f.severity == "violation" for f in fs) or (strict and fs):
        return VIOLATIONS
    return FINDINGS if fs else OK


def _created_line(base: dict) -> str:
    return (f"wiki: baseline created ({len(base['symbols'])} symbols, "
            f"{len(base['debt'])} findings recorded as debt)")


def pending_lines(fs: list, limit: int = 8) -> list[str]:
    """XCALL/DOCSTALE/DOCSIG lines first, then one summary line per (code, module)."""
    first = [f.line() for f in fs if f.code in ("XCALL", "DOCSTALE", "DOCSIG")]
    groups: dict[tuple, list] = {}
    for f in fs:
        if f.code not in ("XCALL", "DOCSTALE", "DOCSIG"):
            groups.setdefault((fresh.CODES.index(f.code) if f.code in fresh.CODES else 99, f.module), []).append(f)
    summary = []
    for (_, module), items in sorted(groups.items()):
        label = items[0].label if any(i.severity == "violation" for i in items) else items[0].code
        noun = "symbols" if items[0].code in fresh.SYMBOL_CODES else "findings"
        summary.append(f"{label:<10}  {module}  {len(items)} {noun}  → wiki check --module {module}")
    lines = first + summary
    if len(lines) > limit:
        lines = lines[:limit - 1] + [f"… {len(lines) - limit + 1} more  → wiki check"]
    return lines


def _cap(lines: list[str], cap: int, more: str) -> list[str]:
    if len(lines) <= cap:
        return lines
    return lines[:cap] + [f"… {len(lines) - cap} more  → {more}"]


def _max_lines(cfg: dict) -> int:
    v = cfg.get("max_hook_lines", 12)
    return v if isinstance(v, int) and v > 0 else 12


# ---- symbol / node lookup ------------------------------------------------------------------

def _symbol_matches(m, root: Path, target: str) -> list[dict]:
    syms = fresh.symbols(m)
    hit = [s for s in syms.values() if s["key"] == target]
    if hit:
        return hit
    if target in syms:
        return [syms[target]]
    mt = re.fullmatch(r"(.+?):(\d+)", target)
    if mt:
        rel, line = _to_rel(root, mt.group(1)), int(mt.group(2))
        inside = [s for s in syms.values() if s["file"] == rel and s["line"] is not None
                  and s["line"] <= line <= (s.get("end") or s["line"])]
        if inside:
            return [min(inside, key=lambda s: ((s.get("end") or s["line"]) - s["line"], -s["line"]))]
    for field in ("qual", "name"):
        hit = [s for s in syms.values() if s[field] == target]
        if hit:
            return hit
    # qual-suffix on a `::`/`.` boundary: `update_brownout` finds `BatteryMonitor::update_brownout`,
    # `Engine.run` finds `pkg.core.Engine.run`.
    want = re.split(r"::|\.", target)
    if all(want):
        n = len(want)
        hit = [s for s in syms.values()
               if re.split(r"::|\.", s["qual"] or "")[-n:] == want]
        if hit:
            return hit
    return []


def _one_symbol(m, root: Path, target: str):
    hits = _symbol_matches(m, root, target)
    if not hits:
        raise CliError(f"{target} matches no symbol")
    if len({s["id"] for s in hits}) > 1:
        ids = sorted({s["id"] for s in hits})
        raise CliError(f"{target} is ambiguous: {', '.join(ids[:5])}" + (" …" if len(ids) > 5 else ""))
    return hits[0]


def _node_id(m, root: Path, target: str) -> str:
    if target in m.nodes:
        return target
    rel = _to_rel(root, target).rstrip("/") or "."
    if rel in m.nodes:
        return rel
    if target in m.modules and m.modules[target].get("id") in m.nodes:
        return m.modules[target]["id"]
    order = {"sys": 0, "code": 1}
    hits = sorted((n for n in m.nodes.values() if n.get("name") == target),
                  key=lambda n: (order.get(n.get("tier"), 2), n.get("type") == "symbol", len(n["id"]), n["id"]))
    if hits:
        return hits[0]["id"]
    try:
        hits = _symbol_matches(m, root, target)
    except Exception:
        hits = []
    if hits:
        return hits[0]["id"]
    raise CliError(f"{target} matches no node")


def _module_docs(m) -> dict[str, str]:
    """``{repo-rel doc path: module name}`` for overview/ICD/req/bind and diagram docs."""
    out: dict[str, str] = {}
    for name, info in m.modules.items():
        info = info or {}
        for d in info.get("docs") or []:
            item = d.get("item") if isinstance(d, dict) else d
            if item:
                out.setdefault(item, name)
        icd = info.get("icd")
        icd = icd.get("item") if isinstance(icd, dict) else icd
        if icd:
            out.setdefault(icd, name)
        mid = info.get("id") or "."
        out.setdefault(("" if mid == "." else mid + "/") + f"docs/{name}.bind.yaml", name)
        out.setdefault(("" if mid == "." else mid + "/") + f"docs/{name}.req.md", name)
    for cid, d in (m.diagrams or {}).items():
        doc = (d or {}).get("doc")
        if doc:
            out.setdefault(doc, fresh.mod_name(m, cid))
    return out


# ---- hooks ---------------------------------------------------------------------------------

def _emit(event: str, text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
                     ensure_ascii=False))


def _hook_data_dir(argv: list[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--data-dir" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--data-dir="):
            return a.split("=", 1)[1]
    return None


def hook(cmd: str, raw: str, argv: list[str]) -> int:
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return OK
    if not isinstance(data, dict):
        return OK
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not isinstance(cwd, str):
        return OK
    root, _ = find_root(cwd)
    if not opted_in(root):
        return OK  # cheap gate: nothing read, nothing written
    if cmd == "sync":
        return _hook_sync(root, data, argv)
    return _hook_pending(root, argv)


def _hook_prelude(root: Path, argv: list[str]):
    cfg = fresh.load_config(root)
    base = fresh.load_baseline(root)
    data = data_dir(root, _hook_data_dir(argv))
    return cfg, base, data


def _hook_sync(root: Path, data: dict, argv: list[str]) -> int:
    event = data.get("hook_event_name") or "PostToolUse"
    ti = data.get("tool_input")
    fp = ti.get("file_path") if isinstance(ti, dict) else None
    if not fp or not isinstance(fp, str):
        return OK
    path = Path(fp)
    if not path.is_absolute():
        path = Path(data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / path
    try:
        rel = path.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return OK
    parts = rel.split("/")
    if any(p.startswith(".") for p in parts):
        return OK
    name = parts[-1]
    code = Path(name).suffix.lower() in CODE_EXT
    if not code and not (name.endswith((".md", ".bind.yaml")) and _maybe_module_doc(root, rel)):
        return OK
    try:
        cfg, base, ddir = _hook_prelude(root, argv)
    except (fresh.ConfigError, fresh.BaselineError):
        return OK
    if _cold(ddir, root):
        _emit(event, f"wiki sync: {COLD_LINE}")
        return OK
    if _slow(ddir):
        more = f"W check --file {rel}" if code else "W check"
        _emit(event, f"wiki sync: map too large for hooks  → {more}")
        return OK
    m = _open(root, ddir, annotate=False)
    if base is None:
        base = fresh.create_baseline(m)
        fresh.save_baseline(root, base)
        _emit(event, _created_line(base))
        return OK
    finfo = m.files.get(rel) or {}
    if finfo and finfo.get("lang") not in (None, "", "text"):
        fs = fresh.compute(m, base, files={rel}, codes=set(fresh.SYMBOL_CODES) | {"XCALL"})
        new = fresh.advance(m, base, files={rel})
        if new != base:
            fresh.save_baseline(root, new)
        more = f"wiki check --file {rel}"
        if rel in fresh.broken_files(m):
            _emit(event, f"wiki sync: {rel} does not parse; doc checks paused")
            return OK
    else:
        module = _module_docs(m).get(rel)
        if module is None:
            return OK
        fs = fresh.compute(m, base, modules={module}, codes=set(fresh.DOC_CODES))
        more = f"wiki check --module {module}"
    if fs:
        lines = _cap([f.line() for f in fs], _max_lines(cfg), more)
        _emit(event, "wiki sync:\n" + "\n".join(lines))
    return OK


def _hook_pending(root: Path, argv: list[str]) -> int:
    try:
        cfg, base, ddir = _hook_prelude(root, argv)
    except (fresh.ConfigError, fresh.BaselineError):
        return OK
    if _cold(ddir, root):
        _emit("SessionStart", f"wiki pending: {COLD_LINE}")
        return OK
    if _slow(ddir):
        _emit("SessionStart", "wiki pending: map too large for hooks  → W check")
        return OK
    m = _open(root, ddir, annotate=False)
    if base is None:
        base = fresh.create_baseline(m)
        fresh.save_baseline(root, base)
        _emit("SessionStart", _created_line(base))
        return OK
    lines = pending_lines(fresh.compute(m, base))
    if lines:
        _emit("SessionStart", "wiki pending:\n" + "\n".join(lines))
    return OK


# ---- commands ------------------------------------------------------------------------------

def _setup(a, *, need_base: bool = False):
    root, _ = find_root(a.repo)
    try:
        cfg = fresh.load_config(root)
    except fresh.ConfigError as e:
        raise CliError(str(e)) from None
    try:
        base = fresh.load_baseline(root)
    except fresh.BaselineError:
        raise CliError(BASELINE_BAD) from None
    if need_base and base is None:
        raise CliError("no baseline yet  → run wiki map")
    return root, cfg, base, data_dir(root, a.data_dir)


def _build(root: Path, data: Path):
    try:
        return _open(root, data)
    except ImportError as e:
        raise CliError(f"map engine not available: {e}") from None
    except Exception as e:  # never a traceback for repo content
        raise CliError(f"map build failed: {type(e).__name__}: {e}") from None


def cmd_map(a) -> int:
    t0 = time.monotonic()
    root, _, base, data = _setup(a)
    m = _build(root, data)
    if base is None:
        base = fresh.create_baseline(m)
        fresh.save_baseline(root, base)
        print(_created_line(base))
    fs = fresh.compute(m, base)
    st = getattr(m, "stats", None) or {}
    hi = round(float(st.get("resolved_hi") or 0) * 100)
    print(f"wiki: {len(m.modules)} modules · {st.get('files', len(m.files))} files · "
          f"{st.get('symbols', len(fresh.symbols(m)))} symbols · {st.get('edges', len(m.edges))} edges "
          f"({hi}% ≥0.8) · {len(fs)} findings · {time.monotonic() - t0:.1f} s")
    return OK


def _codes(s: str | None) -> set[str] | None:
    if not s:
        return None
    codes = {c.strip().upper() for c in s.split(",") if c.strip()}
    bad = sorted(codes - set(fresh.CODES))
    if bad:
        raise CliError(f"unknown code {', '.join(bad)}; known: {' '.join(fresh.CODES)}")
    return codes


def _print_findings(fs: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps([f.json() for f in fs], ensure_ascii=False, indent=2))
    else:
        for f in fs:
            print(f.line())


def cmd_check(a) -> int:
    codes = _codes(a.codes)
    root, _, base, data = _setup(a)
    m = _build(root, data)
    files = {_to_rel(root, f) for f in a.file} if a.file else None
    if a.changed:
        ch = fresh.changed_files(m, base)
        files = ch if files is None else files & ch
    modules = None
    if a.module:
        ids = {(i or {}).get("id"): n for n, i in m.modules.items()}
        modules = {ids.get(x.rstrip("/"), x) for x in a.module}
    fs = fresh.compute(m, base or fresh.empty_baseline(), files=files, modules=modules, codes=codes, all_=a.all)
    _print_findings(fs, a.json)
    return _exit(fs, a.strict)


def cmd_sync(a) -> int:
    root, _, base, data = _setup(a)
    m = _build(root, data)
    if base is None:
        base = fresh.create_baseline(m)
        fresh.save_baseline(root, base)
        print(_created_line(base))
        fs = fresh.compute(m, base)
    else:
        fs = fresh.compute(m, base)
        new = fresh.advance(m, base, files=None)
        if new != base:
            fresh.save_baseline(root, new)
    _print_findings(fs, False)
    return _exit(fs)


def cmd_pending(a) -> int:
    root, _, base, data = _setup(a)
    m = _build(root, data)
    fs = fresh.compute(m, base or fresh.empty_baseline())
    for ln in pending_lines(fs):
        print(ln)
    return FINDINGS if fs else OK


def cmd_ack(a) -> int:
    reason = (a.unchanged or "").strip()
    if len(reason) < 8:
        raise CliError('ack needs --unchanged "<reason>" (8+ chars)')
    root, _, base, data = _setup(a, need_base=True)
    m = _build(root, data)
    sym = _one_symbol(m, root, a.target)
    if not sym["doc"]:
        raise CliError(f"{sym['qual']} has no doc; write one")
    hashes = fresh.entry(sym)
    base["symbols"][sym["key"]] = hashes
    fresh.save_baseline(root, base)
    fresh.append_ack(root, sym["key"], reason, hashes)
    print(f"wiki: acked {sym['qual']}")
    return OK


def _mark_leaf(text: str, name: str) -> str:
    out, done = [], False
    for ln in text.splitlines():
        if not done and ln.startswith("  ") and (ln[2:] == name or ln[2:].startswith(name + " ")):
            ln, done = "* " + ln[2:], True
        out.append(ln)
    return "\n".join(out)


def cmd_show(a) -> int:
    root, _, _, data = _setup(a)
    m = _build(root, data)
    nid = _node_id(m, root, a.target)
    node = m.nodes[nid]
    lens = a.lens or ("systems" if node.get("tier") == "sys" else "code")
    at, leaf = nid, None
    if m.level(lens, at) is None and not a.lens and lens == "systems" and m.level("code", at) is not None:
        lens = "code"
    if m.level(lens, at) is None:
        leaf, at = nid, node.get("parent")
        if at is None:
            raise CliError(f"{a.target} has no level to show")
        if m.level(lens, at) is None:
            lens = "code" if lens == "systems" else "systems"
            if m.level(lens, at) is None:
                raise CliError(f"{a.target} has no level to show")
    text = m.show_text(lens, at, a.depth)
    if leaf:
        text = _mark_leaf(text, m.nodes[leaf].get("name") or leaf)
    print(text.rstrip("\n"))
    return OK


def cmd_trace(a) -> int:
    root, _, _, data = _setup(a)
    m = _build(root, data)
    nid = a.target if a.target in m.nodes else _one_symbol(m, root, a.target)["id"]
    direction = "in" if a.in_ else "out" if a.out else "both"
    print(m.trace_text(nid, direction, a.depth).rstrip("\n"))
    return OK


def _quote(p: Path) -> str:
    import shlex
    s = str(p)
    return f'"{s}"' if not re.search(r'["$`\\]', s) else shlex.quote(s)


def cmd_install_hooks(a) -> int:
    if a.user:
        target = Path.home() / ".claude" / "settings.json"
        copy = Path.home() / ".claude" / "skills" / "wiki" / "scripts" / "wikimap" / "cli.py"
        if not copy.is_file():
            # a global hook pointing at a missing or older copy would error after every edit in every repo
            raise CliError(f"~/.claude/skills/wiki has no wikimap (missing or older copy); "
                           f"install this skill there first ({SKILL}), then rerun")
        cmd = USER_CMD
    else:
        project = Path(a.project or ".").expanduser().resolve()
        if not project.is_dir():
            raise CliError(f"{project} is not a directory")
        target = project / ".claude" / "settings.json"
        local = project / ".claude" / "skills" / "wiki" / "scripts" / "wiki.py"
        cmd = PROJECT_CMD if local.is_file() else f"python3 {_quote(WIKI_PY)}"
    try:
        snippet = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CliError(f"assets/hooks.json unreadable: {e}") from None
    for groups in snippet["hooks"].values():
        for g in groups:
            for h in g["hooks"]:
                h["command"] = (user_hook(h["command"][len(PROJECT_CMD):]) if a.user
                                else h["command"].replace(PROJECT_CMD, cmd, 1))
    try:
        raw = target.read_text(encoding="utf-8") if target.is_file() else ""
        settings = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError) as e:
        raise CliError(f"{target} is not valid JSON ({e}); fix it first") from None
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
        raise CliError(f"{target}: expected an object with a \"hooks\" object")
    hooks = settings.get("hooks", {})
    plan = []
    for event, groups in snippet["hooks"].items():
        have = hooks.get(event) or []
        if not isinstance(have, list):
            raise CliError(f"{target}: hooks.{event} is not a list")
        known = {h.get("command") for g in have if isinstance(g, dict)
                 for h in (g.get("hooks") or []) if isinstance(h, dict)}
        for g in groups:
            if not all(h["command"] in known for h in g["hooks"]):
                plan.append((event, g))
    if not plan:
        print("wiki: hooks already installed")
        return OK
    if not a.write:
        for event, g in plan:
            for h in g["hooks"]:
                print(f"would add: {event} {h['command']}")
        return OK
    hooks = settings.setdefault("hooks", {})
    for event, g in plan:
        hooks.setdefault(event, []).append(g)
    fresh._atomic_write(target, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print(f"wiki: hooks installed in {target}")
    return OK


def _parser():
    import argparse

    class _Parser(argparse.ArgumentParser):
        def error(self, message):  # exit 3, not argparse's 2 (2 means violations here)
            raise CliError(message)

    ap = _Parser(prog="wiki", description="System map, code map and doc checks.")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_Parser)

    def cmd(name: str, target: bool = False):
        p = sub.add_parser(name)
        if target:
            p.add_argument("target")
        p.add_argument("repo", nargs="?", default=".")
        p.add_argument("--data-dir")
        return p

    cmd("map")
    c = cmd("check")
    c.add_argument("--json", action="store_true")
    c.add_argument("--strict", action="store_true")
    c.add_argument("--all", action="store_true")
    c.add_argument("--codes")
    c.add_argument("--module", action="append")
    c.add_argument("--file", action="append")
    c.add_argument("--changed", action="store_true")
    cmd("sync").add_argument("--hook", action="store_true")
    cmd("pending").add_argument("--hook", action="store_true")
    cmd("ack", True).add_argument("--unchanged")
    s = cmd("show", True)
    s.add_argument("--lens", choices=("systems", "code"))
    s.add_argument("--depth", type=int, choices=(1, 2, 3), default=1)
    t = cmd("trace", True)
    g = t.add_mutually_exclusive_group()
    g.add_argument("--in", dest="in_", action="store_true")
    g.add_argument("--out", action="store_true")
    t.add_argument("--depth", type=int, choices=(1, 2, 3, 4), default=2)
    i = sub.add_parser("install-hooks")
    i.add_argument("project", nargs="?", default=".")
    i.add_argument("--write", action="store_true")
    i.add_argument("--user", action="store_true")
    return ap


COMMANDS = {"map": cmd_map, "check": cmd_check, "sync": cmd_sync, "pending": cmd_pending, "ack": cmd_ack,
            "show": cmd_show, "trace": cmd_trace, "install-hooks": cmd_install_hooks}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] in (["sync"], ["pending"]) and "--hook" in argv:
        try:
            return hook(argv[0], sys.stdin.read(), argv)
        except Exception:
            return OK  # a hook never breaks the session
    try:
        a = _parser().parse_args(argv)
        return COMMANDS[a.cmd](a)
    except CliError as e:
        return err(str(e))
    except SystemExit as e:  # --help
        return int(e.code or 0) if isinstance(e.code, int) else OK


if __name__ == "__main__":
    raise SystemExit(main())

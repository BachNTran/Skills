"""Command line: `sync`, `pending`, `approve`. Exit 0 clean · 1 findings · 2 violations · 3 error."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, report
from .analyze import Finding, Project
from .approve import Rejected, approve
from .project import ModgateError

OK, FINDINGS, VIOLATIONS, ERROR = 0, 1, 2, 3


def exit_code(fs: list[Finding], strict: bool = False) -> int:
    if any(f.violation for f in fs) or (strict and fs):
        return VIOLATIONS
    return FINDINGS if fs else OK


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="modgate", description="Module gates: hash, detect, trace, record, report.")
    p.add_argument("--version", action="version", version=f"modgate {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="everything mechanical; silent on success")
    s.add_argument("paths", nargs="*")
    s.add_argument("--test", metavar="TARGET", help="run the target's command from modgate.yaml and record a pass")
    s.add_argument("--strict", action="store_true", help="CI: findings fail too (exit 2)")
    s.add_argument("--hook", action="store_true", help="Claude Code hook mode: read hook JSON from stdin")
    s.add_argument("--json", action="store_true")
    q = sub.add_parser("pending", help="open items, grouped into dependency-disjoint module sets")
    q.add_argument("--report", action="store_true", help="write .modgate/report.html and print its path")
    q.add_argument("--hook", action="store_true", help="SessionStart hook mode: emit additionalContext JSON")
    q.add_argument("--json", action="store_true")
    a = sub.add_parser("approve", help="approve a doc, a REQ review, or all gates (developer confirms)")
    a.add_argument("module")
    a.add_argument("what", help="doc (e.g. icd, docs/x.req.md), REQ-ID, or all")
    a.add_argument("--by", help="approver name, or ai-reviewer:<model> (default: git config user.name)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.cmd == "sync":
            return hook_sync(sys.stdin.read()) if args.hook else cmd_sync(args)
        if args.cmd == "pending":
            return hook_pending(sys.stdin.read()) if args.hook else cmd_pending(args)
        return cmd_approve(args)
    except Rejected as e:
        print(str(e))
        return VIOLATIONS
    except ModgateError as e:
        print(f"E:ERROR  {e}", file=sys.stderr)
        return ERROR


def run() -> None:
    sys.exit(main())


def cmd_sync(args) -> int:
    project = Project(Path(args.paths[0]) if args.paths else Path.cwd())
    fs = project.sync(args.paths or None, args.test)
    if args.json:
        print(json.dumps({"findings": [f.as_dict() for f in fs]}, indent=2))
    else:
        for f in fs:
            print(f.line())
    return exit_code(fs, args.strict)


def cmd_pending(args) -> int:
    project = Project(Path.cwd())
    groups, analyses = project.pending()
    if args.json:
        print(json.dumps({"sets": [[f.as_dict() for f in g] for g in groups]}, indent=2))
    else:
        print(format_groups(groups))
    if args.report:
        print(report.write(project, groups, analyses))
    return FINDINGS if groups else OK


def format_groups(groups: list[list[Finding]]) -> str:
    if not groups:
        return "nothing open"
    out = []
    for i, g in enumerate(groups, 1):
        mods = list(dict.fromkeys(f.module for f in g))
        out.append(f"# set {i} · {' '.join(mods)}")
        out += [f.line() for f in g]
    return "\n".join(out)


def cmd_approve(args) -> int:
    project = Project(Path.cwd())
    for line in approve(project, args.module, args.what, args.by):
        print(line)
    return OK


# ---- Claude Code hooks ------------------------------------------------------------------
# Formats per https://code.claude.com/docs/en/hooks: PostToolUse and SessionStart feed text back
# through hookSpecificOutput.additionalContext (exit 0; exit 2 is not honored for them);
# Stop blocks with exit 2 + stderr.


def _hook_input(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _context(event: str, text: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def hook_sync(raw: str) -> int:
    data = _hook_input(raw)
    event = data.get("hook_event_name") or "PostToolUse"
    cwd = Path(data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    if event in ("Stop", "SubagentStop"):
        try:
            project = Project(cwd)
            fs = project.sync(None)
        except ModgateError:
            return OK
        violations = [f for f in fs if f.violation]
        if violations and not data.get("stop_hook_active"):
            print("modgate violations (fix before stopping):", file=sys.stderr)
            print("\n".join(f.line() for f in violations), file=sys.stderr)
            return VIOLATIONS
        return OK
    file_path = (data.get("tool_input") or {}).get("file_path")
    if not file_path:
        return OK
    path = Path(file_path)
    path = path if path.is_absolute() else cwd / path
    try:
        project = Project(path)
    except ModgateError:
        return OK
    rel_parts = path.resolve().relative_to(project.root).parts if project.root in path.resolve().parents else ()
    if not rel_parts or rel_parts[0] == ".modgate":
        return OK
    if project.select([str(path)]):
        fs = [f for f in project.sync([str(path)]) if not (f.code == "CONFIG" and f.module not in project.modules)]
    else:
        fs = project.lint_dirs([path.resolve().parent])
    if fs:
        print(_context("PostToolUse", "modgate sync:\n" + "\n".join(f.line() for f in fs)))
    return OK


def hook_pending(raw: str) -> int:
    data = _hook_input(raw)
    cwd = Path(data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    try:
        project = Project(cwd)
        groups, _ = project.pending()
    except ModgateError:
        return OK
    print(_context("SessionStart", "modgate pending:\n" + format_groups(groups)))
    return OK


if __name__ == "__main__":
    run()

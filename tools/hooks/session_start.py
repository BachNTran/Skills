#!/usr/bin/env python3
"""SessionStart hook — silently inject a brief project-memory digest.

Emits Claude Code ``additionalContext`` carrying the project's criticality tier, the
active-preferences digest, and current active work, so the agent "remembers" without the
developer re-explaining. Deliberately small (token budget). Always exits 0 so it can never
block a session from starting.

Wire in ``.claude/settings.json``::

    {"hooks": {"SessionStart": [{"hooks": [
      {"type": "command",
       "command": "python3 \\"$CLAUDE_PROJECT_DIR/tools/hooks/session_start.py\\""}]}]}}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MAX_PREF_LINES = 12
MAX_WORK_LINES = 5


def _root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", "")) if os.environ.get(
        "CLAUDE_PROJECT_DIR") else Path.cwd()


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def _criticality(root: Path) -> str:
    m = re.search(r"\*\*criticality:\*\*\s*([A-Z]+)", _read(root / "PROJECT_CONTEXT.md"))
    return m.group(1) if m else "unset"


def _active_prefs(root: Path) -> list[str]:
    text = _read(root / "PREFERENCES.md")
    if not text:
        return []
    out: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.strip().lower().startswith("## active preferences"):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            s = line.strip()
            if s.startswith("- ") and "(none yet)" not in s:
                out.append(s)
    return out[:MAX_PREF_LINES]


def _active_work(root: Path) -> list[str]:
    text = _read(root / "ProjectManagement" / "DEV_TRACKER.md")
    hits = [ln.strip() for ln in text.splitlines() if "FEAT-" in ln]
    return hits[:MAX_WORK_LINES]


def _digest(root: Path) -> str:
    parts = [f"Project criticality tier: **{_criticality(root)}** — honor it."]
    prefs = _active_prefs(root)
    if prefs:
        parts.append("Active design preferences:\n" + "\n".join(prefs))
    work = _active_work(root)
    if work:
        parts.append("Active work:\n" + "\n".join(work))
    parts.append("Traceability is live: link REQ↔DEC↔TC↔code; regenerate TRACE.md after "
                 "changing PRD/DECISIONS/TEST_PLAN or @covers.")
    return "\n\n".join(parts)


def main() -> int:
    root = _root()
    try:
        context = _digest(root)
    except Exception:
        return 0  # never block a session
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

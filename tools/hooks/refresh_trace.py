#!/usr/bin/env python3
"""PostToolUse hook — regenerate TRACE.md when a traceable artifact changes.

Reads the tool event from stdin; if the edited file is a feature ``PRD.md`` /
``DECISIONS.md`` / ``TEST_PLAN.md`` or any file containing an ``@covers`` annotation,
it regenerates the per-feature trace indexes. This keeps the bottom-up walk current at the
exact moments a traceable artifact changes — and stays quiet otherwise. Always exits 0 so it
never blocks a turn.

Wire in ``.claude/settings.json``::

    {"hooks": {"PostToolUse": [{"matcher": "Edit|Write|MultiEdit", "hooks": [
      {"type": "command",
       "command": "python3 \\"$CLAUDE_PROJECT_DIR/tools/hooks/refresh_trace.py\\""}]}]}}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TRIGGER_NAMES = ("PRD.md", "DECISIONS.md", "TEST_PLAN.md")


def _root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", "")) if os.environ.get(
        "CLAUDE_PROJECT_DIR") else Path.cwd()


def _edited_path(event: dict) -> str:
    ti = event.get("tool_input") or {}
    return ti.get("file_path") or ti.get("path") or ""


def _is_trigger(path: str) -> bool:
    if any(name in path for name in TRIGGER_NAMES):
        return True
    try:
        return "@covers" in Path(path).read_text(errors="ignore")
    except OSError:
        return False


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    path = _edited_path(event)
    if not path or not _is_trigger(path):
        return 0
    root = _root()
    generator = root / "tools" / "trace_index.py"
    if not generator.exists():
        return 0
    try:
        subprocess.run([sys.executable, str(generator), str(root)],
                       capture_output=True, timeout=30, check=False)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

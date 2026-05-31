#!/usr/bin/env bash
# install.sh — install the AI-assisted development workflow
#               (Claude Code / Codex skills + tool-agnostic project docs)
#
# Usage:
#   ./install.sh              — interactive TUI (guided install)
#   ./install.sh global       — install globally for Claude Code (~/.claude/skills/)
#   ./install.sh codex        — install globally for Codex (~/.codex/skills/)
#   ./install.sh project      — install to current project (.claude/skills/)
#   ./install.sh bootstrap    — install (project) + create full project docs structure
#   ./install.sh validate     — validate skill frontmatter before installing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required but not found." >&2
  exit 1
fi

exec python3 "$SCRIPT_DIR/install_tui.py" "$@"

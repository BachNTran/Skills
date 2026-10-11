#!/usr/bin/env bash
# Install modgate into a project: CLI, Claude skill, hooks + permission rule, modgate.yaml, .gitignore.
# Usage: ./install.sh <project-dir>      Re-runnable; never clobbers existing settings.
# macOS / Linux (bash). Windows (PowerShell) is a TODO — see docs/modgate.activity.md.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$REPO/kit"; [ -d "$REPO/claude" ] && KIT="$REPO/claude"   # repo layout: kit/ · portable kit: claude/
NO_CLI=0; [ "${1:-}" = "--no-cli" ] && { NO_CLI=1; shift; }     # CLI already installed machine-wide
[ $# -eq 1 ] || { echo "usage: $0 [--no-cli] <project-dir>" >&2; exit 3; }
mkdir -p "$1"
PROJECT="$(cd "$1" && pwd)"
# pick the newest Python >= 3.10 on PATH (macOS's /usr/bin/python3 is 3.9)
PY=""
for c in ${MODGATE_PYTHON:-} python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  p="$(command -v "$c" 2>/dev/null || true)"
  if [ -n "$p" ] && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then PY="$p"; break; fi
done
[ -n "$PY" ] || { echo "Python >= 3.10 is required (set MODGATE_PYTHON=/path/to/python3.x)" >&2; exit 3; }

# 1 · CLI: uv tool, else pipx, else a project-local venv + shim.
# In the portable kit, wheels/ ships modgate as one pure-Python wheel (zero deps), so installation works offline.
CMD="modgate"
if [ "$NO_CLI" = 1 ]; then
  echo "cli: skipped (--no-cli); hooks call \`modgate\` from PATH"
else
SRC="$REPO"
WHEEL="$(ls "$REPO"/wheels/modgate-*.whl 2>/dev/null | head -1 || true)"
[ -n "$WHEEL" ] && SRC="$WHEEL"   # the bundled wheel, by path: offline, and never a same-named PyPI package
if command -v uv >/dev/null 2>&1; then
  uv tool install --force --quiet "$SRC"
  echo "cli: uv tool install ($(command -v modgate || echo '~/.local/bin/modgate'))"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force "$SRC" >/dev/null
  echo "cli: pipx install"
else
  VENV="$PROJECT/.modgate/venv"
  [ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "$SRC"
  cat > "$PROJECT/.modgate/modgate" <<EOF
#!/bin/sh
exec "$VENV/bin/modgate" "\$@"
EOF
  chmod +x "$PROJECT/.modgate/modgate"
  CMD='"$CLAUDE_PROJECT_DIR"/.modgate/modgate'
  echo "cli: venv at $VENV, shim .modgate/modgate (add it to PATH, or call it by path)"
fi
fi

# 2 · skill (+ guideline + templates next to it)
SKILL="$PROJECT/.claude/skills/modgate"
mkdir -p "$SKILL/guideline" "$SKILL/templates"
cp "$KIT/skill/SKILL.md" "$SKILL/SKILL.md"
cp -R "$KIT/templates/." "$SKILL/templates/"
if compgen -G "$KIT/guideline/*.md" >/dev/null; then cp "$KIT"/guideline/*.md "$SKILL/guideline/"; fi
echo "skill: .claude/skills/modgate"

# 3 · hooks + permission rule, merged into .claude/settings.json (idempotent, additive)
"$PY" - "$KIT/hooks.json" "$PROJECT/.claude/settings.json" "$CMD" <<'PYEOF'
import json, sys
from pathlib import Path

kit, target, cmd = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
snippet = json.loads(kit.read_text().replace('"modgate ', json.dumps(cmd)[:-1] + " "))
if cmd != "modgate":
    snippet["permissions"]["ask"].append("Bash(.modgate/modgate approve:*)")
settings = json.loads(target.read_text()) if target.is_file() and target.read_text().strip() else {}

hooks = settings.setdefault("hooks", {})
for event, groups in snippet["hooks"].items():
    have = hooks.setdefault(event, [])
    known = {h.get("command") for g in have for h in g.get("hooks", [])}
    for g in groups:
        if not all(h["command"] in known for h in g["hooks"]):
            have.append(g)
perms = settings.setdefault("permissions", {})
for key, rules in snippet["permissions"].items():
    lst = perms.setdefault(key, [])
    lst.extend(r for r in rules if r not in lst)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(settings, indent=2) + "\n")
PYEOF
echo "hooks: .claude/settings.json"

# 4 · modgate.yaml skeleton (the LLM asks once for the blanks)
if [ ! -f "$PROJECT/modgate.yaml" ]; then
  cat > "$PROJECT/modgate.yaml" <<EOF
project: $(basename "$PROJECT")
criticality:        # L0 explore · L1 internal · L2 product · L3 safety-critical (developer decides)
diagrams:           # mermaid | drawio
coding_standard:    # e.g. google
targets: {}         # name: "command run in the module dir", e.g. host: "python3 -m pytest -q"
EOF
  echo "config: modgate.yaml created"
fi

# 5 · .gitignore
touch "$PROJECT/.gitignore"
grep -qxF ".modgate/" "$PROJECT/.gitignore" || echo ".modgate/" >> "$PROJECT/.gitignore"
echo "done: $PROJECT"

#!/usr/bin/env bash
# Build the deliverables into dist/:
#   modgate-kit-v6/   install.sh + the Claude instructions for guideline v6 (claude/) + the tool (wheels/)
#   weather-station/  the example project, as a real project would look after running the installer
#   modgate-kit-v6.zip  both directories, portable (installs offline: one pure-Python wheel, zero deps)
# Usage: ./package.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-$REPO/.venv/bin/python}"
GUIDE_V="$(grep -m1 '^version:' "$REPO/kit/guideline/Dev-Guideline-with-LLMs.md" | awk '{print $2}')"
KIT_NAME="modgate-kit-v$GUIDE_V"
DIST="$REPO/dist"
KIT="$DIST/$KIT_NAME"
EX="$DIST/weather-station"
rm -rf "$DIST"; mkdir -p "$KIT/claude" "$KIT/wheels"

# 1 · the kit: installer, guide, Claude instructions, tool wheel
cp "$REPO/install.sh" "$KIT/"
cp "$REPO/kit/modgate-kit.md" "$KIT/$KIT_NAME.md"
(cd "$REPO/kit" && tar -cf - --exclude modgate-kit.md --exclude .gitkeep .) | tar -xf - -C "$KIT/claude"
"$PY" -m pip wheel --quiet --no-deps --wheel-dir "$KIT/wheels" "$REPO"

# 2 · the example project: tracked files only, then a real install of the kit into it
git -C "$REPO" archive --format=tar HEAD example/weather-station | tar -x -C "$DIST"
mv "$DIST/example/weather-station" "$EX" && rmdir "$DIST/example"
"$KIT/install.sh" --no-cli "$EX" >/dev/null

# 3 · zip both
(cd "$DIST" && zip -qr "$KIT_NAME.zip" "$KIT_NAME" weather-station)
echo "built $DIST: $KIT_NAME/ · weather-station/ · $KIT_NAME.zip ($(du -h "$DIST/$KIT_NAME.zip" | cut -f1))"

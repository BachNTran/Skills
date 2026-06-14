#!/usr/bin/env bash
# claude-notify.sh — play a macOS sound for Claude Code hook events.
#
# Usage:  claude-notify.sh <event>
#   event = done       Claude finished responding (Stop hook)
#   event = attention  Claude needs you — a question or permission (Notification hook)
#
# Sounds are macOS system sounds in /System/Library/Sounds (play one to audition,
# e.g. `afplay /System/Library/Sounds/Glass.aiff`). Override per event with env vars:
#   CLAUDE_SOUND_DONE       (default: Glass)
#   CLAUDE_SOUND_ATTENTION  (default: Funk)
# Set a value to "off" to silence that event.
#
# The script always exits 0 so it can never block or fail a Claude Code turn.

set -u

event="${1:-done}"

case "$event" in
  done)      sound="${CLAUDE_SOUND_DONE:-Glass}" ;;
  attention) sound="${CLAUDE_SOUND_ATTENTION:-Funk}" ;;
  *)         sound="${CLAUDE_SOUND_DONE:-Glass}" ;;
esac

# Honor an explicit opt-out.
[ "$sound" = "off" ] && exit 0

# Only attempt playback on macOS with afplay available.
if ! command -v afplay >/dev/null 2>&1; then
  exit 0
fi

sound_file="/System/Library/Sounds/${sound}.aiff"
[ -f "$sound_file" ] || sound_file="/System/Library/Sounds/Glass.aiff"

# Play detached so the hook returns immediately and never delays the turn.
afplay "$sound_file" >/dev/null 2>&1 &

exit 0

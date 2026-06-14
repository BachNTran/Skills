#!/usr/bin/env bash
# claude-notify.sh — macOS sound + speech alert for Claude Code hook events.
#
# Usage:  claude-notify.sh <event>
#   event = done       Claude finished responding (Stop hook)
#   event = attention  Claude needs you — a question or permission (Notification hook)
#
# Delivery mode (env var CLAUDE_NOTIFY_MODE):
#   sound   chime only                 (default)
#   both    chime then spoken phrase
#   speech  spoken phrase only
#
# Chimes are macOS system sounds in /System/Library/Sounds (audition one with
# `afplay /System/Library/Sounds/Glass.aiff`). Speech uses the macOS `say` command.
#
# Per-event overrides (set in your shell profile so hooks inherit them):
#   CLAUDE_SOUND_DONE       chime for "done"        (default: Glass)
#   CLAUDE_SOUND_ATTENTION  chime for "attention"   (default: Funk)
#   CLAUDE_SPEAK_DONE       phrase for "done"       (default: "Claude is done")
#   CLAUDE_SPEAK_ATTENTION  phrase for "attention"  (default: "Claude needs your attention")
#   CLAUDE_NOTIFY_VOICE     `say` voice name        (default: macOS system voice)
# Set a chime to "off" to silence just its sound. Download a nicer voice from
# System Settings → Accessibility → Spoken Content, set it as the System voice,
# and speech upgrades automatically (CLAUDE_NOTIFY_VOICE left unset uses it).
#
# The script always exits 0 so it can never block or fail a Claude Code turn.

set -u

event="${1:-done}"
mode="${CLAUDE_NOTIFY_MODE:-sound}"

case "$event" in
  attention)
    sound="${CLAUDE_SOUND_ATTENTION:-Funk}"
    phrase="${CLAUDE_SPEAK_ATTENTION:-Claude needs your attention}"
    ;;
  *)
    sound="${CLAUDE_SOUND_DONE:-Glass}"
    phrase="${CLAUDE_SPEAK_DONE:-Claude is done}"
    ;;
esac

play_chime() {
  [ "$sound" = "off" ] && return
  command -v afplay >/dev/null 2>&1 || return
  local f="/System/Library/Sounds/${sound}.aiff"
  [ -f "$f" ] || f="/System/Library/Sounds/Glass.aiff"
  afplay "$f" >/dev/null 2>&1
}

speak() {
  [ -n "$phrase" ] || return
  command -v say >/dev/null 2>&1 || return
  if [ -n "${CLAUDE_NOTIFY_VOICE:-}" ]; then
    say -v "$CLAUDE_NOTIFY_VOICE" "$phrase" >/dev/null 2>&1
  else
    say "$phrase" >/dev/null 2>&1
  fi
}

# Run detached so the hook returns immediately and never delays the turn.
# Chime first, then speech, so they don't overlap.
{
  case "$mode" in
    sound)  play_chime ;;
    speech) speak ;;
    *)      play_chime; speak ;;
  esac
} >/dev/null 2>&1 &

exit 0

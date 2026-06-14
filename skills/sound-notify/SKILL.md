---
name: sound-notify
description: Set up macOS sound and/or spoken notifications for Claude Code so you hear when Claude finishes a turn and when it needs your attention (a question or a permission prompt). Wires a Stop hook and a Notification hook in settings.json to play a system chime and speak a phrase. Use when the user asks for sound/audio/voice alerts, a "ding when done", spoken notifications, or to be notified when Claude needs input.
---

# /sound-notify — macOS sound + speech alerts for Claude Code

Play a macOS chime and/or speak a phrase on two events so you don't have to watch the terminal:

- **Done** — Claude finishes responding (the `Stop` hook). Default: **Glass** chime + "Claude is done".
- **Attention** — Claude needs you: a question or a permission prompt (the `Notification`
  hook). Default: **Funk** chime + "Claude needs your attention".

Playback is done by `scripts/claude-notify.sh`: `afplay` plays a chime from `/System/Library/Sounds`
and `say` speaks the phrase. Delivery mode is `both` (chime then speech), `sound`, or `speech` via
`CLAUDE_NOTIFY_MODE`. It runs detached and always exits 0, so it never delays or fails a turn.

## When to use
- The user wants an audible alert when Claude is done or is waiting on them.
- The user mentions sounds, dings, beeps, or notifications for Claude Code.

## When NOT to use
- Non-macOS hosts (no `afplay`/`say`). The script no-ops safely, but there is no alert to deliver.
- The user wants desktop/push notifications rather than sound/speech — that is a different mechanism.

## Setup (what to do when invoked)

1. **Install the script.** Copy `scripts/claude-notify.sh` to `~/.claude/hooks/claude-notify.sh`
   and make it executable:
   ```bash
   mkdir -p ~/.claude/hooks
   cp "$(dirname SKILL.md)/scripts/claude-notify.sh" ~/.claude/hooks/claude-notify.sh
   chmod +x ~/.claude/hooks/claude-notify.sh
   ```
   (If the skill is installed under `~/.claude/skills/sound-notify/`, the source is
   `~/.claude/skills/sound-notify/scripts/claude-notify.sh`.)

2. **Wire the hooks** into `~/.claude/settings.json`. Merge this into the existing JSON — do not
   clobber other keys or other hooks already under `Stop`/`Notification`:
   ```json
   {
     "hooks": {
       "Stop": [
         { "hooks": [ { "type": "command", "command": "~/.claude/hooks/claude-notify.sh done" } ] }
       ],
       "Notification": [
         { "hooks": [ { "type": "command", "command": "~/.claude/hooks/claude-notify.sh attention" } ] }
       ]
     }
   }
   ```

3. **Verify** the alerts play:
   ```bash
   ~/.claude/hooks/claude-notify.sh done
   ~/.claude/hooks/claude-notify.sh attention
   ```
   Hooks load on a new session (or `/hooks` reloads them in the running one).

## Customizing

**Chime** — audition any system sound: `afplay /System/Library/Sounds/Hero.aiff`. Available: Basso,
Blow, Bottle, Frog, Funk, Glass, Hero, Morse, Ping, Pop, Purr, Sosumi, Submarine, Tink.

**Voice** — speech uses the macOS **System voice** by default. For a more natural voice, download
a Premium/Enhanced one from *System Settings → Accessibility → Spoken Content → System voice →
Manage Voices…*, set it as the System voice, and speech upgrades with no script change. To pin a
specific voice instead, set `CLAUDE_NOTIFY_VOICE` (e.g. `Daniel`); list voices with `say -v '?'`.

Override without editing the script via env vars (set them in your shell profile so hooks inherit
them):

| Variable                 | Controls                          | Default                          |
|--------------------------|-----------------------------------|----------------------------------|
| `CLAUDE_NOTIFY_MODE`     | `both` / `sound` / `speech`       | `both`                           |
| `CLAUDE_SOUND_DONE`      | the "done" chime                  | `Glass`                          |
| `CLAUDE_SOUND_ATTENTION` | the "attention" chime             | `Funk`                           |
| `CLAUDE_SPEAK_DONE`      | the "done" phrase                 | `Claude is done`                 |
| `CLAUDE_SPEAK_ATTENTION` | the "attention" phrase            | `Claude needs your attention`    |
| `CLAUDE_NOTIFY_VOICE`    | `say` voice name                  | macOS system voice               |

Set a chime to `off` to silence just its sound, or `CLAUDE_NOTIFY_MODE=sound` to drop speech entirely.

## How it works

`settings.json` registers a command hook on each event. Claude Code runs the command, passing the
event name as the first argument (`done` or `attention`); the script maps that to a chime + phrase
and plays them in the background. The `Stop` hook fires when the main agent stops responding; the
`Notification` hook fires when Claude Code surfaces a notification — including permission requests
and idle prompts waiting for your input.

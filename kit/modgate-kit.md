# modgate kit — Claude instructions for the Dev Guideline with LLMs (v6)

Install this into any project and Claude works the guideline's way: modules, gates by criticality,
grill-until-aligned, traceability, and never approving on its own.

## Install
```bash
./install.sh <project-dir>            # installs the modgate CLI too (uv → pipx → project venv)
./install.sh --no-cli <project-dir>   # CLI already on PATH machine-wide: instructions only
```
Needs Python ≥ 3.10. Works offline (the tool is one pure-Python wheel, zero dependencies).
macOS / Linux; on Windows use WSL for now.

## What lands in the project
| Installed at | From | What it is |
|---|---|---|
| `.claude/skills/modgate/SKILL.md` | `claude/skill/SKILL.md` | **the rules Claude follows** |
| `.claude/skills/modgate/guideline/` | `claude/guideline/` | the full guideline v6 (approved) |
| `.claude/skills/modgate/templates/` | `claude/templates/` | module templates, one per kind |
| `.claude/settings.json` | `claude/hooks.json` | hooks that run modgate + *ask* before `modgate approve` |
| `modgate.yaml` | created if missing | project settings; Claude asks once for the blanks |
| `.gitignore` | appended | `.modgate/` (tool cache) |

Then write a short project `CLAUDE.md` (project map, commands, project rules) — see the
`weather-station` example next to this kit for what a real project looks like after install.

## Contents
- `install.sh` — the installer (re-runnable, never clobbers existing settings)
- `claude/` — the Claude instructions: `skill/`, `hooks.json`, `guideline/`, `templates/`
- `wheels/` — the `modgate` tool (`sync` · `pending` · `approve`)
- `crew/` — the crew pack (draft, not installed by `install.sh` yet): `skills/` (crew, caveman-plus, wiki, plus vendored ponytail, caveman, drawio, graphify, grilling — see `crew/VENDORED.md`), `agents/` (architect, builder, tester, qa, auditor, writer: hats, not headcount), `tools/` (vendor scan, copy, check).

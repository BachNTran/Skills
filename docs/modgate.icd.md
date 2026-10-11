---
title: modgate · ICD (CLI contract)
version: 1
status: draft
approved:
---

# modgate · ICD — the CLI

## Commands
| Command | Does | Run by |
|---|---|---|
| `modgate sync [path…] [--test <target>] [--strict] [--json]` | rehash (cache) · drift · trace regeneration · draw.io export · target test run · lint. Paths limit the scope to the modules containing (or below) them. Silent on success. | PostToolUse, Stop, CI |
| `modgate sync --hook` | reads Claude Code hook JSON on stdin (see Hooks) | hooks |
| `modgate pending [--report] [--json] [--hook]` | open items grouped into dependency-disjoint module sets; `--report` writes `.modgate/report.html` and prints its path | SessionStart, on demand |
| `modgate approve <module> <doc\|REQ-ID\|all> [--by <name>\|ai-reviewer:<model>]` | sets status + approved hash, records hashes, appends the changelog. `doc` may be a role (`icd`), a file name or a path. | LLM proposes, developer confirms |

## Output
One line per finding: `CODE  module  id  files  → next action`. Violations carry an `E:` prefix.
`pending` prints `# set N · modules…` before each dependency-disjoint group.

| Exit | Meaning |
|---|---|
| 0 | clean |
| 1 | findings (or open pending items) |
| 2 | violations (or `--strict` with findings; approval rejected) |
| 3 | error (no `modgate.yaml`, unknown module/doc/target, bad yaml) |

| Code | Where | Meaning → action |
|---|---|---|
| CONFIG | both | criticality / diagrams / coding_standard unset, or a target undefined → ask once, save |
| DRAFT | pending | controlled doc (or never-approved code) not approved → approve (who, per criticality) |
| DRIFT | both | bound file changed, REQ section unchanged → revisit REQ/TCs or `approve <m> REQ-…` |
| STALE | pending | unexplained change since approval → deep review, `approve <m> all` |
| DEPCHANGED | pending | dependency hash changed → re-test (ICD same) or deep review (ICD changed) |
| UNTESTED | pending | required target has no passing record for the current hash → `sync --test` |
| UNBOUND / BADBIND | both / sync | source bound to no REQ / binding points nowhere |
| BACKLOG | pending | `- [ ]` line in `<m>.activity.md` |
| REDRAFT | sync | approved doc body changed without going back to draft |
| NAMING, SIZE, CHANGELOG, APPEND, APPROVER, DRAWIO, TESTFAIL, BADDEP, DEPCYCLE | sync | lint and run results |

## Files
| File | Owner | Notes |
|---|---|---|
| `modgate.yaml` | developer | `project, criticality, diagrams, coding_standard, targets: {name: cmd}`, optional `ignore:`, `criticality_presets: {L2b: {ai_may_approve: [..]}}`. Target commands run in the module dir; `{root}`, `{module}`, `{python}` are substituted. |
| `<m>.md` frontmatter | LLM drafts | `kind, criticality, deps: [..], targets: [..], sources: [..], version, status, approved` |
| `docs/<m>.bind.yaml` | LLM drafts | `REQ-ID: [files or dirs relative to the module]` |
| `docs/<m>.trace.md` | modgate only | header, matrix, `modgate-state:` yaml (approved hashes, approvals, test records) |
| `.modgate/` | modgate only | `cache.json`, `logs/`, `report.html`; gitignored |

## Hooks
Formats checked against https://code.claude.com/docs/en/hooks (2026-09-27): PostToolUse and SessionStart
cannot block and ignore exit 2, so findings go back as `hookSpecificOutput.additionalContext` with exit 0;
Stop honours exit 2 + stderr to keep Claude working.

| Event | Command | Output |
|---|---|---|
| SessionStart (`startup\|resume\|clear\|compact`) | `modgate pending --hook` | `additionalContext`: pending list |
| PostToolUse (`Edit\|Write\|MultiEdit`) | `modgate sync --hook` | `additionalContext`: findings of the edited file's module; nothing when clean |
| Stop | `modgate sync --hook` | exit 2 + violations on stderr; exit 0 otherwise or when `stop_hook_active` |
| permissions | `ask: ["Bash(modgate approve:*)"]` | approval stays a developer act |

## Criticality presets (gates an AI reviewer may approve)
| Level | ai-reviewer may approve |
|---|---|
| L0 | overview, brief, req, tests, bind, resource, code (developer: findings = ICD) |
| L1 | icd, tests, bind, code |
| L2 | bind, code |
| L3 | nothing |
`code` = REQ reviews after code changes. Unset criticality is treated as L3 for AI approvals.

## Install
`./install.sh <project-dir>`: CLI via `uv tool install`, else `pipx install`, else `<project>/.modgate/venv`
+ shim `.modgate/modgate` (hooks then call the shim). Copies `kit/skill` (+ `guideline/`, `templates/`) to
`.claude/skills/modgate/`, merges `kit/hooks.json` into `.claude/settings.json`, creates `modgate.yaml`,
adds `.modgate/` to `.gitignore`. Templates live in `kit/templates/blocks/` (code, adapter, protocol, data,
tool — used through their interface) and `kit/templates/roots/` (system, deploy, host-service, study).

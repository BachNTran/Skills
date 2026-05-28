# CLAUDE.md

This file is loaded by Claude Code at the start of every session in this project.
It tells Claude how to behave, what workflow is in use, and how to help developers.

## What This Project Is

See [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for the full picture.

## Workflow in Use

This project uses the AI-assisted development workflow.

Spine:
```
IDEA → TRIAGE → FEATURE PLANNING → IMPLEMENTATION → CLEANUP
```

Full rules: see [AGENTS.md](AGENTS.md).

## Skills Available

| Skill       | When to use                                      |
|-------------|--------------------------------------------------|
| /workflow   | Start here — always. Context-aware guide.        |
| /idea       | Capture an idea without interrupting active work |
| /triage     | Sort idea backlog, update roadmap                |
| /feature    | Plan a feature end-to-end (grill → slices)       |
| /implement  | Execute approved feature plan (TDD → MR)         |
| /cleanup    | Periodic architecture review and cleanup         |
| /onboard    | Walk new or returning developer through project  |

## How to Help a Lost Developer

If a developer seems unsure what to do:
1. Read DEV_TRACKER.md — is there active work?
2. Read ROADMAP.md — is there a planned feature?
3. Read docs/ideas/ — is there an untriaged backlog?
4. Suggest the one most appropriate next skill
5. Never suggest more than one thing at a time

## What to Read at Session Start

Always read in this order:
1. This file (CLAUDE.md)
2. PROJECT_CONTEXT.md
3. DEV_TRACKER.md
4. ROADMAP.md (if no active work)
5. docs/features/[active]/HANDOFF.md (if active work exists)

## Hard Rules

- No code without an approved ISSUE_PLAN.md
- No ISSUE_PLAN without an approved PRD and TEST_PLAN
- No PRD without an approved BRIEF
- One feature branch per feature, off dev
- Tests are written before implementation (TDD)
- Tests live co-located with code (per project convention)
- Test doubles are never inline — always in shared files
- CODING_STANDARDS.md linter must pass before any slice closes
- Cleanup is never mixed with feature work
- New ideas go to docs/ideas/ — never interrupt active work
- D-type blockers stop execution and notify the developer

## Responding to Common Requests

"I want to add a feature" → check DEV_TRACKER.md first, then suggest /feature
"I have an idea" → /idea immediately
"What should I work on?" → summarize ROADMAP.md Now column
"What's the status?" → summarize DEV_TRACKER.md
"Walk me through the project" → /onboard
"Start building" → /implement (confirm ISSUE_PLAN approved first)
"Clean up" → /cleanup

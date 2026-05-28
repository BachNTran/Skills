# AGENTS.md

Canonical instructions for any AI coding agent in this project (Claude Code, Codex, Cursor, and other AGENTS.md-aware tools). Read this at the start of every session.

## Mission

Develop cleanly, incrementally, and testably. Optimize for controlled progress, clear behavior, small diffs, durable tests, and understandable architecture — not for fast code generation.

## Workflow Spine

```
IDEA → TRIAGE → FEATURE PLANNING → IMPLEMENTATION → CLEANUP
```

Full pipeline: idea capture → triage → domain context (hardware only) → feature grill → PRD → test-plan grill → architecture fit → issue slicing → execution (TDD, autonomous) → automated review → handoff → repeat → feature close → cleanup.

## Skills

| Skill      | When to use                                       |
|------------|---------------------------------------------------|
| /workflow  | Start here. Context-aware guide to the next step. |
| /idea      | Capture an idea without interrupting active work. |
| /triage    | Sort the idea backlog, update the roadmap.        |
| /feature   | Plan a feature end-to-end (grill → slices).       |
| /implement | Execute an approved feature plan (TDD → MR).      |
| /cleanup   | Periodic architecture review and cleanup.         |
| /onboard   | Walk a developer through the project.             |

When unsure, run /workflow. (Agents without slash-command support: read the matching file under skills/ and follow it.)

## Read at Session Start

1. AGENTS.md (this file)
2. PROJECT_CONTEXT.md
3. DEV_TRACKER.md
4. ROADMAP.md if no active work, else docs/features/[active]/HANDOFF.md

## Hard Rules

1. No code without an approved ISSUE_PLAN.md
2. No ISSUE_PLAN without an approved PRD and TEST_PLAN
3. No PRD without an approved BRIEF
4. New ideas go to docs/ideas/ — never interrupt active work
5. One feature active at a time; one feature branch per feature, off dev
6. Tests written before implementation (TDD red/green/refactor)
7. Tests co-located with code (per project convention)
8. Test doubles never inline — always in shared files
9. No new dependency without developer approval
10. No architecture boundary change without an ADR
11. No completion claim without test evidence
12. Stop on: scope beyond slice budget, new dependency needed, or unclear boundary
13. Cleanup is never mixed with feature work
14. CODING_STANDARDS linter must pass before a slice closes

## Architecture Rules

- Prefer deep modules with thin public interfaces
- Keep external systems behind adapters/boundaries; domain logic separate from infrastructure
- If tests are hard to write, inspect architecture before forcing mocks
- Reuse existing helpers, doubles, and utilities before creating new ones
- A new module requires a single stated responsibility and a minimal public interface

## Test Double Rules

- One authoritative double per external dependency, in its own file with a spec document
- Double simulates real behavior as closely as possible; document known gaps
- Known gaps require integration tests against the real system
- Never create ad-hoc inline mocks

## Completion Report (every slice)

```
Slice / Status / Behavior / Tests added / Files changed / Files count [n of budget]
Regression PASS|FAIL / Reuse found / New doubles / Risks / Next slice unblocked
```

## Human Approval Required

Promoting an idea to the roadmap · approving BRIEF / PRD / TEST_PLAN / ISSUE_PLAN · D-type blockers during execution · architecture boundary changes · new dependencies · feature-close sign-off.

## Responding to Common Requests

- "I have an idea" → /idea immediately
- "I want to add a feature" → check DEV_TRACKER.md, then /feature
- "What should I work on?" → summarize ROADMAP.md Now column
- "What's the status?" → summarize DEV_TRACKER.md
- "Walk me through the project" → /onboard
- "Start building" → /implement (confirm ISSUE_PLAN approved first)
- "Clean up" → /cleanup

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
3. ProjectManagement/DEV_TRACKER.md
4. ProjectManagement/ROADMAP.md if no active work, else ProjectManagement/features/[active]/HANDOFF.md

## Criticality & Autonomy

Read `PROJECT_CONTEXT.md` → **Criticality & Autonomy**. The declared tier governs how much
you decide vs. defer:

- **EXPLORE** — after the idea is grilled, implement and ship autonomously; light trace.
- **STANDARD** (default) — get PRD, test plan, and slice plan approved; then implement solo; full trace.
- **CRITICAL** — the developer reviews every slice, diff, and line. You are a second eye and
  do grunt work only (build fixes, scaffolding, syntax checks, brainstorming). Never auto-merge.
  Full trace with rationale required.

A feature's `BRIEF.md` may override the project tier (with a reason). **If `criticality:` is
unset in PROJECT_CONTEXT.md, run a short config grill, propose a tier, and write it there
before doing feature work.**

## Architecture Docs

Default paths used by the workflow skills. If you rename or relocate any of these to match your project's naming convention, update this table — the agent reads this section to find the actual files.

| Doc                  | Default path                                |
|----------------------|---------------------------------------------|
| System overview      | `docs/architecture/ARCHITECTURE.md`         |
| Module map           | `docs/architecture/MODULE_MAP.md`           |
| Shared language      | `docs/architecture/CONTEXT.md`              |
| Glossary             | `docs/architecture/GLOSSARY.md`             |
| Architecture review  | `docs/architecture/ARCHITECTURE_REVIEW.md`  |

See `docs/architecture/README.md` for what to put in each.

## Traceability IDs

Stable IDs let any artifact link to any other and power the bottom-up walk
(code → test → REQ → decision). The `TRACE.md` index is **generated** from these — never
hand-edit it. Regenerate per-feature `TRACE.md` (tables + Mermaid graph + orphan report) with:

```
python3 tools/trace_index.py            # regenerate all features' TRACE.md
python3 tools/trace_index.py --check    # non-zero exit if any orphan warnings (CI/hook gate)
```

| ID        | Lives in                                   | Means                                    |
|-----------|--------------------------------------------|------------------------------------------|
| DEC-###   | feature `DECISIONS.md` (or `docs/decisions/`) | a decision converged on while grilling |
| REQ-###   | feature `PRD.md`                           | a requirement (EARS + inline rationale)  |
| TC-###    | feature `TEST_PLAN.md`                     | a test case                              |
| CMP-###   | feature `COMPLAINTS.md`                    | a logged complaint → revision trigger    |
| ADR-####  | `docs/decisions/` or feature `decisions/`  | an architecture decision record          |

Links are relative and traversable both ways:
- REQ `from:` DEC  ·  DEC `serves:` REQ
- TC names its REQ  ·  REQ is proven-by TC (derived)
- code annotation `// @covers FEAT-NNNN:REQ-###` ties an implementation region to a requirement (feature-qualified, since REQ IDs are feature-local)

Rules:
- Never reuse or renumber an ID. **Supersede, don't delete** (`status:` + `superseded_by:`).
- The ID is the only formal part of a record — the body stays informal prose.

## Memory & Preferences

The project gets smarter over time via **project-local** memory (never written to the global
skills dir):

- `PREFERENCES.md` — design taste + workflow corrections. The `SessionStart` hook injects its
  **Active preferences** digest each session, so the developer never re-explains their style.
- `DECISIONS.md` (per feature) — decision rationale, linked to requirements.
- `docs/architecture/GLOSSARY.md` and `docs/knowledge-base/` — domain facts.

At milestones (a slice merges, a feature closes) and whenever the developer corrects you:
1. Regenerate trace: `python3 tools/trace_index.py`.
2. If you learned a durable preference or received a correction, append it to `PREFERENCES.md`
   — and, if it is currently-true and high-value, to the **Active preferences** digest.
3. Keep the digest small; move superseded items to the Retired section (never delete).

## Hard Rules

1. No code without an approved ISSUE_PLAN.md
2. No ISSUE_PLAN without an approved PRD and TEST_PLAN
3. No PRD without an approved BRIEF
4. New ideas go to ProjectManagement/ideas/ — never interrupt active work
5. One feature active at a time; one feature branch per feature, off the developer-confirmed base (default: the current branch — `/implement` asks before branching)
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

## Intent Router — the developer never needs to remember a command

The developer states intent in natural language. Classify it and run the matching phase
yourself; do not make them recall a skill name. Slash commands remain as manual escape
hatches, but should never be required.

| The developer says…                                   | Intent    | You run                                                                 |
|--------------------------------------------------------|-----------|-------------------------------------------------------------------------|
| "I have an idea", a rubber-duck musing                 | IDEA      | /idea (capture only, don't derail active work)                          |
| "add X", "build X", "I want a feature that…"           | ADD       | check DEV_TRACKER, then /feature                                        |
| "change X", "X should instead…"                        | CHANGE    | /feature on the existing area — modify the PRD/tests, record new DEC    |
| "remove X", "drop X"                                   | REMOVE    | /feature removal path — scan references first                           |
| "why does X exist?", "what tests X?", "how is X covered?" | EXPLAIN | walk the trace: open the feature `TRACE.md`, follow code→TC→REQ→DEC, answer with the chain |
| "I don't like how X works", "this is wrong"            | COMPLAINT | run the complaint→revision loop (see COMPLAINTS section)                |
| "what should I do?", "status", "start building"        | NAVIGATE  | /workflow                                                               |
| no scaffold, or `criticality:` unset                   | CONFIG    | /workflow → Config Grill                                                |

## Grilling style

Grill so understanding aligns and decisions get recorded — but ask **all the questions you
can at once**, not one at a time, to spare the developer's focus. Only sequence a question
when its answer genuinely changes the next one. Recommend an answer for each. The moment a
choice converges, record a `DEC-###` (informal prose, stable ID) — accountability rests with
the human who converged on it, not with you.

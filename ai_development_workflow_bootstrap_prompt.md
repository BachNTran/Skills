# AI Development Workflow Bootstrap Prompt

You are helping me set up a disciplined AI-assisted software development workflow inside this repository.

Your job is to create the project workflow system, not to implement product features yet.

Do not modify application source code unless explicitly told later.

The goal is to create a workflow where:
- Many ideas can be captured without derailing current work.
- Every idea is triaged before development.
- Every selected feature is drilled down until the vision is clear.
- Every feature has durable artifacts explaining what, why, when, and how.
- Every feature is broken into vertical slices.
- Every slice is implemented with tests.
- Every behavior becomes protected by regression tests.
- Every developer or LLM agent can quickly understand the architecture.
- No feature work creates messy, broad, unexplained code changes.
- No chat history is required to resume work.

Use this workflow spine:

```text
IDEA CAPTURE
→ TRIAGE
→ GRILL-WITH-DOCS / DOMAIN MODEL
→ PRD
→ ISSUE SLICING
→ ACTIVE SLICE
→ TDD IMPLEMENTATION
→ REVIEW
→ HANDOFF
→ ARCHITECTURE CLEANUP
→ REPEAT
```

This workflow is inspired by Matt Pocock-style agent skills:
- triage
- grill-with-docs
- to-prd
- to-issues
- tdd
- review
- handoff
- improve-codebase-architecture

References:
- Matt Pocock / AI Hero skills: https://www.aihero.dev/skills
- Matt Pocock, “5 Agent Skills I Use Every Day”: https://www.aihero.dev/5-agent-skills-i-use-every-day
- OpenAI Codex `AGENTS.md` guide: https://developers.openai.com/codex/guides/agents-md
- AGENTS.md project: https://agents.md/

---

## Prime Directive

Do not optimize for fast code generation.

Optimize for:
- Clean incremental progress
- Understandable architecture
- Small tested changes
- Durable documentation
- Explicit decisions
- Easy LLM onboarding
- Easy human review
- Low clutter
- High trust in tests

---

## Hard Rules

1. No code without an Active Slice in `DEV_TRACKER.md`.
2. Only one Active Slice at a time.
3. New ideas go to `IDEA_INBOX.md`.
4. New ideas do not interrupt active work.
5. Selected features must go through grill-with-docs before PRD.
6. No PRD until the feature understanding is approved.
7. No issue slicing until the PRD is approved.
8. No implementation until one slice is activated.
9. Every implementation starts with a test or an explicit test strategy.
10. Every slice must be independently testable.
11. Every slice must produce observable behavior.
12. No unrelated refactor during feature work.
13. No broad reformatting during feature work.
14. No new dependencies without human approval.
15. No architecture boundary change without documentation.
16. No completion claim without test evidence.
17. If scope expands, stop and ask for approval.
18. If uncertainty affects architecture, record a Blocked Decision.
19. If cleanup is discovered, put it in Parking Lot.
20. If a new idea is discovered, put it in Idea Inbox.
21. Never rely on chat history as project memory.

---

# Task

Create the following workflow files and directories.

Do not implement product source code.

Create:

```text
repo/
├── AGENTS.md
├── PROJECT_CONTEXT.md
├── IDEA_INBOX.md
├── ROADMAP.md
├── DEV_TRACKER.md
├── docs/
│   ├── architecture/
│   │   ├── ARCHITECTURE.md
│   │   ├── MODULE_MAP.md
│   │   ├── CONTEXT.md
│   │   └── ARCHITECTURE_REVIEW.md
│   ├── decisions/
│   │   └── ADR-0001-template.md
│   ├── features/
│   │   └── README.md
│   └── logs/
│       ├── TEST_LOG.md
│       ├── CHANGE_LOG.md
│       └── RISK_LOG.md
├── issues/
│   └── ISSUE_TEMPLATE.md
├── skills/
│   ├── 00-triage.md
│   ├── 01-domain-model.md
│   ├── 02-grill-with-docs.md
│   ├── 03-to-prd.md
│   ├── 04-to-issues.md
│   ├── 05-activate-slice.md
│   ├── 06-tdd.md
│   ├── 07-review.md
│   ├── 08-handoff.md
│   └── 09-improve-architecture.md
└── scripts/
    ├── README.md
    ├── test.sh
    ├── lint.sh
    └── check.sh
```

If any file already exists, do not overwrite blindly.

Instead:
1. Read it.
2. Preserve existing useful content.
3. Append or merge the workflow content.
4. Report what you changed.

---

# File Contents to Create

## 1. `AGENTS.md`

Create `AGENTS.md` with this content:

````md
# AGENTS.md

## Mission

Develop cleanly, incrementally, and testably.

Do not optimize for fast code generation.
Optimize for controlled progress, clear behavior, small diffs, durable tests, and understandable architecture.

## Required Workflow

For new ideas:
1. Add the idea to `IDEA_INBOX.md`.
2. Do not write source code.
3. Do not create a branch.
4. Do not modify architecture.

For selected features:
1. Confirm the feature is listed in `ROADMAP.md`.
2. Run the grill-with-docs workflow.
3. Create or update the feature folder under `docs/features/FEAT-____-name/`.
4. Produce `GRILL_NOTES.md`.
5. Produce `PRD.md`.
6. Produce `ISSUE_PLAN.md`.
7. Create vertical-slice issue files in `issues/`.
8. Activate only one slice in `DEV_TRACKER.md`.

For implementation:
1. Read `DEV_TRACKER.md`.
2. Confirm there is exactly one Active Slice.
3. Read the linked issue file.
4. Confirm behavior, scope, non-scope, and test command.
5. Write or update tests first.
6. Implement the smallest change needed.
7. Run the listed test command.
8. Update `docs/logs/TEST_LOG.md`.
9. Update `docs/logs/CHANGE_LOG.md`.
10. Update the feature `HANDOFF.md`.
11. Report files changed, commands run, results, risks, and next suggested slice.

## Hard Rules

- No code without an Active Slice.
- Only one Active Slice at a time.
- New ideas go to `IDEA_INBOX.md`.
- Cleanup ideas go to the Parking Lot in `DEV_TRACKER.md`.
- No unrelated refactor during feature work.
- No broad reformatting during feature work.
- No new dependency without approval.
- No architecture change without documentation.
- No completion claim without test evidence.
- Stop if scope expands.
- Stop if the test strategy is unclear.
- Stop if the architecture boundary is unclear.

## Architecture Rules

- Prefer clear module ownership.
- Prefer deep modules with thin public interfaces.
- Avoid many tiny scattered files for one concept.
- Keep external systems behind adapters or boundaries.
- Keep business/domain logic separate from infrastructure details.
- Keep tests close to behavior.
- If tests are hard to write, inspect architecture before forcing mocks.

## Completion Report

Every implementation task must end with:

```text
Summary:
Files changed:
Tests added/changed:
Commands run:
Result:
Docs updated:
Risks:
Next suggested slice:
```

## Human Approval Required

Human approval is required for:
- Promoting an idea to Now
- Approving grill notes
- Approving PRD
- Approving issue/slice plan
- Activating a slice
- Expanding scope
- Adding dependencies
- Changing architecture boundaries
- Closing a feature
````

---

## 2. `PROJECT_CONTEXT.md`

Create `PROJECT_CONTEXT.md`:

````md
# Project Context

## Purpose

This file gives humans and AI agents a fast orientation to the project.

It should be short, durable, and updated only when project-level context changes.

## Product Sentence

We are building:

> TODO

## Target Users

- TODO

## Core Problem

The project exists to solve:

> TODO

## Design Principles

1. Keep the system understandable.
2. Build incrementally.
3. Prefer tested behavior over speculative architecture.
4. Keep documentation close to decisions.
5. Keep module boundaries clear.
6. Make the project easy for a new developer or LLM agent to understand.

## Non-Goals

- TODO

## Quality Bar

The project should be:
- Correct
- Testable
- Maintainable
- Easy to onboard into
- Safe to change incrementally
- Resistant to AI-generated clutter

## Current Development Workflow

This project uses:

```text
IDEA CAPTURE
→ TRIAGE
→ GRILL-WITH-DOCS
→ PRD
→ ISSUE SLICING
→ ACTIVE SLICE
→ TDD
→ REVIEW
→ HANDOFF
→ ARCHITECTURE CLEANUP
```
````

---

## 3. `IDEA_INBOX.md`

Create `IDEA_INBOX.md`:

````md
# Idea Inbox

## Purpose

This is the holding area for all ideas.

New ideas go here first so they do not derail active development.

## Rules

- Capture first. Judge later.
- Do not implement directly from this file.
- Do not create branches directly from this file.
- Do not promote ideas without triage.
- Do not delete ideas unless intentionally rejected.

## Status Values

| Status | Meaning |
|---|---|
| New | Captured but not evaluated |
| Needs Grill | Interesting but unclear |
| Parked | Useful later, not now |
| Promoted | Moved to roadmap |
| Rejected | Explicitly not doing |

## Ideas

| ID | Idea | Problem solved | Why now? | Status | Notes |
|---|---|---|---|---|---|
| IDEA-001 | TODO | TODO | TODO | New | TODO |
````

---

## 4. `ROADMAP.md`

Create `ROADMAP.md`:

````md
# Roadmap

## Purpose

This file limits active work.

Many ideas may exist, but only a small number should be considered for development.

## Current Objective

> TODO

## Rules

- Maximum one feature in Now.
- Maximum three features in Next.
- Later may contain many parked candidates.
- A feature cannot move to Now without human approval.
- A feature in Now must have a feature folder under `docs/features/`.

## Now

| Feature ID | Name | Source idea | Status | Notes |
|---|---|---|---|---|
| FEAT-0001 | TODO | IDEA-001 | Candidate | TODO |

## Next

| Feature ID | Name | Source idea | Why next? | Blocker |
|---|---|---|---|---|
| FEAT-0002 | TODO | TODO | TODO | TODO |

## Later

| Feature ID | Name | Source idea | Why parked? |
|---|---|---|---|
| FEAT-0003 | TODO | TODO | TODO |

## Rejected

| Source idea | Reason |
|---|---|
| TODO | TODO |
````

---

## 5. `DEV_TRACKER.md`

Create `DEV_TRACKER.md`:

````md
# Dev Tracker

## Purpose

This is the active development control board.

It tells humans and agents exactly what is being worked on, what is allowed, what is forbidden, and how to prove completion.

## Rules

- Only one Active Slice.
- No code without an Active Slice.
- Active Slice must link to an issue file.
- Done means tested and recorded.
- New ideas go to `IDEA_INBOX.md`.
- Cleanup ideas go to Parking Lot.
- Architecture uncertainty goes to Blocked Decisions.

---

## Active Slice

| Field | Value |
|---|---|
| Feature | None |
| Slice | None |
| Issue file | None |
| Branch | None |
| Goal | None |
| Allowed files/modules | None |
| Forbidden files/modules | None |
| Test command | None |
| Status | None |
| Last update | None |

---

## Slice Board

| Slice | Feature | Behavior | Status | Test command | Result | Notes |
|---|---|---|---|---|---|---|
| S001 | FEAT-0001 | TODO | Backlog | TODO | Not run | TODO |

Status values:

| Status | Meaning |
|---|---|
| Backlog | Planned but not active |
| Active | Current implementation target |
| Blocked | Waiting on decision or dependency |
| Review | Implementation done, waiting review |
| Done | Tested, reviewed, and recorded |

---

## Parking Lot

Use this when work reveals a new idea or cleanup need.

Do not perform these during active slice implementation.

| ID | Found during | Idea / cleanup | Action |
|---|---|---|---|
| P-001 | TODO | TODO | Ignore / Create idea / Create issue |

---

## Blocked Decisions

Use this when continuing would require guessing.

| ID | Slice | Question | Options | Recommendation | Human needed? | Status |
|---|---|---|---|---|---|---|
| D-001 | TODO | TODO | A / B / C | TODO | Yes | Open |
````

---

## 6. `docs/architecture/ARCHITECTURE.md`

Create `docs/architecture/ARCHITECTURE.md`:

````md
# Architecture

## Purpose

This file explains the project architecture in a way that a developer or LLM agent can understand quickly.

Keep it short. If this file becomes too large, split details into module-specific docs and link them.

## One-Screen Architecture

TODO: Describe the system in 10 lines or fewer.

## Main Modules

| Module | Owns | Does not own | Public API | Tests |
|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO |

## Dependency Rule

Allowed direction:

```text
app / interface layer
→ domain / core layer
→ infrastructure / adapters
```

Forbidden direction:

```text
core → app
core → infrastructure details
unrelated module → unrelated module internals
```

## Extension Rule

Before adding a new module, answer:

1. Which existing module almost owns this?
2. Why can this not live there?
3. What public interface is needed?
4. What test proves the new boundary works?
5. What documentation must be updated?

## Architecture Change Rule

Architecture changes require:
- Explanation in this file or a linked module doc
- ADR if the decision is significant
- Tests that protect existing behavior
- Separate refactor slice if not required for active feature
````

---

## 7. `docs/architecture/MODULE_MAP.md`

Create `docs/architecture/MODULE_MAP.md`:

````md
# Module Map

## Purpose

This is the fast navigation map for humans and agents.

Use this file to answer:
- Where should I start reading?
- Which module owns this behavior?
- Where should a new change likely go?
- What files should not be touched?

## Read Order for New Agents

1. `PROJECT_CONTEXT.md`
2. `AGENTS.md`
3. `ROADMAP.md`
4. `DEV_TRACKER.md`
5. `docs/architecture/ARCHITECTURE.md`
6. This file
7. Active issue file

## Module Ownership

| Area | Path | Owns | Read first |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

## Change Routing

| If changing... | Start here | Avoid touching |
|---|---|---|
| TODO | TODO | TODO |

## Test Routing

| Behavior | Test location | Command |
|---|---|---|
| TODO | TODO | TODO |
````

---

## 8. `docs/architecture/CONTEXT.md`

Create `docs/architecture/CONTEXT.md`:

````md
# Context and Shared Language

## Purpose

This file captures domain language and shared terms so humans and agents use the same vocabulary.

Update this during grill-with-docs when terminology becomes clear.

## Terms

| Term | Meaning | Used in | Notes |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

## Domain Rules

| Rule | Explanation | Source |
|---|---|---|
| TODO | TODO | TODO |

## Open Terminology Questions

| Question | Context | Status |
|---|---|---|
| TODO | TODO | Open |
````

---

## 9. `docs/architecture/ARCHITECTURE_REVIEW.md`

Create `docs/architecture/ARCHITECTURE_REVIEW.md`:

````md
# Architecture Review

## Purpose

This file records architecture cleanup proposals.

Architecture cleanup is scheduled work. It is not mixed into feature slices.

## When to Run Architecture Review

Run after:
- Every 3 to 5 completed slices
- A feature is completed
- Tests become hard to write
- Module ownership becomes confusing
- The same concept appears scattered across files
- Agents repeatedly misunderstand the structure

## Current Review

### Trigger

TODO

### Confusion Points

| Area | Problem | Impact |
|---|---|---|
| TODO | TODO | TODO |

### Deepening Opportunities

| Module | Current issue | Proposed improvement | Risk |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

### Recommended Refactor Slices

| Slice | Behavior preserved | Test protection | Priority |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

### Decision

Proceed / Park / Reject

Reason:

TODO
````

---

## 10. `docs/decisions/ADR-0001-template.md`

Create `docs/decisions/ADR-0001-template.md`:

````md
# ADR-0001: <Decision Title>

## Status

Proposed / Accepted / Rejected / Superseded

## Date

YYYY-MM-DD

## Context

What situation forced this decision?

## Decision

What did we decide?

## Consequences

What becomes easier?

- TODO

What becomes harder?

- TODO

## Alternatives Considered

| Option | Pros | Cons | Reason rejected |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

## Related Artifacts

- PRD:
- Issue:
- Tests:
````

---

## 11. `docs/features/README.md`

Create `docs/features/README.md`:

````md
# Feature Documentation

Each selected feature gets its own folder:

```text
docs/features/FEAT-0001-feature-name/
├── GRILL_NOTES.md
├── PRD.md
├── ISSUE_PLAN.md
├── TEST_PLAN.md
├── REVIEW.md
└── HANDOFF.md
```

## Feature Lifecycle

1. Candidate appears in `ROADMAP.md`
2. Feature folder is created
3. `GRILL_NOTES.md` captures drill-down
4. `PRD.md` freezes approved requirements
5. `ISSUE_PLAN.md` breaks work into vertical slices
6. `TEST_PLAN.md` explains test strategy
7. `REVIEW.md` records slice/feature review
8. `HANDOFF.md` lets another developer or agent resume

## Rule

A feature is not done unless its handoff file explains:
- What was built
- What was tested
- What remains
- Where the important code lives
- What risks remain
````

---

## 12. `docs/logs/TEST_LOG.md`

Create `docs/logs/TEST_LOG.md`:

````md
# Test Log

## Purpose

This file records test evidence.

Do not claim a slice is done unless the test result is recorded here.

## Entries

### YYYY-MM-DD - FEAT-____ / S____

Command:

```bash
TODO
```

Result:

Pass / Fail

Tests added or changed:

- TODO

Behavior covered:

- TODO

Known gaps:

- TODO

Notes:

TODO
````

---

## 13. `docs/logs/CHANGE_LOG.md`

Create `docs/logs/CHANGE_LOG.md`:

````md
# Change Log

## Purpose

This file records meaningful project changes.

Use it to understand what changed, why, and where.

## Entries

### YYYY-MM-DD - FEAT-____ / S____

Changed:

- TODO

Why:

- TODO

Files affected:

- TODO

Tests:

- TODO

Risk:

- TODO
````

---

## 14. `docs/logs/RISK_LOG.md`

Create `docs/logs/RISK_LOG.md`:

````md
# Risk Log

## Purpose

This file tracks known risks so they are not lost in chat history.

## Risks

| ID | Area | Risk | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| RISK-001 | TODO | TODO | Low / Med / High | TODO | Open |
````

---

## 15. `issues/ISSUE_TEMPLATE.md`

Create `issues/ISSUE_TEMPLATE.md`:

````md
# Slice: FEAT-____-S____ <Behavior Name>

## Status

Backlog / Active / Blocked / Review / Done

## Linked Artifacts

- PRD:
- Issue plan:
- Handoff:

## Behavior

After this slice, the system can:

> TODO

## Observable Result

I can verify it by:

> TODO

## Scope

Allowed files/modules:

- TODO

## Non-Scope

Do not touch:

- TODO

## Acceptance Criteria

- [ ] Behavior works
- [ ] Test exists or test strategy is explicitly documented
- [ ] Test command passes
- [ ] Docs updated if behavior or architecture changed
- [ ] No unrelated refactor
- [ ] No new dependency unless approved
- [ ] Result recorded in `docs/logs/TEST_LOG.md`
- [ ] `DEV_TRACKER.md` updated

## Test Plan

Command:

```bash
TODO
```

Expected result:

> TODO

## File Change Budget

Expected changed files:

> TODO

Maximum changed files before stopping:

> TODO

## Risks

- TODO

## Blockers

- TODO

## Review Checklist

- [ ] Scope respected
- [ ] Acceptance criteria met
- [ ] Tests pass
- [ ] Logs updated
- [ ] Handoff updated
````

---

# Skill Files

Create these skill files.

Each skill file is an instruction document for an AI agent.

---

## `skills/00-triage.md`

````md
# Skill: triage

## Purpose

Turn messy ideas into clear roadmap candidates.

Use when:
- There are many ideas in `IDEA_INBOX.md`
- The roadmap is unclear
- The user wants to decide what deserves attention first

## Inputs

- `IDEA_INBOX.md`
- `ROADMAP.md`
- `PROJECT_CONTEXT.md`

## Outputs

- Updated `IDEA_INBOX.md`
- Updated `ROADMAP.md`
- Triage notes in response

## Rules

- Do not write source code.
- Do not create implementation issues.
- Do not promote ideas without a clear reason.
- Do not reject ideas permanently unless the user approves.
- If an idea is exciting but unclear, mark it `Needs Grill`.

## Scoring

Score each idea from 1 to 5:

| Criterion | Meaning |
|---|---|
| Vision fit | Does it align with the project purpose? |
| User value | Does it solve a real problem? |
| Leverage | Does it unlock future work? |
| Testability | Can we prove it works? |
| Effort | How much work is it? Higher means more effort. |
| Risk | How much could it break or complicate? Higher means more risk. |

Suggested score:

```text
Total = Vision fit + User value + Leverage + Testability - Effort - Risk
```

## Decision Buckets

| Bucket | Meaning |
|---|---|
| Promote | Move to roadmap candidate |
| Needs Grill | Needs deeper questioning |
| Park | Useful later |
| Reject | Not aligned or not worth it |

## Completion Checklist

- [ ] Each New idea has a recommended bucket
- [ ] Promoted ideas have a reason
- [ ] Parked ideas have a reason
- [ ] Unclear ideas are marked Needs Grill
- [ ] No source code changed
````

---

## `skills/01-domain-model.md`

````md
# Skill: domain-model

## Purpose

Build shared language before implementation.

Use when:
- A feature has unclear terminology
- Agents may misunderstand the domain
- The same concept appears under different names
- The project needs a stronger mental model

## Inputs

- `PROJECT_CONTEXT.md`
- `docs/architecture/CONTEXT.md`
- `docs/architecture/MODULE_MAP.md`
- Feature `GRILL_NOTES.md`, if present

## Outputs

- Updated `docs/architecture/CONTEXT.md`
- Optional notes in feature `GRILL_NOTES.md`

## Rules

- Do not write source code.
- Do not create issues.
- Do not invent terminology if the user has not confirmed it.
- Mark uncertain terms as open questions.

## Process

1. Identify key nouns and verbs.
2. Identify overloaded terms.
3. Identify domain rules.
4. Ask clarifying questions if meaning changes architecture.
5. Update shared language only when stable.
````

---

## `skills/02-grill-with-docs.md`

````md
# Skill: grill-with-docs

## Purpose

Drill down into a feature until the vision, behavior, integration, and tests are clear.

Use when:
- A feature is selected from the roadmap
- The idea is promising but under-specified
- The user wants to be fully aligned before code
- The agent needs to challenge assumptions

## Inputs

- `PROJECT_CONTEXT.md`
- `ROADMAP.md`
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/MODULE_MAP.md`
- `docs/architecture/CONTEXT.md`

## Outputs

Feature folder:

```text
docs/features/FEAT-____-name/
├── GRILL_NOTES.md
```

Optionally update:
- `docs/architecture/CONTEXT.md`
- `docs/logs/RISK_LOG.md`

## Rules

- Do not write source code.
- Do not write PRD yet.
- Do not create issues yet.
- Ask focused questions.
- Resolve one branch at a time.
- If the codebase or docs can answer a question, inspect them instead of asking.
- Capture decisions as they crystallize.
- Mark unresolved questions explicitly.
- Stop when the user approves the understanding.

## Grill Notes Template

Create or update `GRILL_NOTES.md`:

```md
# Grill Notes: FEAT-____ <Feature Name>

## Feature Summary

One sentence:

> TODO

## Open Questions

| ID | Question | Answer | Decision impact | Status |
|---|---|---|---|---|
| Q-001 | TODO | TODO | TODO | Open |

## Design Tree

### Branch 1: User/System Behavior

Decision:
Options:
Chosen:
Why:

### Branch 2: State/Data

Decision:
Options:
Chosen:
Why:

### Branch 3: Integration Point

Decision:
Options:
Chosen:
Why:

### Branch 4: Failure Behavior

Decision:
Options:
Chosen:
Why:

### Branch 5: Test Strategy

Decision:
Options:
Chosen:
Why:

## Shared Language

| Term | Meaning | Where used |
|---|---|---|
| TODO | TODO | TODO |

## Resolved Understanding

The feature should work like this:

1. TODO
2. TODO
3. TODO

## Non-Goals

- TODO

## Risks

- TODO

## Human Approval

Approved by:
Date:
Notes:
```

## Completion Checklist

- [ ] Behavior is clear
- [ ] Non-goals are clear
- [ ] Integration point is clear
- [ ] Failure behavior is clear
- [ ] Test strategy is plausible
- [ ] Shared terms are captured
- [ ] User approves the understanding
````

---

## `skills/03-to-prd.md`

````md
# Skill: to-prd

## Purpose

Convert resolved feature understanding into a Product Requirements Document.

Use when:
- `GRILL_NOTES.md` is approved
- The feature is ready to be specified
- The user wants requirements frozen before issue slicing

## Inputs

- Feature `GRILL_NOTES.md`
- `PROJECT_CONTEXT.md`
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/MODULE_MAP.md`
- `docs/architecture/CONTEXT.md`

## Output

Feature `PRD.md`

## Rules

- Do not interview the user again unless there is an unresolved blocker.
- Do not invent unresolved requirements.
- Do not write source code.
- Do not create implementation issues yet.
- Mark unresolved questions explicitly.
- Requirements must be testable where possible.

## PRD Template

```md
# PRD: FEAT-____ <Feature Name>

## Status

Draft / Approved / Replaced

## Source

- Idea:
- Grill notes:

## Problem

TODO

## Goal

TODO

## Non-Goals

- TODO

## User/System Stories

- As a <user/system>, I can <behavior>, so that <benefit>.

## Functional Requirements

| ID | Requirement | Priority | Testable? |
|---|---|---|---|
| REQ-001 | TODO | Must / Should / Could | Yes / No |

## Behavior Examples

### Example 1

Given:
When:
Then:

### Example 2

Given:
When:
Then:

## Failure Behavior

| Case | Expected behavior |
|---|---|
| TODO | TODO |

## Integration Points

| Area | Existing module | Required change |
|---|---|---|
| TODO | TODO | TODO |

## Test Strategy

| Behavior | Test type | Test location |
|---|---|---|
| TODO | Unit / Integration / E2E | TODO |

## Acceptance Criteria

- [ ] TODO
- [ ] TODO
- [ ] TODO

## Open Questions

| Question | Impact | Required before implementation? |
|---|---|---|
| TODO | TODO | Yes / No |

## Approval

Approved by:
Date:
```

## Completion Checklist

- [ ] Problem is clear
- [ ] Goal is clear
- [ ] Non-goals are clear
- [ ] User/system stories exist
- [ ] Requirements are testable
- [ ] Failure behavior is specified
- [ ] Integration points are known
- [ ] Acceptance criteria exist
````

---

## `skills/04-to-issues.md`

````md
# Skill: to-issues

## Purpose

Convert an approved PRD into vertical-slice implementation issues.

Use when:
- `PRD.md` is approved
- The feature is ready to be broken into implementation work

## Inputs

- Feature `PRD.md`
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/MODULE_MAP.md`
- `DEV_TRACKER.md`

## Outputs

- Feature `ISSUE_PLAN.md`
- Issue files under `issues/`
- Updated `DEV_TRACKER.md` Slice Board

## Rules

- Do not write source code.
- Each issue must produce observable behavior.
- Each issue must be independently testable.
- Each issue must list allowed files/modules.
- Each issue must list forbidden files/modules.
- Each issue must include a test plan.
- Avoid horizontal tasks like “create interface” unless tied to behavior.
- Identify blockers between slices.
- Keep slices small.

## Vertical Slice Definition

A vertical slice is a thin complete behavior that cuts through the required layers.

Good:
- User can create one item, save it, reload, and see it again.

Bad:
- Create database schema.
- Create service class.
- Create interface.

## ISSUE_PLAN.md Template

```md
# Issue Plan: FEAT-____ <Feature Name>

## Linked PRD

TODO

## Slice Overview

| Slice | Behavior | Depends on | Risk | Test command |
|---|---|---|---|---|
| S001 | TODO | None | Low / Med / High | TODO |

## Implementation Order

1. S001 - TODO
2. S002 - TODO

## Blockers

| Slice | Blocker | Resolution needed |
|---|---|---|
| TODO | TODO | TODO |
```

## Issue File Template

Use `issues/ISSUE_TEMPLATE.md`.

## Completion Checklist

- [ ] ISSUE_PLAN.md created
- [ ] Each slice has an issue file
- [ ] Each slice has observable behavior
- [ ] Each slice is testable
- [ ] Each slice has scope/non-scope
- [ ] DEV_TRACKER.md updated
- [ ] No source code changed
````

---

## `skills/05-activate-slice.md`

````md
# Skill: activate-slice

## Purpose

Select exactly one slice for implementation.

Use when:
- Issue plan exists
- Human chooses the next slice
- DEV_TRACKER.md needs to be updated

## Inputs

- `DEV_TRACKER.md`
- Feature `ISSUE_PLAN.md`
- Slice issue file

## Output

Updated `DEV_TRACKER.md`

## Rules

- Do not write source code.
- Do not activate more than one slice.
- Confirm allowed files/modules.
- Confirm forbidden files/modules.
- Confirm test command.
- Confirm file change budget.
- If the slice is not ready, mark it Blocked instead of Active.

## Completion Checklist

- [ ] Exactly one Active Slice
- [ ] Issue file linked
- [ ] Allowed files listed
- [ ] Forbidden files listed
- [ ] Test command listed
- [ ] Status updated
````

---

## `skills/06-tdd.md`

````md
# Skill: tdd

## Purpose

Implement one Active Slice using test-driven development.

Use when:
- DEV_TRACKER.md has exactly one Active Slice
- The slice issue is ready
- The test strategy is clear

## Inputs

- `DEV_TRACKER.md`
- Active slice issue file
- Feature `PRD.md`
- Feature `TEST_PLAN.md`, if present
- `docs/architecture/MODULE_MAP.md`

## Outputs

- Tests
- Minimal code changes
- Updated `docs/logs/TEST_LOG.md`
- Updated `docs/logs/CHANGE_LOG.md`
- Updated `DEV_TRACKER.md`

## Rules

- Implement only the Active Slice.
- Stay within allowed files/modules.
- Do not touch forbidden files/modules.
- Write or update tests first.
- Run the test and record result.
- Implement minimum code.
- Run test again.
- Refactor only within scope.
- Do not add dependencies without approval.
- Do not change architecture boundaries without approval.
- Stop if scope expands.

## Required Loop

1. Restate the behavior.
2. Identify the smallest test proving the behavior.
3. Write or update the test first.
4. Run the test.
5. Show the failure if practical.
6. Implement minimum code.
7. Run the test again.
8. Refactor only inside slice scope.
9. Run final test command.
10. Update logs.

## Stop Conditions

Stop and create a Blocked Decision if:
- More files are needed than the file budget.
- A new dependency is needed.
- The architecture boundary is unclear.
- The test strategy is unclear.
- Existing behavior breaks unexpectedly.
- The change no longer matches the issue.

## Completion Report

End with:

```text
Summary:
Files changed:
Tests added/changed:
Commands run:
Result:
Docs updated:
Risks:
Next suggested slice:
```
````

---

## `skills/07-review.md`

````md
# Skill: review

## Purpose

Review the Active Slice before it is closed.

Use when:
- Implementation is complete
- Tests have been run
- The slice is ready for closure review

## Inputs

- `DEV_TRACKER.md`
- Active slice issue file
- Feature `PRD.md`
- `docs/logs/TEST_LOG.md`
- `docs/logs/CHANGE_LOG.md`
- Git diff or file changes

## Output

Feature `REVIEW.md` or review section appended to existing file

## Rules

- Do not implement new behavior.
- Do not refactor.
- Do not expand scope.
- Check only whether the slice is clean, tested, and aligned.

## Review Checklist

```md
# Slice Review

## Scope

- [ ] Only allowed files changed
- [ ] No forbidden files changed
- [ ] No unrelated cleanup
- [ ] No hidden architecture change
- [ ] No new dependency unless approved

## Behavior

- [ ] Acceptance criteria satisfied
- [ ] Observable behavior exists
- [ ] Failure behavior considered
- [ ] Edge cases considered where relevant

## Tests

- [ ] Test added or updated
- [ ] Test command run
- [ ] Test result recorded
- [ ] Known gaps documented

## Docs

- [ ] TEST_LOG.md updated
- [ ] CHANGE_LOG.md updated
- [ ] HANDOFF.md updated
- [ ] Architecture docs updated if needed

## Decision

Approve / Needs changes / Blocked

Reason:

TODO
```
````

---

## `skills/08-handoff.md`

````md
# Skill: handoff

## Purpose

Make the next session or next agent able to resume without chat history.

Use when:
- A slice is completed
- A session is ending
- A feature is partially complete
- A new agent/developer needs context

## Inputs

- `DEV_TRACKER.md`
- Feature `PRD.md`
- Feature `ISSUE_PLAN.md`
- Issue files
- `docs/logs/TEST_LOG.md`
- `docs/logs/CHANGE_LOG.md`
- `docs/architecture/MODULE_MAP.md`

## Output

Feature `HANDOFF.md`

## Rules

- Do not write source code.
- Do not invent completion status.
- Summarize only what artifacts and tests support.
- Make resume instructions concrete.

## HANDOFF.md Template

```md
# Handoff: FEAT-____ <Feature Name>

## Current State

What is done:

- TODO

What is not done:

- TODO

## Completed Slices

| Slice | Behavior | Test evidence |
|---|---|---|
| S001 | TODO | TODO |

## Active or Next Slice

Recommended next slice:

> TODO

Why:

> TODO

## Important Decisions

| Decision | Where recorded |
|---|---|
| TODO | TODO |

## Relevant Files

| File | Why it matters |
|---|---|
| TODO | TODO |

## Known Risks

- TODO

## How to Resume

1. Read `PROJECT_CONTEXT.md`.
2. Read `AGENTS.md`.
3. Read `DEV_TRACKER.md`.
4. Read this `HANDOFF.md`.
5. Read the next slice issue.
6. Run baseline tests.
7. Continue with TDD.
```
````

---

## `skills/09-improve-architecture.md`

````md
# Skill: improve-architecture

## Purpose

Find architecture improvements that make the codebase easier to test, change, and navigate with agents.

Use when:
- 3 to 5 slices are complete
- A feature is complete
- Tests are becoming painful
- Module ownership is confusing
- One concept is scattered across many files
- Agents repeatedly misunderstand the codebase

## Inputs

- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/MODULE_MAP.md`
- `docs/architecture/CONTEXT.md`
- `docs/decisions/`
- Completed issue files
- `docs/logs/TEST_LOG.md`
- Existing source code

## Output

- `docs/architecture/ARCHITECTURE_REVIEW.md`
- Optional ADR draft
- Optional refactor slice issues

## Rules

- Do not refactor immediately.
- Do not mix cleanup with feature work.
- Preserve behavior.
- Propose refactors as separate vertical slices.
- Require tests before refactor.
- Prefer deeper modules with thinner public interfaces.
- Avoid scattering one concept across many shallow files.

## Process

1. Identify confusing module boundaries.
2. Identify shallow modules.
3. Identify scattered concepts.
4. Identify painful tests.
5. Identify duplicated concepts.
6. Recommend small refactor slices.
7. Record risks.
8. Ask for approval before implementation.

## Completion Checklist

- [ ] Architecture review written
- [ ] Proposed refactors are separate slices
- [ ] Behavior preservation strategy exists
- [ ] Test protection identified
- [ ] No source code changed unless explicitly requested
````

---

# Script Stubs

Create `scripts/README.md`:

````md
# Scripts

These scripts are placeholders for workflow automation.

They may be implemented later.

## Intended Scripts

| Script | Purpose | Should not do |
|---|---|---|
| `test.sh` | Run project tests | Modify files |
| `lint.sh` | Run lint/static checks | Modify files unless explicitly configured |
| `check.sh` | Run all validation | Modify files |
| `new-idea.sh` | Append idea to IDEA_INBOX.md | Promote idea |
| `new-feature.sh` | Create feature folder/templates | Write source code |
| `activate-slice.sh` | Update DEV_TRACKER.md | Write source code |
| `close-slice.sh` | Validate logs/checklists | Mark done if tests missing |
````

Create `scripts/test.sh`:

````bash
#!/usr/bin/env bash
set -euo pipefail

echo "TODO: replace with project test command"
````

Create `scripts/lint.sh`:

````bash
#!/usr/bin/env bash
set -euo pipefail

echo "TODO: replace with project lint command"
````

Create `scripts/check.sh`:

````bash
#!/usr/bin/env bash
set -euo pipefail

./scripts/lint.sh
./scripts/test.sh
````

Make these scripts executable if the environment supports it:

```bash
chmod +x scripts/test.sh scripts/lint.sh scripts/check.sh
```

---

# Automation Policy

Create `AUTOMATION_POLICY.md`:

````md
# Automation Policy

## Purpose

This file defines what can be automated safely and what requires human approval.

## Safe to Automate

- Idea capture formatting
- Idea deduplication suggestions
- Triage scoring drafts
- Feature folder creation
- PRD draft generation
- Issue/slice draft generation
- Test command execution
- Test log updates
- Changelog draft updates
- Handoff draft generation
- Architecture review proposals

## Not Safe to Fully Automate

- Final product priority
- Vision approval
- PRD approval
- Slice boundary approval
- Architecture boundary changes
- Adding dependencies
- Scope expansion
- Marking a feature done
- Deleting ideas permanently
- Large refactors

## Semi-Automated With Approval

- Promote idea to roadmap
- Activate slice
- Create branch
- Open pull request
- Update architecture docs
- Create ADR
- Close slice
- Close feature
````

---

# Optional: Feature Folder Template

When a feature is selected, create:

```text
docs/features/FEAT-____-feature-name/
├── GRILL_NOTES.md
├── PRD.md
├── ISSUE_PLAN.md
├── TEST_PLAN.md
├── REVIEW.md
└── HANDOFF.md
```

Use the templates above.

---

# Final Response Requirement

After creating or updating files, report:

```text
Summary:
Files created:
Files updated:
Files preserved:
Scripts created:
Any conflicts:
Recommended next step:
```

Do not start implementing product features.

The recommended next step should be:

1. Fill in `PROJECT_CONTEXT.md`.
2. Capture current ideas in `IDEA_INBOX.md`.
3. Triage ideas into `ROADMAP.md`.
4. Select one feature for grill-with-docs.

---

# Daily Use Prompt

After the system is created, use this prompt with agents:

```md
Follow the repository workflow.

Read:
1. `AGENTS.md`
2. `PROJECT_CONTEXT.md`
3. `DEV_TRACKER.md`
4. The active slice issue

Rules:
- Do not code unless there is exactly one Active Slice.
- Stay within allowed files/modules.
- Write or update tests first.
- Implement the smallest change.
- Run the listed test command.
- Update `TEST_LOG.md`, `CHANGE_LOG.md`, and `HANDOFF.md`.
- Put new ideas in `IDEA_INBOX.md`.
- Put cleanup ideas in Parking Lot.
- Stop if scope expands, dependency is needed, or architecture is unclear.

End with:

Summary:
Files changed:
Tests added/changed:
Commands run:
Result:
Docs updated:
Risks:
Next suggested slice:
```

---

# Glossary

| Term | Meaning | Source |
|---|---|---|
| Triage | Sorting many ideas/issues by priority and deciding what deserves attention first. | https://www.aihero.dev/skills |
| Grill-with-docs | Interviewing/drilling down while updating durable project context/docs. | https://www.aihero.dev/skills |
| PRD | Product Requirements Document; freezes what will be built and how success is judged. | https://www.aihero.dev/5-agent-skills-i-use-every-day |
| Vertical slice | A small independently testable behavior, not just one technical layer. | https://www.aihero.dev/5-agent-skills-i-use-every-day |
| TDD | Test-driven development: write test, make it pass, refactor. | https://www.aihero.dev/skills |
| Handoff | Compact artifact that lets a later session or agent resume without relying on chat history. | https://www.aihero.dev/skills |
| `AGENTS.md` | Repository-level instruction file for coding agents. | https://developers.openai.com/codex/guides/agents-md |
| ADR | Architecture Decision Record; a short document explaining a design decision, alternatives, and consequences. | https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions |

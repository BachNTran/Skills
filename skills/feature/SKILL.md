---
name: feature
description: Full feature planning pipeline. Runs end-to-end from domain context through grill, PRD, test plan, architecture fit, and issue slicing. Produces all planning artifacts needed before implementation. Use when a feature is promoted on the roadmap and ready to be planned.
---

You are running the full feature planning pipeline. Your job is to deeply understand the feature with the developer, freeze requirements, define tests, fit architecture, and slice into executable issues — all before any code is written.

You produce durable artifacts that enable autonomous sub-agent execution. Quality here determines quality of everything downstream.

## On Start

1. Read `CLAUDE.md`, `PROJECT_CONTEXT.md`, `docs/architecture/ARCHITECTURE.md`, `docs/architecture/MODULE_MAP.md`, `docs/architecture/CONTEXT.md`
2. Read `ROADMAP.md` — confirm feature is in Now column
3. Ask developer which feature to plan if ambiguous
4. Create feature folder: `docs/features/FEAT-[NNNN]-[slug]/`
5. Create empty `BRIEF.md` with YAML frontmatter and section headers

---

## PHASE 2.5 — DOMAIN CONTEXT (conditional: hardware/specialized domain only)

Skip this phase entirely if the feature is pure software with no hardware interaction and no specialized domain knowledge required.

**Trigger conditions — run this phase if:**
- Feature touches hardware, peripherals, or custom silicon
- Feature involves proprietary protocols or specialized interfaces
- Codebase contains register definitions, hardware addresses, or errata references
- Feature area has patterns Claude cannot explain from general knowledge

**If triggered:**

First, check `docs/knowledge-base/` — if documentation for this hardware/domain already exists, load it and skip to gap-filling only.

If new hardware/domain:

1. Ask developer to place reference documents in `docs/hardware/` (datasheets, errata, reference manuals)
2. Read and distill provided documents into structured knowledge
3. Grill developer on what documents don't cover — one question at a time:
   - "Are there known errata for this hardware that affect this feature area?"
   - "Are there timing or sequencing constraints that exist nowhere in any document?"
   - "Has anyone attempted this before? What failed and why?"
   - "Are there register access patterns that are non-obvious?"
   - "What does correct operation look like at the observable/signal level?"
   - "How do I access this hardware for testing? (JTAG CLI? SSH? Serial? Custom tool?)"
4. Confirm sufficiency: "Based on what you've told me, I now understand [summary]. Is there anything I should know but haven't asked?"

Create `docs/knowledge-base/[component-name]/DOMAIN_CONTEXT.md` and `HARDWARE_ACCESS.md`.

---

## PHASE 3 — FEATURE GRILL

Produce `BRIEF.md` by walking 9 branches, one at a time. Write each section of BRIEF.md as the branch resolves — do not wait until the end.

**Before asking any question:** scan the codebase and existing docs to answer what you can. Only ask the developer about things you cannot determine from code or documents.

### Branch -1: Operation Classification
Declare and confirm: New Feature / Modify Feature / Remove Feature.
Adjust all subsequent branch questions based on operation type.
For Remove: scan codebase for all references before asking anything.

### Branch 0: Non-Goals
"What are we explicitly NOT building in this feature?"
Read ROADMAP.md and docs/ideas/ to suggest likely scope temptations.
Require at least one explicit exclusion.

### Branch 1: User/System Behavior
"Walk me through what happens step by step, from the user's or system's perspective, when this feature works perfectly."
Follow up until: no ambiguous pronouns, no "etc", no "and so on".
Capture alternate paths if they exist.

### Branch 2: State/Data
"What data gets created, changed, or deleted by this feature?"
Scan existing data structures/models first. Present findings.
Lock: persistence, ownership, migration decision (explicit even if "not required").

### Branch 3: Integration Points
Scan MODULE_MAP.md and codebase. Propose candidate list.
"Does my list match your intent? Anything missing?"
For each integration: read/write, interface exists/needs creation, owner.
Flag unbuilt dependencies as explicit blockers.

### Branch 4: Failure Behavior
Generate failure candidates from Branches 1-3 automatically.
For each: "What should the system do?" 
Name edge cases — do not fully specify them here (that's TEST_PLAN.md).
Every integration point must have at least one failure case.

### Branch 5: Architecture Fit (signal only)
Propose placement based on ARCHITECTURE.md scan.
"Does my proposed placement match your intent?"
Flag potential ADR needs — do not write ADR yet.
Note: if feature fits cleanly in existing module with no boundary change, confirm and move on quickly.

### Branch 6: Test Strategy (architecture only)
Propose test types per behavior (unit/integration/e2e) with justification.
Decide mock/real per integration point.
Identify regression risk: existing behavior at risk + covered by existing test?
Define one verification command.
Do NOT define slice-level test commands here.

### Branch 7: Success Criteria
Propose a binary checklist from Branches 1-4.
Every criterion must be: pass/fail, no judgment required.
Confirm: "If every item here passes, are you comfortable shipping this feature?"

### BRIEF.md Self-Check Before Approval
Before asking developer to approve:
- All 9 branches have content (even if "N/A — not applicable")
- No branch has an unresolved open question unless explicitly deferred with reason
- Behavior is unambiguous enough that someone not in this conversation could understand it
- No new information introduced that wasn't discussed

Ask: "Does BRIEF.md match your understanding of this feature?"
Update BRIEF.md status to `approved` on confirmation.

---

## PHASE 4 — PRD

Convert approved BRIEF.md to `PRD.md`. Do NOT re-interview — everything comes from BRIEF.md.
Only ask developer if a genuine blocker exists that BRIEF didn't resolve.

PRD.md structure:
```markdown
---
feature: FEAT-[NNNN]
status: draft
created: [YYYY-MM-DD]
brief: [BRIEF.md](BRIEF.md)
---

# PRD: FEAT-[NNNN] [Feature Name]

## Problem
## Goal
## Non-Goals
## User/System Stories
## Functional Requirements
| ID | Requirement | Priority | Testable? |
## Behavior Examples (Given/When/Then — high level)
## Failure Behavior
## Integration Points
## Architecture Signal
## Acceptance Criteria
## Open Questions (non-blocking only)
## Approval
```

Self-check before approval request:
- Every Branch 0-7 decision is reflected
- No new information introduced
- All requirements are testable
- No open questions that block implementation

Update PRD.md status to `approved` on developer confirmation.

---

## PHASE 4.5 — TEST PLAN GRILL

This is a dedicated grill session — not automatic generation.

You are simultaneously two characters:

**The Stringent QA Engineer** — assumes the feature is broken until proven otherwise. Has been burned by production incidents from untested edge cases. Is personally responsible if this feature fails.

**The Adversarial User** — does not read docs, does not use the feature as intended, tries everything that wasn't designed for, finds gaps between "what was built" and "what was assumed."

Generate a comprehensive draft test plan from PRD.md, then present it to the developer for review and additions.

For each test case, think through:
- INPUTS: valid, invalid, boundary, empty, enormous, malformed, adversarial
- STATES: fresh, populated, corrupted, partial, missing
- SEQUENCES: out of order, repeated, interrupted, skipped steps
- ENVIRONMENTS: slow, unavailable, degraded, resource-constrained
- ACTORS: intended user, confused user, impatient user, concurrent user, adversarial actor
- FAILURES: each dependency unavailable, each write failing, each read returning garbage
- CONCURRENCY: simultaneous identical operations, conflicting operations, race conditions
- RECOVERY: retry behavior, partial state cleanup, rollback correctness
- OBSERVABILITY: can a test assert this result without human eyes?
- TIME: too early, too late, expired, wrong clock, unexpected ordering

For hardware/embedded projects, also cover:
- Endianness and byte order
- Cache coherency and DMA interaction
- Interrupt timing and ISR reentrancy
- Register access patterns and hazards
- Memory alignment and word size
- Power state transitions
- Real-time deadline behavior
- Hardware sanity tests (verify DOMAIN_CONTEXT.md claims on real hardware before implementation)

Parameterize when 3+ test cases share structure but differ only in inputs.

Before asking for approval:
- Every REQ-### has at least one test case
- Every failure mode has a test case
- Every named edge case from Branch 4 is fully specified
- No test case requires human judgment to evaluate pass/fail
- Verification commands are exact and runnable

Update TEST_PLAN.md status to `approved` on developer confirmation.

---

## PHASE 5 — ARCHITECTURE FIT

Convert Branch 5 signal into locked decisions.

1. Run reuse audit first:
   - Existing helpers that cover this behavior?
   - Existing modules that can be extended?
   - Existing test doubles for these dependencies?
   - Check `docs/knowledge-base/` for reusable domain context
   Report findings before any placement decision.

2. Propose exact placement:
   - Which files get extended (exact paths)
   - Which new files/modules are needed (exact paths)
   - Public interface definition
   - Dependency direction — does it comply with ARCHITECTURE.md dependency rule?

3. Module independence check:
   "Can this module's tests run without the rest of the project?"
   Produce dependency declaration:
   | Depends on | Type | Removable? |
   Flag if dependency list is growing — propose injection/adapter.

4. Write ADR if flagged in Branch 5:
   - Create `docs/features/FEAT-[NNNN]/decisions/ADR-001-[slug].md` (feature-scoped)
   - Or `docs/decisions/ADR-[NNN]-[slug].md` if it affects all future features
   - Rule: if another dev on a different feature must know this → project-scoped

5. Update `docs/architecture/ARCHITECTURE.md` and `docs/architecture/MODULE_MAP.md`

6. If Branch 5 signal was "fits cleanly, no boundary change" → confirm and skip to Phase 6.

Developer approves placement and any ADRs before proceeding.

---

## PHASE 6 — ISSUE SLICING

Convert PRD.md + TEST_PLAN.md into vertical slice files.

**Vertical slice rule:** one slice = one independently observable behavior that can be tested and reviewed in isolation. Never a technical layer (create X). Always a behavior (X works).

**Reuse audit per slice:**
- Does equivalent behavior already exist?
- Does a test double already exist for this dependency?
- If new double needed → create as its own slice first (always first in dependency order)

**Slice file structure** (`docs/features/FEAT-[NNNN]/slices/S[NNN].md`):
```markdown
---
slice: S[NNN]
feature: FEAT-[NNNN]
status: backlog
depends-on: [S000 or none]
---

# S[NNN] — [Behavior Name]

## Behavior
After this slice, the system can: [one sentence]

## Scope (allowed)
- [exact paths]

## Non-Scope (do not touch)
- [exact paths]

## Acceptance Criteria
- [ ] [binary criterion]

## Test Command
[exact command]

## File Budget
Expected: [n] files
Maximum: [n × 1.5 rounded up]

## Test Double Required
[yes — new double spec needed / no — reuse existing at path]

## Blockers
[dependency or unresolved decision]

## Linked
- [PRD](../PRD.md)
- [TEST_PLAN](../TEST_PLAN.md)
- [Issue Plan](../ISSUE_PLAN.md)
```

**ISSUE_PLAN.md** — dependency graph + wave grouping:
```markdown
---
feature: FEAT-[NNNN]
status: draft
---

# ISSUE PLAN: FEAT-[NNNN]

## Slice Overview
| Slice | Behavior | Depends on | Risk | Status |

## Wave Groups
| Wave | Slices | Can parallelize |

## Implementation Order
1. S001 — reason
2. S002 — reason

## Blockers
| Slice | Blocker | Resolution needed |
```

Developer approves ISSUE_PLAN.md before implementation begins.

---

## Completion

When ISSUE_PLAN.md is approved, report:
```
Feature FEAT-[NNNN] fully planned.
Artifacts created:
  docs/features/FEAT-[NNNN]/BRIEF.md       ✓
  docs/features/FEAT-[NNNN]/PRD.md         ✓
  docs/features/FEAT-[NNNN]/TEST_PLAN.md   ✓
  docs/features/FEAT-[NNNN]/ISSUE_PLAN.md  ✓
  docs/features/FEAT-[NNNN]/slices/        ✓ ([N] slices in [M] waves)
  [ADRs if any]
  [Architecture updates if any]
  [Knowledge base additions if any]

Ready to implement. Run /implement to begin execution.
```

# AGENTS.md

## Mission

Develop cleanly, incrementally, and testably.

Do not optimize for fast code generation.
Optimize for controlled progress, clear behavior, small diffs, durable tests, and understandable architecture.

## Workflow Spine

```
IDEA CAPTURE
→ TRIAGE
→ DOMAIN MODEL / DOMAIN CONTEXT (hardware only)
→ FEATURE GRILL
→ PRD
→ TEST PLAN GRILL
→ ARCHITECTURE FIT
→ ISSUE SLICING
→ WAVE ACTIVATION
→ TDD EXECUTION (autonomous)
→ AUTOMATED REVIEW
→ HANDOFF
→ REPEAT
→ FEATURE CLOSE
→ ARCHITECTURE CLEANUP
```

## Hard Rules

1. No code without an approved ISSUE_PLAN.md
2. No ISSUE_PLAN without approved PRD and TEST_PLAN
3. No PRD without approved BRIEF
4. New ideas go to docs/ideas/ — do not interrupt active work
5. Only one feature active at a time per developer
6. Tests written before implementation (TDD — red/green/refactor)
7. Tests live co-located with code (per project convention)
8. Test doubles never inline in test files — always shared files
9. No new dependency without developer approval
10. No architecture boundary change without ADR
11. No completion claim without test evidence
12. Stop if scope expands beyond slice budget
13. Stop if new dependency is needed
14. Stop if architecture boundary is unclear
15. Cleanup is never mixed with feature work
16. CODING_STANDARDS linter must pass before slice closes

## Architecture Rules

- Prefer deep modules with thin public interfaces
- Keep external systems behind adapters or boundaries
- Keep domain/business logic separate from infrastructure
- Tests close to behavior — co-located with code
- If tests are hard to write, inspect architecture before forcing mocks
- Reuse existing helpers, doubles, and utilities before creating new ones
- New module requires: single stated responsibility + minimal public interface

## Test Double Rules

- One authoritative double per external dependency
- Double specification document required alongside double file
- Double simulates real system behavior as closely as possible
- Document known gaps (what double cannot simulate)
- Known gaps → require integration tests against real system
- Never create ad-hoc mocks inline in test files

## Completion Report (every slice)

```
Slice:
Status:
Behavior:
Tests added:
Files changed:
Files count: [n] of [budget]
Regression: PASS/FAIL
Reuse found: yes/no
New doubles: yes/no
Risks:
Next slice unblocked:
```

## Human Approval Required

- Promoting idea to roadmap
- Approving BRIEF.md
- Approving PRD.md
- Approving TEST_PLAN.md
- Approving ISSUE_PLAN.md
- D-type blockers during execution
- Architecture boundary changes
- New dependencies
- Feature close sign-off

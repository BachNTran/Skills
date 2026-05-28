---
name: cleanup
description: Periodic architecture cleanup. Reviews codebase for confusion, scattered concepts, painful tests, and growing module dependencies. Proposes refactor slices — never mixes cleanup with feature work. Run after every 3-5 completed slices or after a feature closes.
---

You are running architecture cleanup. Your job is to identify structural problems and propose refactor slices — not to fix them immediately. Cleanup is always separate from feature work.

## Rules

- Do NOT refactor during feature work
- Do NOT mix cleanup with active slice implementation
- Do NOT modify source code during this phase
- Propose refactor slices → they enter the idea backlog like any other idea
- Preserve all existing behavior
- Require test protection before any refactor

## On Start

Read:
1. `docs/architecture/ARCHITECTURE.md`
2. `docs/architecture/MODULE_MAP.md`
3. `docs/architecture/CONTEXT.md`
4. `CODING_STANDARDS.md`
5. Recently completed feature folders and REVIEW.md files
6. Source code — scan for structural signals

## Trigger Signals (check each)

```
□ Tests becoming painful to write
□ Module ownership confusing — unclear where a change goes
□ Same concept scattered across multiple files/modules
□ One module's dependency declaration growing (5+ external deps)
□ Sub-agents repeatedly misunderstood structure in recent features
□ Test doubles duplicated for same dependency
□ Inline mocks found in test files
□ CODING_STANDARDS violations accumulated during rapid development
□ New module created without clear single responsibility
□ Public interface larger than necessary
```

## Analysis Process

### 1. Module Boundary Review

For each module in MODULE_MAP.md:
- Does it have a single stated responsibility?
- Is its public interface minimal?
- Is its dependency declaration reasonable?
- Are its tests self-contained (runnable without other modules)?

Flag: modules that fail two or more of these.

### 2. Concept Scatter Detection

Scan for the same concept appearing in multiple modules.
Ask: is this intentional layering, or accidental scatter?
Scatter = same business/domain logic duplicated or split without clear ownership.

### 3. Test Health Check

- Are test files co-located with code (per project convention)?
- Are test doubles shared (not duplicated per test file)?
- Are integration tests at the right boundary level?
- Are there tests that require loading unrelated modules?

### 4. Dependency Direction Check

Does any module violate the dependency rule in ARCHITECTURE.md?
Does any domain/core module depend on infrastructure details?

### 5. Standards Drift Check

Run linter/static analysis across the codebase.
Flag: files or modules that consistently violate CODING_STANDARDS.md.

## Output: ARCHITECTURE_REVIEW.md

Write `docs/architecture/ARCHITECTURE_REVIEW.md`:

```markdown
---
triggered: [YYYY-MM-DD]
trigger-reason: [what caused this review]
---

# Architecture Review — [YYYY-MM-DD]

## Confusion Points
| Area | Problem | Impact |

## Scattered Concepts
| Concept | Found in | Should own |

## Dependency Health
| Module | External deps | Removable? |

## Test Health Issues
| Issue | Location | Fix |

## Proposed Refactor Slices
| Slice | Problem solved | Behavior preserved | Test protection | Priority |

## Decision
Proceed / Park / Reject
Reason:
```

## Proposed Refactor Slices

For each identified problem, propose a refactor slice:
- Small — one problem, one fix
- Behavior-preserving — existing tests must still pass after
- Test-protected — must have tests that prove behavior unchanged before refactoring
- Independent — does not depend on in-progress feature work

Submit proposed slices to idea backlog (`docs/ideas/`) — not directly to ROADMAP.md.
Developer triages like any other idea.

## Report

```
Architecture review complete.
Confusion points found:  [N]
Scattered concepts:      [N]
Test health issues:      [N]
Standards drift:         [N] files

Proposed refactor slices: [N]
  → Added to docs/ideas/ for triage

High priority:
  [top 1-2 items with one-line summary]

Run /triage to schedule cleanup work.
```

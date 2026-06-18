---
feature: FEAT-[NNNN]
status: draft
created: [YYYY-MM-DD]
brief: [BRIEF.md](BRIEF.md)
decisions: [DECISIONS.md](DECISIONS.md)
---

# PRD: FEAT-[NNNN] [Feature Name]

## Problem
## Goal
## Non-Goals

## Functional Requirements

Each requirement uses **EARS** phrasing and carries its own rationale + decision link, so the
"why" travels with the requirement (ADR-0001 §3). The trace index is generated from these
`REQ-###` blocks.

> **EARS patterns** — pick one per requirement:
> - Ubiquitous: "The `<system>` shall `<response>`."
> - Event: "When `<trigger>`, the `<system>` shall `<response>`."
> - State: "While `<state>`, the `<system>` shall `<response>`."
> - Unwanted: "If `<condition>`, then the `<system>` shall `<response>`."
> - Optional: "Where `<feature present>`, the `<system>` shall `<response>`."

### REQ-001 — [short name]
- **statement (EARS):** [one EARS sentence]
- **priority:** must | should | could
- **why:** [why this requirement exists at all]
- **why-not-broader:** [what we deliberately do NOT require, and why — the boundary]
- **from:** DEC-###, DEC-###
- **testable:** yes

<!-- repeat REQ-### blocks; one observable obligation each -->

## Behavior Examples (Given/When/Then — high level)
## Failure Behavior
## Integration Points
## Architecture Signal
## Acceptance Criteria
## Open Questions (non-blocking only)
## Approval

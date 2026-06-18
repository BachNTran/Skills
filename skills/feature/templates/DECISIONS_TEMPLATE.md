---
feature: FEAT-[NNNN]
kind: decision-ledger
updated: [YYYY-MM-DD]
---

# Decision Ledger — FEAT-[NNNN]

Informal, durable record of decisions converged on **while grilling**. Each entry has a
stable ID so requirements, tests, and code can link back to it. Append a new entry the
**moment** a decision is reached — do not batch at the end. **Never delete an entry —
supersede it** (set `status: superseded` + `superseded_by`).

Accountability note: an entry records *who* converged on it. Decisions are joint outcomes of
grilling, not agent proposals — the human owns them because the human shaped them.

> The generated `TRACE.md` derives linkage from these entries — do not hand-edit TRACE.md.
> This file is the source of truth for decision rationale.

---

## DEC-001 — [one-line title]
- **date:** [YYYY-MM-DD]
- **with:** [developer]            <!-- who converged on it; accountability rests here -->
- **status:** active               <!-- active | superseded -->
- **serves:** REQ-###, REQ-###     <!-- requirements this decision drives; may be empty early -->
- **superseded_by:** —             <!-- DEC-### if later revised, else — -->

Decided: [what we chose, in plain language].
Why: [the reason it won].
Rejected: [alternatives considered and why they lost].

---

<!-- Append further decisions below in the same shape. -->

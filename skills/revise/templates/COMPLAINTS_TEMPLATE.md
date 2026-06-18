---
feature: FEAT-[NNNN]
kind: complaint-log
updated: [YYYY-MM-DD]
---

# Complaints & Revisions — FEAT-[NNNN]

Each entry records dissatisfaction the developer raised, **why** the thing was built that way
(traced through the decision ledger), and what changed. Complaints are a first-class learning
signal — a resolved one feeds `PREFERENCES.md` so the project stops repeating the pattern.
Never delete an entry.

---

## CMP-001 — [one-line summary]
- **date:** [YYYY-MM-DD]
- **raised by:** [developer]
- **about:** [REQ-### / DEC-### / file:line]
- **status:** open            <!-- open | revised | wontfix -->

Complaint: [what the developer disliked, in their words].
Why it was built that way: [traced — cite DEC-### and REQ-### with their rationale].
Resolution: [new DEC-### that supersedes the old; the REQ-### / TC-### amended].
Propagated: [preference added to PREFERENCES.md? other features/code flagged for the same pattern?].

---

<!-- Append further complaints below in the same shape. -->

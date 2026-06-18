---
name: revise
description: Turn a developer complaint about existing behavior into a traced revision. Records the complaint, traces why it was built that way (walking the decision ledger), re-grills the desired behavior, amends PRD/TEST_PLAN/decisions, and offers to propagate the new pattern project-wide. Use when the developer dislikes how something works, says "this is wrong", or wants to change a shipped behavior.
---

You are running the complaint → revision loop. A complaint is a **first-class learning
signal**: it should leave the project smarter, not just patched. Respect the project's
criticality tier (PROJECT_CONTEXT → Criticality & Autonomy) for how much approval you need.

## Trigger

Run when the developer expresses dissatisfaction with existing behavior ("I don't like how X
works", "this is wrong", "why is this so slow"). **Confirm first** — don't fire on an offhand
grumble:

> "Sounds like you're unhappy with [X]. Want me to log it and open a revision?"

Proceed only on yes.

## Step 1 — Record the complaint

Append a `CMP-###` entry to the relevant feature's `COMPLAINTS.md` (create it from
[`templates/COMPLAINTS_TEMPLATE.md`](templates/COMPLAINTS_TEMPLATE.md) if absent). Capture the
complaint in the developer's own words and what it is about (a REQ-###, DEC-###, or file:line).

## Step 2 — Trace why it was built that way

Before proposing any change, walk the trace **bottom-up** so the revision is informed, not
reactive:
1. Open the feature `TRACE.md` (regenerate with `python3 tools/trace_index.py` if stale).
2. From the disliked code/behavior, follow code → TC → REQ → DEC.
3. Summarize for the developer: "This was built this way because of REQ-### (rationale: …),
   which came from DEC-### where we decided … and rejected …."

This is the accountability step — it shows the decision was a past joint convergence, not an
agent whim, and it surfaces whether the original reason still holds.

## Step 3 — Re-grill the desired behavior

Grill the new intent **in a batch** (all questions at once, recommended answers). Converge on
what should change. Record a **new `DEC-###`** that supersedes the old one (set the old
decision's `status: superseded` and `superseded_by:` — never delete it).

## Step 4 — Amend the artifacts

Propagate the converged change down the spine:
- `PRD.md` — update/add/remove the affected `REQ-###` (keep EARS + rationale + `from:` the new DEC).
- `TEST_PLAN.md` — update the `TC-###` so the new behavior is proven and the old failure modes still covered.
- Implementation follows per the criticality tier (EXPLORE: you implement; CRITICAL: you scaffold, the developer reviews every line).
- Regenerate `TRACE.md`.

Set the `CMP-###` status to `revised` and link the new DEC.

## Step 5 — Propagate the pattern (ask first)

A complaint usually reveals a **preference**, not a one-off. Ask:

> "Should this become a project-wide preference, and should I apply it to other features that
> share the old pattern?"

On yes:
- Append the preference to `PREFERENCES.md` (Design taste or Workflow corrections), and to the
  **Active preferences** digest if currently-true and high-value.
- Scan for other features/code using the old pattern; list them and propose follow-up changes
  (as ideas or a new revision) — do not silently mass-edit.

## Completion

Report: the `CMP-###`, the superseding `DEC-###`, the amended REQ/TC IDs, whether a preference
was added, and any other features flagged for the same pattern.

---
name: triage
description: Triage the idea backlog. Reads pre-scored ideas from docs/ideas/, surfaces uncertain or borderline entries for developer decision, and updates ROADMAP.md. Use when your backlog has grown and you want to decide what deserves attention next.
---

You are triaging the idea backlog. Your job is to surface decisions — not make them. Claude scored ideas at capture time. Your role here is to present those scores, flag the uncertain ones, and get the developer to confirm buckets.

## Rules

- Do NOT re-read or re-score ideas that are already scored with high confidence
- Do NOT implement anything
- Do NOT create feature folders or branches
- Only surface ideas that need a human decision
- Keep the session fast — one decision per idea, move on

## Step 1 — Load Backlog

Read all files in `docs/ideas/` with `status: new` or `status: needs-review`.

Group by bucket from their saved score:
- Promote candidates (score 8–10)
- Uncertain (score 5–7 or confidence flagged)
- Park/Later/Reject (score 1–4, low effort decisions)

## Step 2 — Present in Order

Present Promote candidates first (highest value decisions), then Uncertain, then low-score batch.

For each idea, show:
```
IDEA-[NNN]: [Title]
Score: [N]/10 | [bucket]
Driven by: [top 2 dimensions]
Problem: [one line]
Claude says: [recommendation]

→ Your call: Promote / Park / Later / Reject / Needs Grill
```

For high-confidence scores (Promote or clear Reject): ask for quick confirm, don't re-explain.
For borderline scores: briefly explain the tension, then ask.
For "Needs Grill" ideas: mark them and move on — don't grill here.

## Step 3 — Update Artifacts

After developer decisions:

Update each `docs/ideas/IDEA-[NNN].md` status field.

Update `ROADMAP.md`:
- Promoted ideas → Now or Next column (max 1 in Now, 3 in Next)
- Parked ideas → Later column
- Rejected → Rejected table with reason
- Needs Grill → leave in ideas/, status: needs-grill

## Step 4 — Confirm

Report:
```
Triage complete.
Promoted: [N] ideas → ROADMAP.md
Parked:   [N] ideas
Rejected: [N] ideas
Needs grill: [N] ideas (run /feature when ready)

Now: [feature name if any]
Next: [up to 3 features]
```

Suggest next step if Now is populated: "Ready to plan [feature]? Run /feature."

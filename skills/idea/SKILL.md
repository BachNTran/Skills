---
name: idea
description: Capture an idea without interrupting active work. Runs a lightweight grill session to capture the essence of the idea — problem, who it affects, why it matters — then scores and saves it to docs/ideas/. Use when you have an idea and don't want to lose it.
---

You are capturing a new idea. Your job is to understand the essence of the idea without going into technical implementation details, score it, and save it — all without derailing active work.

## Rules

- Do NOT discuss implementation details
- Do NOT create branches or modify source code
- Do NOT triage or promote — only capture
- Stay in problem space: why, who, what solved
- Keep the session short — under 10 minutes

## Step 1 — Receive the Idea

Accept the idea as stated. Do not judge it yet.

If the idea came from a rubber-duck conversation, summarize what you heard and ask:
"It sounds like you're thinking about [summary]. Want me to capture this as an idea?"

## Step 2 — Light Grill (problem space only)

Ask these questions one at a time. Stop when you have enough to fill the artifact.

1. "What problem does this solve?"
2. "Who experiences this problem?"
3. "What does solved look like in one sentence?"
4. "Why does this matter now versus later?" (optional — skip if obvious)
5. "Any hard constraints already known?" (optional — skip if none)

Do NOT ask about:
- How to implement it
- What technology to use
- How long it will take
- What the architecture should be

## Step 3 — Score

Score silently using these dimensions (1–5 each):

| Dimension   | Question                                      |
|-------------|-----------------------------------------------|
| Vision fit  | Does it align with the project's purpose?     |
| User value  | Does it solve a real problem for a real user? |
| Leverage    | Does it unlock or accelerate future work?     |
| Fit         | Does it belong in this codebase/product?      |
| Effort      | How much work? (higher = more effort)         |
| Risk        | Could it break or complicate things? (higher = more risk) |

Normalized score (1–10):
`Score = round(((VisionFit + UserValue + Leverage + Fit) - (Effort + Risk) + 12) / 2.4)`

Bucket:
- 8–10 → Promote
- 5–7  → Park
- 3–4  → Later
- 1–2  → Reject

## Step 4 — Save Artifact

Generate a unique ID by reading existing files in `docs/ideas/` and incrementing.

Create `docs/ideas/IDEA-[NNN]-[short-slug].md`:

```markdown
---
id: IDEA-[NNN]
title: [Short descriptive title]
status: new
score: [1-10]
bucket: [Promote|Park|Later|Reject]
score-breakdown:
  vision-fit: [1-5]
  user-value: [1-5]
  leverage: [1-5]
  fit: [1-5]
  effort: [1-5]
  risk: [1-5]
captured: [YYYY-MM-DD]
---

# IDEA-[NNN]: [Title]

## Problem
[What problem this solves]

## Who
[Who experiences this problem]

## Solved Looks Like
[One sentence — what done looks like]

## Why Now
[Why this matters now vs later — or "Not time-sensitive"]

## Known Constraints
[Any hard constraints already known — or "None identified"]

## Claude Suggestion
Score: [N]/10 — [bucket]
Driven by: [top 2 dimensions that drove the score]
Recommendation: [one sentence on what to do with this idea]
```

## Step 5 — Confirm

Tell the developer:
"Captured as IDEA-[NNN]. Score: [N]/10 → [bucket]. Your active work is unchanged."

Do not suggest next steps. Do not triage now unless the developer asks.

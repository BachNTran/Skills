---
name: codex-delegate
description: Delegate a single bounded, ad-hoc task to Codex from Claude Code — investigation, a contained fix, or grunt implementation that sits outside an approved feature plan. For parallel slice work inside a feature plan, use /implement (it already delegates slices to Codex).
---

# Codex Delegate (ad-hoc)

Hand one bounded task to Codex when it is grunt work Claude should not spend context on, and it sits **outside** an approved feature plan. Inside a feature plan, `implement` already delegates slices to Codex worktrees — use that instead.

## When to use
- Investigate a failing test or regression.
- A contained, reversible fix with a clear "done".
- Mechanical refactor or boilerplate with disjoint scope.

## When NOT to use
- Anything needing requirement interpretation, architecture placement, or PRD/test-plan authorship — that stays Claude + developer (Tier 3).
- Multi-slice parallel work under a feature — use `implement`.

## How
Spawn the Codex worker directly via the Agent tool:

```
Agent(
  subagent_type: "codex:codex-rescue",
  run_in_background: true,     # foreground for a small, quick task
  prompt: "<one bounded task: what to do, which files are in scope,
            what 'done' looks like, the exact test command>"
)
```

Spawning the subagent directly bypasses the interactive `/codex:rescue` resume/fresh prompt. Codex is write-capable and runs full-auto — it never asks for approval. Keep it to **one task per run**; split unrelated asks into separate runs. When the developer would rather drive it themselves, tell them to type `/codex:rescue <task>`.

## Adjudication (Claude's job)
When Codex returns, Claude decides — on evidence, not Codex's word:
- Re-run the task's test command yourself before trusting any "pass".
- Inspect the diff: scope respected, no new dependency, no unrelated files touched.
- Fails once → re-delegate with tighter scope once. Fails again → stop and report to the developer.

## Reviews stay human-gated
If you ran `/codex:review` or `/codex:adversarial-review`, do **not** auto-apply the findings. Present them and ask the developer which to fix — per the plugin's own rule.

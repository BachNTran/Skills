---
name: implement
description: Execute an approved feature plan wave by wave, running TDD autonomously (parallel sub-agents in isolated worktrees where supported, otherwise sequential). Stops only on blockers that need a human decision. Use after /feature has produced an approved ISSUE_PLAN.md.
---

You are the implementation orchestrator. Your job is to execute an approved feature plan wave by wave, each slice running TDD. Where the agent supports parallel sub-agents, run one per slice in its own git worktree; otherwise run slices sequentially. You stop only when the developer's decision is required.

## On Start

Read in order:
1. `AGENTS.md`
2. `DEV_TRACKER.md` — which feature is active?
3. `docs/features/FEAT-[NNNN]/ISSUE_PLAN.md` — wave groups and slice order
4. `docs/features/FEAT-[NNNN]/PRD.md`
5. `docs/features/FEAT-[NNNN]/TEST_PLAN.md`
6. `CODING_STANDARDS.md`
7. `docs/knowledge-base/` relevant entries (if hardware feature)

Confirm: ISSUE_PLAN.md status is `approved`. If not approved — stop, run /feature first.

---

## PHASE 7 — WAVE ACTIVATION

### Confirm Base Branch, then Create Feature Branch and Worktree

Detect the current branch (`git rev-parse --abbrev-ref HEAD`) and ask the developer: "Use `[current-branch]` as the base for FEAT-[NNNN], or branch off a different one?" Do not touch the current branch directly — branch off whatever the developer confirms.

```bash
# After the developer confirms the base branch as $BASE
git checkout -b feature/FEAT-[NNNN]-[slug] "$BASE"
git worktree add .worktrees/FEAT-[NNNN] feature/FEAT-[NNNN]-[slug]
```

Record the confirmed base in `DEV_TRACKER.md` so PHASE 12 knows the merge target.

### Update DEV_TRACKER.md

Add feature to Active Features table with wave status.

### Analyze Dependency Graph

Read ISSUE_PLAN.md wave groups. Identify Wave 1 — all slices with no dependencies.

Verify no two Wave 1 slices share the same files (scope overlap check).
If overlap found → sequence those slices, do not parallelize.

---

## PHASE 8 — TDD EXECUTION

### Per Wave

For each wave, run its slices — one parallel sub-agent per slice where supported, otherwise sequentially. Each slice:

**Startup (shared context — cache-friendly, load once):**
- `PROJECT_CONTEXT.md`
- `AGENTS.md`
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/CONTEXT.md`
- `docs/features/FEAT-[NNNN]/PRD.md`
- `docs/features/FEAT-[NNNN]/TEST_PLAN.md`
- `CODING_STANDARDS.md`
- `docs/knowledge-base/` relevant entries (hardware only)

**Per-agent context (unique):**
- `docs/features/FEAT-[NNNN]/slices/S[NNN].md`
- Own git worktree: `.worktrees/FEAT-[NNNN]-S[NNN]/`
- Own branch: `feature/FEAT-[NNNN]-S[NNN]` (off feature branch)

**Baseline check:**
Run full test command. If baseline fails — STOP. Report as D-type blocker. Do not implement on a broken baseline.

**Hardware sanity check (hardware features only):**
Load `docs/knowledge-base/[component]/HARDWARE_ACCESS.md`.
Run sanity test sequence. If hardware does not behave as DOMAIN_CONTEXT.md specifies — STOP. Report as D-type blocker. Do not implement against wrong assumptions.

### TDD Loop (per acceptance criterion)

```
For each criterion in slice acceptance checklist:

  RED:
    Write the smallest test that proves this criterion.
    Run it — confirm it fails.
    If it fails for the wrong reason → fix the test first.

  GREEN:
    Write minimum code to pass the test.
    No more than what the test requires.
    Check reuse: does existing helper/double cover this?
      → yes: import and use it, do not create new
      → no: create in module location, not inline in test
    Run test — confirm pass.

  REFACTOR:
    Load CODING_STANDARDS.md.
    Apply naming conventions.
    Apply structural rules.
    Apply forbidden pattern checks.
    Run linter/static analysis — must pass.
    Run test — must still pass.
    If test fails after refactor → revert refactor, investigate.

  LOG:
    Append entry to docs/features/FEAT-[NNNN]/RISK_LOG.md
    if any risk was discovered during implementation.

Move to next criterion.
```

### Test Co-location Rule

Tests live as close to the code they test as possible.
Project convention wins on exact location — but record in MODULE_MAP.md if convention differs from self-contained ideal.

Test doubles:
- Never inline in test files
- Always in their own file, imported
- Always accompanied by a double specification document
- Reuse existing doubles — check before creating

### D-Type Blockers — Stop Conditions

Stop immediately and notify orchestrator if:

| Blocker type | Condition |
|---|---|
| Scope expansion | Need to touch a file not in allowed list |
| New dependency | Requires library/package not in project |
| Architecture unclear | Two valid placements, cannot decide |
| Budget exceeded | Need more files than maximum in slice |
| Baseline broken | Existing tests fail before any change |
| Hardware sanity fail | Hardware doesn't match DOMAIN_CONTEXT.md |
| Ambiguity | Acceptance criterion has two valid interpretations |

**Blocker report format:**
```
Slice: S[NNN]
Blocker type: [type]
Situation: [what happened]
Options: A / B / C
Recommendation: [which and why]
Files changed so far: [list]
Tests written so far: [list]
Safe to resume from here: yes/no
```

Developer decides. Resume when unblocked.

### Slice Completion Report

```
Slice: S[NNN]
Status: Done
Behavior: [one sentence — what now works]
Tests added: [list with commands]
Files changed: [list]
Files changed count: [n] of [budget]
Regression: PASS [command]
Reuse found: [yes — used X / no]
New doubles created: [yes — spec at path / no]
Risks: [any concerns]
Next slice unblocked: [list]
```

---

## PHASE 9 — AUTOMATED SLICE REVIEW

After each slice completion report:

**Automated checks (no human needed):**
```
□ All acceptance criteria checked off
□ Test command passes
□ Regression suite passes
□ Scope respected — only allowed files changed
□ File budget not exceeded
□ CODING_STANDARDS linter passes
□ No new dependencies introduced
□ No forbidden files touched
```

All pass → auto-merge slice branch to feature branch → delete slice worktree → notify orchestrator.
Any fail → report specific failure to developer.

**Append to `docs/features/FEAT-[NNNN]/REVIEW.md`:**
```markdown
## S[NNN] — [behavior] — [YYYY-MM-DD]
Result: PASS
Tests: [n] added, [n] passing
Files: [n] of [budget]
Linter: PASS
Regression: PASS
```

---

## PHASE 10 — HANDOFF (updated per wave)

After each wave completes, update `docs/features/FEAT-[NNNN]/HANDOFF.md` using the structure in [`templates/HANDOFF_TEMPLATE.md`](templates/HANDOFF_TEMPLATE.md).

---

## Wave Completion → Next Wave

When all slices in a wave are merged:
1. Run full regression suite on feature branch
2. If passes → spawn Wave N+1 sub-agents
3. If fails → report specific failure to developer before continuing

---

## PHASE 12 — FEATURE CLOSE

When all waves complete:

**Verify Branch 7 Success Criteria checklist from BRIEF.md:**
```
□ All slice acceptance criteria met
□ Regression suite passes: [exact command]
□ REVIEW.md complete for all slices
□ HANDOFF.md reflects final state
□ docs/architecture/ updated if boundaries changed
□ CODING_STANDARDS linter passes on all new code
□ No open D-type blockers in DEV_TRACKER.md
□ docs/knowledge-base/ updated if new hardware knowledge gained
□ Project-level RISK_LOG.md updated if risks have broader scope
```

Create merge request: `feature/FEAT-[NNNN]-[slug]` → the base branch confirmed at PHASE 7 (recorded in `DEV_TRACKER.md`).

Update DEV_TRACKER.md — move feature from Active to Pending MR.

Report:
```
FEAT-[NNNN] implementation complete.
[N] slices across [M] waves.
MR created: feature/FEAT-[NNNN]-[slug] → dev
Pending: developer merge approval

Suggest: run /cleanup before starting next feature.
```

Developer signs off → feature closed.

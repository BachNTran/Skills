---
name: implement
description: Execute an approved feature plan wave by wave, running TDD autonomously (parallel sub-agents in isolated worktrees where supported, otherwise sequential). Stops only on blockers that need a human decision. Use after /feature has produced an approved ISSUE_PLAN.md.
---

You are the implementation orchestrator. Your job is to execute an approved feature plan wave by wave, each slice running TDD. Where the agent supports parallel sub-agents, run one per slice in its own git worktree; otherwise run slices sequentially. You stop only when the developer's decision is required.

## On Start

Read in order:
1. `AGENTS.md`
2. `ProjectManagement/DEV_TRACKER.md` — which feature is active?
3. `ProjectManagement/features/FEAT-[NNNN]/ISSUE_PLAN.md` — wave groups and slice order
4. `ProjectManagement/features/FEAT-[NNNN]/PRD.md`
5. `ProjectManagement/features/FEAT-[NNNN]/TEST_PLAN.md`
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

Record the confirmed base in `ProjectManagement/DEV_TRACKER.md` so PHASE 12 knows the merge target.

### Update ProjectManagement/DEV_TRACKER.md

Add feature to Active Features table with wave status.

### Analyze Dependency Graph

Read ISSUE_PLAN.md wave groups. Identify Wave 1 — all slices with no dependencies.

Verify no two Wave 1 slices share the same files (scope overlap check).
If overlap found → sequence those slices, do not parallelize.

---

## PHASE 8 — TDD EXECUTION

### Per Wave

For each wave, run its slices — one parallel sub-agent per slice where supported, otherwise sequentially. Each slice runs on one worker (see below).

### Worker Selection (Claude or Codex)

Pick a worker per slice. You decide — do not ask the developer.

- **Claude sub-agent** (default) — slices needing architecture judgment, ambiguous placement, or tight coupling to in-flight Claude work.
- **Codex sub-agent** — bounded grunt work: straightforward TDD implementation, test authoring, mechanical refactor. Offloads the grind off Claude's context and runs full-auto.

Choose Codex only when the slice is bounded, testable, and its Scope/Non-Scope files are **disjoint from every other concurrently-running slice** (this is the same overlap check from PHASE 7 — it is the invariant that keeps parallel merges clean). Choose Claude otherwise.

Concurrency cap: at most **4** Codex sub-agents running at once (configurable). Queue the rest.

### Codex Slice Delegation

Spawn one Codex worker per slice via the Agent tool — **not** the `/codex:rescue` command (that fires an interactive resume/fresh prompt):

```
Agent(
  subagent_type: "codex:codex-rescue",
  isolation: "worktree",      # or bind cwd to .worktrees/FEAT-[NNNN]-S[NNN] — verify cwd plumbing on first run
  run_in_background: true,
  prompt: <slice packet from S[NNN].md: Behavior, Scope (allowed), Non-Scope,
           Acceptance Criteria, Test Command, File Budget — one slice per run>
)
```

Spawning the subagent directly bypasses the resume/fresh prompt, so Codex runs with no approval question. Codex is write-capable by default and must be in a non-interactive auto-approve mode so it does not block on its own per-edit prompts.

Codex is fully automated — it never asks the developer for approval. When it returns, **Claude adjudicates on evidence** (PHASE 9), it does not take Codex's word.

**Hard stops — escalate to the developer as a D-type blocker only when:**

| Condition | Action |
|---|---|
| Slice fails its gate twice | One re-delegate with tighter scope, then stop |
| Codex needs an out-of-scope file or a new dependency | Stop — violates the disjointness invariant |
| Codex output contradicts PRD/TEST_PLAN | Stop — the spec is developer-owned |
| Concurrency cap (4) reached | Queue, do not exceed |

Everything else, Claude resolves itself without asking.

### While Codex Runs (monitoring + parallel work)

Backgrounded Codex workers free the main thread. While they grind:

- **Know when it finishes:** background workers auto-notify the session on completion — you are not left guessing. The orchestrator reports each slice as it lands.
- **Watch it live:** every Codex job appends a timestamped progress log to its own `<job-id>.log` file (under `$CLAUDE_PLUGIN_DATA/state/<workspace-basename>-<hash>/jobs/`, where `<hash>` is a sha256 of the workspace path — so the path is **not** hand-guessable). The reliable way to surface it: `/codex:status <id> --wait` blocks and prints each new progress entry as it lands; plain `/codex:status` shows all jobs as a table. On spawning each worker the orchestrator must print that worker's **job id** so you can `/codex:status <id> --wait` it. If you want a raw `tail -f`, ask and the orchestrator will read the job's stored `logFile` path from its state record and hand you the exact command.
- **Fullest view:** `/codex:result <id>` returns a Codex session ID — `codex resume <session-id>` attaches to that exact run to watch its reasoning and edits live. The progress log is a phase-level heartbeat (started / thinking / editing / testing), not full chain-of-thought; use `resume` when you want to see everything.
- **Keep planning:** the orchestrator may run planning work — `/feature` grilling, slicing, PRD/test-plan — for the next feature while Codex implements the current one. That writes to `ProjectManagement/` docs, never the slice code in Codex's worktrees, so it cannot collide.
- **Do not** start a Claude code-writing slice on files that overlap a running Codex worktree. Non-writing work only, or disjoint files.

**Startup (shared context — cache-friendly, load once):**
- `PROJECT_CONTEXT.md`
- `AGENTS.md`
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/CONTEXT.md`
- `ProjectManagement/features/FEAT-[NNNN]/PRD.md`
- `ProjectManagement/features/FEAT-[NNNN]/TEST_PLAN.md`
- `CODING_STANDARDS.md`
- `docs/knowledge-base/` relevant entries (hardware only)

**Per-agent context (unique):**
- `ProjectManagement/features/FEAT-[NNNN]/slices/S[NNN].md`
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
    Append entry to ProjectManagement/features/FEAT-[NNNN]/ProjectManagement/RISK_LOG.md
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

After each slice completion report. Applies to every slice regardless of worker.

For **Codex** slices, Claude re-runs the slice Test Command **and** the regression suite **in the slice worktree** before trusting any result — a Codex "pass" claim is not evidence.

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

**Append to `ProjectManagement/features/FEAT-[NNNN]/REVIEW.md`:**
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

After each wave completes, update `ProjectManagement/features/FEAT-[NNNN]/HANDOFF.md` using the structure in [`templates/HANDOFF_TEMPLATE.md`](templates/HANDOFF_TEMPLATE.md).

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
□ No open D-type blockers in ProjectManagement/DEV_TRACKER.md
□ docs/knowledge-base/ updated if new hardware knowledge gained
□ Project-level ProjectManagement/RISK_LOG.md updated if risks have broader scope
```

Create merge request: `feature/FEAT-[NNNN]-[slug]` → the base branch confirmed at PHASE 7 (recorded in `ProjectManagement/DEV_TRACKER.md`).

Update ProjectManagement/DEV_TRACKER.md — move feature from Active to Pending MR.

Report:
```
FEAT-[NNNN] implementation complete.
[N] slices across [M] waves.
MR created: feature/FEAT-[NNNN]-[slug] → dev
Pending: developer merge approval

Suggest: run /cleanup before starting next feature.
```

Developer signs off → feature closed.

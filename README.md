# AI-Assisted Development Workflow

A structured workflow that lets an AI coding agent do the grunt work at speed while the developer stays in control. Clean code, tested behavior, durable documentation — without the chaos of unstructured AI coding sessions.

Built as slash-command **skills** for Claude Code, with all rules in **AGENTS.md** so any AGENTS.md-aware agent (Codex, Cursor, …) can follow the same methodology.

## How It Works

```
IDEA → TRIAGE → FEATURE PLANNING → IMPLEMENTATION → CLEANUP
```

You capture ideas without interrupting active work. The agent grills you on each feature until the vision is clear. Once you approve the plan, it executes autonomously — stopping only when your judgment is required. Every decision is documented. Every behavior is tested. Nothing merges without proof.

## Skills

| Skill | When to use |
|---|---|
| `/workflow` | Start here — always. Context-aware guide to your next step. |
| `/idea` | Capture an idea without interrupting active work. |
| `/triage` | Sort the idea backlog and update the roadmap. |
| `/feature` | Plan a feature end-to-end (grill → PRD → test plan → slices). |
| `/implement` | Execute an approved feature plan (TDD → MR). |
| `/cleanup` | Periodic architecture review and cleanup. |
| `/onboard` | Walk a new or returning developer through the project. |
| `/codex-delegate` | Hand one bounded ad-hoc task to Codex outside an approved feature plan. |
| `/gemma-delegate` | Delegate bounded, test-driven local work to Gemma 4 26B MoE through `opencode --pure`. |

When in doubt, run `/workflow` and the agent tells you the next step. (Agents without slash commands: point them at the matching file under `skills/`.)

## Context Cost

Approximate tokens per skill, measured with tiktoken `cl100k_base` (Claude's tokenizer is similar; values are within ~10%).

| Skill        |   Hint¹ |   Body² |  Lazy templates³ |
|--------------|--------:|--------:|-----------------:|
| `/workflow`        |      45 |     574 | —                |
| `/idea`            |      57 |     807 | —                |
| `/triage`          |      51 |     529 | —                |
| `/feature`         |      52 |   2,268 | 651  (4 files)   |
| `/implement`       |      51 |   2,912 | 189  (1 file)    |
| `/cleanup`         |      49 |     846 | —                |
| `/onboard`         |      54 |     949 | —                |
| `/codex-delegate`  |      54 |     443 | —                |
| `/gemma-delegate`  |      51 |   1,470 | —                |
| **Total**          | **464** | **10,798** | **840**        |

¹ **Hint** — the skill's `description:` field, loaded into always-on context so the agent knows when to invoke the skill. Paid every session.
² **Body** — the full `SKILL.md`, loaded only when the skill is invoked.
³ **Lazy templates** — per-phase template files (PRD, slice, ISSUE_PLAN, TEST_PLAN_DIMENSIONS, HANDOFF) that load only when the corresponding phase runs. They live under `skills/<skill>/templates/` and travel with the skill on install.

Reproduce: `python3 -c "import tiktoken; e=tiktoken.get_encoding('cl100k_base'); ...` over `skills/**/*.md`.

## Install

Run with no arguments for a guided TUI session (requires Python 3):

```bash
./install.sh
```

Or pass a target directly to skip the TUI:

```bash
./install.sh global      # all Claude Code sessions  → ~/.claude/skills/
./install.sh codex       # all Codex sessions        → ~/.codex/skills/
./install.sh project     # this project only         → .claude/skills/
./install.sh bootstrap   # project install + scaffold project docs
./install.sh validate    # validate skill frontmatter before installing
```

`bootstrap` also creates the project structure:

- **Permanent context** at root: `AGENTS.md` (+ thin `CLAUDE.md` pointer), `PROJECT_CONTEXT.md`, `CODING_STANDARDS.md`.
- **ProjectManagement/** for transient work-tracking: `ROADMAP.md`, `DEV_TRACKER.md`, `RISK_LOG.md`, `ideas/`, `features/`.
- **docs/** for durable knowledge: `architecture/`, `decisions/`, `knowledge-base/`.

Then fill in `PROJECT_CONTEXT.md` + `CODING_STANDARDS.md` and run `/workflow`.

## Project Structure Created

```
project-root/
├── AGENTS.md                        ← canonical agent instructions (all rules)
├── CLAUDE.md                        ← thin pointer so Claude Code auto-loads AGENTS.md
├── PROJECT_CONTEXT.md               ← what this project is
├── CODING_STANDARDS.md              ← coding rules + linter
│
├── ProjectManagement/               ← transient work tracking
│   ├── ROADMAP.md                   ← feature priority
│   ├── DEV_TRACKER.md               ← active work board
│   ├── RISK_LOG.md                  ← project-wide risks
│   ├── ideas/                       ← captured ideas (one file per idea)
│   └── features/
│       └── FEAT-0001-name/
│           ├── BRIEF.md             ← grill output
│           ├── PRD.md               ← frozen requirements
│           ├── TEST_PLAN.md         ← concrete test cases
│           ├── ISSUE_PLAN.md        ← slice plan
│           ├── REVIEW.md            ← per-slice review
│           ├── HANDOFF.md           ← resume context
│           ├── RISK_LOG.md          ← feature-scoped risks
│           ├── decisions/           ← feature-scoped ADRs
│           └── slices/              ← S001.md, S002.md, ...
│
└── docs/                             ← durable knowledge
    ├── architecture/                ← ARCHITECTURE.md, MODULE_MAP.md, CONTEXT.md, GLOSSARY.md
    ├── decisions/                   ← project-wide ADRs
    └── knowledge-base/              ← hardware/domain knowledge (permanent)
```

Docs may reference features in `ProjectManagement/` (e.g., an ADR cites the feature that drove it); features do not reference each other through `docs/`.

## Daily Use

**Morning / session start:**
```
/workflow
```
The agent reads the current state and tells you exactly what to do next.

**You have an idea:**
```
/idea
```
Or just describe it naturally — the agent will detect idea-like content and offer to capture it without derailing your active work.

**Ready to plan a feature:**
```
/feature
```
The agent grills you until the vision is clear, then produces all planning artifacts (BRIEF, PRD, TEST_PLAN, ISSUE_PLAN, slices). Nothing moves to implementation until you approve.

**Ready to build:**
```
/implement
```
The agent confirms the base branch with you, then runs TDD on each slice — parallel sub-agents in isolated worktrees where supported, sequential otherwise. You only get interrupted on blockers.

**Need ad-hoc delegation:**
```
/codex-delegate
/gemma-delegate
```
Use Codex for one bounded coding task. Use local Gemma through `opencode --pure` for tightly scoped, test-driven work where the parent owns verification and integration.

Gemma delegation benchmark: the successful local RangeMap calibration used 78,503 Gemma tokens over 285s while keeping the parent-visible artifact estimate to about 1,699 tokens. That is premium-token displacement, not total-token reduction. Details live in `skills/gemma-delegate/README.md`.

**After a feature ships:**
```
/cleanup
```
The agent reviews the architecture and proposes refactor slices (to the idea backlog) before the next feature starts. Cleanup is never mixed with feature work.

**New to the project:**
```
/onboard
```
The agent reads everything and gives you a complete picture of the project, then guides you to your first action.

## Philosophy

- **Developer always in the loop** — you approve every plan before execution starts.
- **Autonomous execution** — once approved, the agent runs uninterrupted unless your judgment is required.
- **Durable artifacts** — every decision is documented; any session resumes without chat history.
- **Vertical slices** — every unit of work is independently testable and produces observable behavior.
- **TDD enforced** — tests are written before implementation, always.
- **Clean architecture** — module independence, test co-location, reuse before create.

## Requirements

- An AI coding agent. Skills install as Claude Code slash commands; any AGENTS.md-aware agent (Codex, Cursor, …) can follow the same workflow by reading the files directly.
- Python 3 (pre-installed on macOS and most Linux distros) — required for the installer only.
- Parallel execution needs sub-agent + git-worktree support; otherwise slices run sequentially.
- Git. `/implement` asks you to confirm the base branch before branching (no hard-coded `main`/`dev`).

## References

- [AI Hero Skills](https://www.aihero.dev/skills) — Matt Pocock's agent skills (inspiration)
- [AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md) — agent instruction files

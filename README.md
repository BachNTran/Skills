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

When in doubt, run `/workflow` and the agent tells you the next step. (Agents without slash commands: point them at the matching file under `skills/`.)

## Install

```bash
./install.sh global      # all projects  → ~/.claude/skills/
./install.sh project     # this project  → .claude/skills/
./install.sh bootstrap   # project install + create project docs
```

`bootstrap` also creates the documentation structure: `AGENTS.md` (plus a thin `CLAUDE.md` pointer), `PROJECT_CONTEXT.md`, `ROADMAP.md`, `DEV_TRACKER.md`, `CODING_STANDARDS.md`, `RISK_LOG.md`, and `docs/{ideas,architecture,decisions,knowledge-base,features}/`.

Then fill in `PROJECT_CONTEXT.md` + `CODING_STANDARDS.md` and run `/workflow`.

## Project Structure Created

```
project-root/
├── AGENTS.md                        ← canonical agent instructions (all rules)
├── CLAUDE.md                        ← thin pointer so Claude Code auto-loads AGENTS.md
├── PROJECT_CONTEXT.md               ← what this project is
├── CODING_STANDARDS.md              ← coding rules + linter
├── ROADMAP.md                       ← feature priority
├── DEV_TRACKER.md                   ← active work board
├── RISK_LOG.md                      ← project-wide risks
│
└── docs/
    ├── ideas/                       ← captured ideas (one file per idea)
    ├── architecture/                ← ARCHITECTURE.md, MODULE_MAP.md, CONTEXT.md
    ├── decisions/                   ← project-wide ADRs
    ├── knowledge-base/              ← hardware/domain knowledge (permanent)
    └── features/
        └── FEAT-0001-name/
            ├── BRIEF.md             ← grill output
            ├── PRD.md               ← frozen requirements
            ├── TEST_PLAN.md         ← concrete test cases
            ├── ISSUE_PLAN.md        ← slice plan
            ├── REVIEW.md            ← per-slice review
            ├── HANDOFF.md           ← resume context
            ├── RISK_LOG.md          ← feature-scoped risks
            ├── decisions/           ← feature-scoped ADRs
            └── slices/              ← S001.md, S002.md, ...
```

## Philosophy

- **Developer always in the loop** — you approve every plan before execution starts.
- **Autonomous execution** — once approved, the agent runs uninterrupted unless your judgment is required.
- **Durable artifacts** — every decision is documented; any session resumes without chat history.
- **Vertical slices** — every unit of work is independently testable and produces observable behavior.
- **TDD enforced** — tests are written before implementation, always.
- **Clean architecture** — module independence, test co-location, reuse before create.

## Requirements

- An AI coding agent. Skills install as Claude Code slash commands; any AGENTS.md-aware agent can follow the same workflow by reading the files.
- Parallel execution needs sub-agent + git-worktree support; otherwise slices run sequentially.
- Git. `/implement` asks you to confirm the base branch before branching (no hard-coded `main`/`dev`).

## References

- [AI Hero Skills](https://www.aihero.dev/skills) — Matt Pocock's agent skills (inspiration)
- [AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md) — agent instruction files

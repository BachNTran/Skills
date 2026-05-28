# AI-Assisted Development Workflow

A structured workflow for Claude Code that keeps the developer in control while enabling autonomous sub-agent execution. Clean code, tested behavior, durable documentation — without the chaos of unstructured AI coding sessions.

## How It Works

```
IDEA → TRIAGE → FEATURE PLANNING → IMPLEMENTATION → CLEANUP
```

You capture ideas without interrupting active work. Claude grills you on each feature until the vision is clear. Once you approve the plan, Claude executes autonomously — stopping only when your judgment is required. Every decision is documented. Every behavior is tested. Nothing merges without proof.

## Skills

| Skill | When to use |
|---|---|
| `/workflow` | Start here — always. Context-aware guide to your next step. |
| `/idea` | Capture an idea without interrupting active work |
| `/triage` | Sort your idea backlog and update the roadmap |
| `/feature` | Plan a feature end-to-end (grill → PRD → test plan → slices) |
| `/implement` | Execute an approved feature plan (TDD → MR) |
| `/cleanup` | Periodic architecture review and cleanup |
| `/onboard` | Walk a new or returning developer through the project |

**When in doubt: type `/workflow` and Claude will tell you what to do next.**

## Install

### Global (available in all projects)

```bash
./install.sh global
```

Skills installed to `~/.claude/skills/`. Available everywhere.

### Project-level (this project only)

```bash
./install.sh project
```

Skills installed to `.claude/skills/`. Checked into your repo.

### Bootstrap a new project (install + create project docs)

```bash
./install.sh bootstrap
```

Installs skills and creates the full project documentation structure:
- `CLAUDE.md`, `AGENTS.md`, `PROJECT_CONTEXT.md`
- `ROADMAP.md`, `DEV_TRACKER.md`, `CODING_STANDARDS.md`, `RISK_LOG.md`
- `docs/architecture/`, `docs/decisions/`, `docs/features/`, `docs/ideas/`, `docs/knowledge-base/`

Then fill in `PROJECT_CONTEXT.md` and run `/workflow`.

## Project Structure Created

```
project-root/
├── CLAUDE.md                        ← workflow guide for Claude
├── AGENTS.md                        ← hard rules for agents
├── PROJECT_CONTEXT.md               ← what this project is
├── CODING_STANDARDS.md              ← coding rules + linter
├── ROADMAP.md                       ← feature priority
├── DEV_TRACKER.md                   ← active work board
├── RISK_LOG.md                      ← project-wide risks
│
└── docs/
    ├── ideas/                       ← captured ideas (per idea)
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

## Daily Use

**Morning / session start:**
```
/workflow
```
Claude reads the current state and tells you exactly what to do next.

**You have an idea:**
```
/idea
```
Or just tell Claude naturally — it will detect idea-like content and offer to capture it.

**Ready to plan a feature:**
```
/feature
```
Claude grills you until the feature is fully understood, then produces all planning artifacts.

**Ready to build:**
```
/implement
```
Claude spawns parallel sub-agents, each executing TDD in isolated worktrees. You only get interrupted on blockers.

**After a feature ships:**
```
/cleanup
```
Claude reviews the architecture and proposes any refactor slices before the next feature starts.

**New to the project:**
```
/onboard
```
Claude reads everything and gives you a complete picture of the project, then guides you to your first action.

## Philosophy

- **Developer always in the loop** — you approve every plan before execution starts
- **Autonomous execution** — once approved, Claude runs without interruption unless your judgment is required
- **Durable artifacts** — every decision is documented; any session can resume without chat history
- **Vertical slices** — every unit of work is independently testable and produces observable behavior
- **TDD enforced** — tests are written before implementation, always
- **Clean architecture** — module independence, test co-location, reuse before create

## Requirements

- Claude Code with sub-agent support
- Git (for worktree-based parallel execution)
- A project with a `dev` branch as the integration branch

## References

- [AI Hero Skills](https://www.aihero.dev/skills) — Matt Pocock's agent skills (inspiration)
- [AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md) — agent instruction files

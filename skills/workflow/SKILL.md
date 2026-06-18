---
name: workflow
description: Master workflow orchestrator. Context-aware — reads current project state and guides developer to the right next step. Use when unsure what to do, starting a new session, or wanting to drive the full dev cycle end-to-end.
---

You are the master workflow orchestrator for this project's AI-assisted development workflow.

## On Start

**Context is always project-local.** Skills may be installed globally (`~/.claude/skills/`)
and shared across projects, but each project keeps its own config, context, domain knowledge,
preferences, and traceability **inside the project**. Never write project knowledge into the
global skills location.

Before guiding anything:

1. Check for `PROJECT_CONTEXT.md` in the project root.
   - **Missing** → the project isn't bootstrapped (likely a global install used here for the
     first time). Go to the **No project scaffold** branch below.
2. Read `PROJECT_CONTEXT.md`. If its **`criticality:`** field is unset, run the **Config Grill**
   before any feature work.

Then read these files in order:
1. `AGENTS.md` — workflow rules and project guidance
2. `PROJECT_CONTEXT.md` — what this project is (incl. criticality tier)
3. `ProjectManagement/DEV_TRACKER.md` — current active work
4. `ProjectManagement/ROADMAP.md` — planned and candidate features

Then detect the current project state and guide the developer to the right next step.

## Config Grill (project setup)

Runs once per project — when there's no scaffold, or when `criticality:` is unset. Ask the
whole set **at once** (don't drip questions one at a time), propose a recommended answer for
each, then write the result to project-local files.

Ask together:
- **Criticality tier** — EXPLORE / STANDARD / CRITICAL (see PROJECT_CONTEXT → Criticality &
  Autonomy). Propose one from the project's nature (throwaway/fun → EXPLORE; normal product →
  STANDARD; safety/expensive-to-fail → CRITICAL).
- **Domain** — does this touch hardware, peripherals, or a specialized domain? (If yes, the
  feature pipeline will capture domain knowledge into project-local `docs/knowledge-base/`.)
- **Tech basics** — language, test runner, linter, build command (fills PROJECT_CONTEXT TODOs).

On confirmation, write `criticality:` and the answers into the project-local
`PROJECT_CONTEXT.md`, and report the saved config. This is the project's durable config — it
persists across sessions and across a global skills upgrade.

## State Detection

### No project scaffold (no PROJECT_CONTEXT.md)
Say: "This project isn't set up for the workflow yet. I'll scaffold it here in the project —
skills can be global, but this project's context, config, and history stay local to it."
Then: create the project-local scaffold from templates (PROJECT_CONTEXT.md, AGENTS.md +
CLAUDE.md pointer, ProjectManagement/, docs/), run the **Config Grill**, and stop for the
developer to fill the remaining context. Do not write any of this into the global skills dir.

### No ideas, empty project
Say: "No ideas captured yet. Tell me what you want to build, or describe a problem you want to solve."
Then run the `/idea` skill inline.

### Ideas exist, not triaged
Say: "You have [N] unscored ideas in `ProjectManagement/ideas/`. Want to triage them?"
Suggest: `/triage`

### Ideas triaged, nothing in Now
Say: "Your roadmap has [X] as a Next candidate. Ready to plan it as a feature?"
Suggest: `/feature`

### Feature planned (BRIEF/PRD/TEST_PLAN/ISSUE_PLAN all approved), not executing
Say: "FEAT-[X] is fully planned and ready to execute. Start implementation?"
Suggest: `/implement`

### Feature executing (waves in progress)
Say: "FEAT-[X] Wave [N] is in progress. [M] slices remaining in this wave. Continue?"
Read `ProjectManagement/DEV_TRACKER.md` and resume the active wave.

### Feature complete, MR pending
Say: "FEAT-[X] is complete. MR is pending merge to dev. Run architecture cleanup before starting the next feature?"
Suggest: `/cleanup`

### New developer or confused
Ask: "Are you new to this project?"
If yes or unclear: run `/onboard` inline.

## Developer Overrides

Always accept natural language overrides:
- "I have an idea" → run `/idea`
- "What should I work on?" → show ProjectManagement/ROADMAP.md Now column
- "What is the project?" → summarize PROJECT_CONTEXT.md
- "What's the status?" → summarize ProjectManagement/DEV_TRACKER.md
- "I want to add a feature" → run `/feature`
- "Start building" → run `/implement`
- "Clean up the code" → run `/cleanup`
- "Walk me through the project" → run `/onboard`

## Rules

- Never start implementing without an approved ISSUE_PLAN.md
- Never start planning without reading current ProjectManagement/DEV_TRACKER.md first
- Never suggest two skills at once — one clear next step only
- If project files don't exist yet, offer to bootstrap them using templates
- Project context, config, domain knowledge, and traceability are always saved project-local —
  never into the global skills location, even when skills are installed globally
- Respect the project's criticality tier in every suggestion (EXPLORE/STANDARD/CRITICAL)

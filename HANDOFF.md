# HANDOFF — invisible-workflow redesign

**Branch:** `feat/invisible-workflow-phase0` · **Design:** [`docs/decisions/ADR-0001-invisible-workflow.md`](docs/decisions/ADR-0001-invisible-workflow.md)

Resume point for the redesign that makes this skillset intent-routed, self-enforcing, and
fully traceable. Pick up by reading the ADR, then this file.

## Where we are

All seven planned phases are built, tested, and committed (`558ebba`…`888c49b`):

| Phase | Done | Key files |
|-------|------|-----------|
| 0 | Criticality tiers + project-local config grill | `templates/PROJECT_CONTEXT.md`, `templates/AGENTS.md`, `skills/workflow/SKILL.md` |
| 1 | DEC ledger + EARS REQs + trace IDs | `skills/feature/templates/DECISIONS_TEMPLATE.md`, `…/PRD_TEMPLATE.md`, `skills/feature/SKILL.md` |
| 2 | Trace-index generator + tests → `TRACE.md` | `tools/trace_index.py`, `tools/test_trace_index.py` |
| 3 | Preferences memory + SessionStart/PostToolUse hooks (project-local) | `templates/PREFERENCES.md`, `tools/hooks/*.py`, `templates/settings.json`, `install_tui.py` |
| 4 | Intent router + batch-grill + bottom-up walk | `templates/AGENTS.md`, `skills/feature/SKILL.md`, `skills/workflow/SKILL.md` |
| 5 | `/revise` complaint → revision loop | `skills/revise/SKILL.md`, `skills/revise/templates/COMPLAINTS_TEMPLATE.md` |
| 6 | Project rollup + token-budget README refresh | `tools/trace_index.py`, `README.md` |

`python3 -m pytest tools/` → 6 pass. Bootstrap + both hooks smoke-tested.

## What is NOT done yet

- **Not merged.** PR opened from this branch; review before merge.
- **Not dogfooded end-to-end.** The generator and hooks are tested code, but the skill-instruction
  changes (router, batch-grill, `/revise`, milestone reconcile) are prose the agent follows. They
  haven't been exercised by running a real feature through a bootstrapped project.
- **System/subsystem auto-mermaid** is limited to the trace graph + project rollup. Auto-generating
  an architecture map from `MODULE_MAP.md` was deliberately left to hand-curated `/diagram`
  (parsing arbitrary module maps is unreliable). Candidate future phase if wanted.

## Next steps (suggested order)

1. **Dogfood:** `./install.sh bootstrap` in a throwaway project, set a criticality tier, run one
   small feature ("add X") through grill → PRD → tests → implement, then ask "why does X exist?"
   and confirm the bottom-up walk + `TRACE.md` + orphan report all work.
2. Fix any rough edges the dogfood surfaces (likely in the skill prose, not the tooling).
3. Decide on the architecture auto-mermaid question above.
4. Merge the PR; delete this `HANDOFF.md` on merge (it's a transient resume note).

## How to resume

Memory file `invisible-workflow-vision` (+ `prefers-batched-questions`) carries the full vision
and locked decisions for the next session.

---
name: modgate
description: Gated module development with modgate. Use in any project with a modgate.yaml — when planning, changing or reviewing modules, requirements, ICDs, tests or code, and whenever modgate finding lines appear in context.
---

# modgate — development rules

Detail: `guideline/Dev-Guideline-with-LLMs.md` (§9 is the source of these rules). Templates: `templates/`.

- Hooks run modgate: `pending` lines arrive at session start, `sync` lines after each edit. Act on those
  lines (`CODE module id files → next action`); never read whole trees to find what changed.
- modgate.yaml missing `criticality`, `diagrams` or `coding_standard` (a CONFIG line): ask once, save it.
- The developer talks naturally: map it onto brief → grill → req → ICD → test plan → code.
- Grill one question at a time until every assumption is cleared, then summarise the aligned
  understanding and let the developer confirm it before drafting. Depth scales with criticality.
- Gates go out as one bundle with one overview picture (Mermaid): where the module sits, its
  FEAT → REQ → TC chain, and what needs whose approval. Never a stream of separate prompts.
- Trust only `verified` modules; drafts are proposals — say so. `approved, untested` → `modgate sync <m> --test <target>`.
  STALE or DEPCHANGED → tell the developer; deep review first.
- Before editing a module read its overview, approved req and ICD. Stay inside it; others only via their ICD.
- Never change code without revisiting the docs bound to it (`<m>.bind.yaml`). A DRIFT line means: update the
  REQ/TCs, or propose `modgate approve <m> REQ-…` with a one-line "no requirement impact" reason.
- Any controlled-doc change: version +1, `status: draft`, append a changelog entry
  (`### YYYY-MM-DD-xxxx · vN · <doc> · <author>`). Keep activity.md and bind.yaml current.
- Changes flow down only; never reopen upstream docs unless the developer asks.
- Never approve yourself. Propose `modgate approve <m> <doc|REQ|all>`; the developer confirms (permission *ask*).
  AI-reviewer sign-off only in a fresh session and only where criticality allows. Never hand-write approvals,
  hashes, trace files or test records.
- New throwaway script → a `study` module; when done ask: keep or throw away?
- Session end: run `modgate pending`, say what awaits approval.

## How to change code
- Think first: state assumptions; if the request is ambiguous, ask instead of guessing.
- Simplest thing that works: right-size; no speculative features, options or abstractions.
- Surgical: touch only the lines the task needs; don't reformat, rename or "improve" nearby code.
- Goal-driven: define the check first (a failing test naming its REQ), then loop until it passes.

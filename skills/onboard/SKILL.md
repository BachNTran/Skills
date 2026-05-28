---
name: onboard
description: Walk a new developer (or returning developer) through the project. Reads all cumulative project docs, explains the current state, answers questions, and guides to the right next action. Use when new to a project, returning after a break, or unsure what to do next.
---

You are onboarding a developer to this project. Your job is to give a complete picture of what the project is, how it is structured, what has been built, what is in progress, and what to do next — all without requiring the developer to read every file themselves.

## On Start

Read everything before saying anything:

**Project identity:**
- `PROJECT_CONTEXT.md`
- `AGENTS.md`
- `CODING_STANDARDS.md`

**Architecture:**
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/MODULE_MAP.md`
- `docs/architecture/CONTEXT.md`
- `docs/architecture/GLOSSARY.md`

**Current state:**
- `ProjectManagement/ROADMAP.md`
- `ProjectManagement/DEV_TRACKER.md`
- `ProjectManagement/RISK_LOG.md`

**Recent features (last 3 completed):**
- `ProjectManagement/features/[recent]/HANDOFF.md`
- `ProjectManagement/features/[recent]/REVIEW.md`

**Active feature (if any):**
- `ProjectManagement/features/[active]/BRIEF.md`
- `ProjectManagement/features/[active]/HANDOFF.md`
- `ProjectManagement/features/[active]/ISSUE_PLAN.md`

**Knowledge base:**
- `docs/knowledge-base/` (all entries if hardware project)
- `docs/decisions/` (all project-wide ADRs)

Then ask: "Are you new to this project, returning after a break, or looking for what to do next?"

Adapt the walkthrough depth based on the answer.

---

## Walkthrough Structure

### 1. What This Project Is (2-3 sentences)
Summarize from PROJECT_CONTEXT.md.
Mention the core problem it solves and who it's for.

### 2. How the Codebase is Organized
Explain MODULE_MAP.md in plain language.
"If you want to change X, start in [module]. If you want to change Y, start in [module]."
Mention the dependency direction rule from ARCHITECTURE.md.

### 3. Shared Language
Highlight 3-5 most important terms from CONTEXT.md/GLOSSARY.md.
Mention any terms to avoid (anti-glossary).

### 4. How Development Works Here
Explain the workflow spine briefly:
Idea → Triage → Feature Planning → Implementation → Cleanup
Point to AGENTS.md for full rules.
Explain the skills and when to use each.

### 5. What Has Been Built
Summarize completed features from recent HANDOFF.md files.
One sentence per feature: what it does, where it lives.

### 6. What Is In Progress
Summarize active feature from ProjectManagement/DEV_TRACKER.md + HANDOFF.md.
Current wave, remaining slices, any open blockers.

### 7. What Is Planned Next
Summarize ProjectManagement/ROADMAP.md Now/Next columns.
One sentence per item.

### 8. Known Risks
Summarize ProjectManagement/RISK_LOG.md — top 2-3 risks worth knowing.

### 9. Knowledge Base (hardware projects only)
List documented hardware components in docs/knowledge-base/.
"Before touching [subsystem], read [DOMAIN_CONTEXT.md path]."

---

## Interactive Q&A

After the walkthrough, ask: "What would you like to know more about, or what are you trying to do?"

Answer questions by reading relevant files — do not answer from memory alone.

Common questions to handle well:
- "Where do I start if I want to add [X]?" → MODULE_MAP.md + ARCHITECTURE.md
- "What is [term]?" → CONTEXT.md / GLOSSARY.md
- "Why was [decision] made?" → docs/decisions/ ADRs
- "What tests exist for [module]?" → scan test files in module
- "How do I run the tests?" → CODING_STANDARDS.md test command
- "What should I work on?" → ProjectManagement/ROADMAP.md + ProjectManagement/DEV_TRACKER.md

---

## Guide to Next Action

End with a clear single recommendation:

```
Based on the current state:

Active feature:   [FEAT-NNNN or none]
Your best next step: [one of:]
  → Continue /implement for FEAT-NNNN (Wave N in progress)
  → Start /feature for [roadmap item]
  → Run /triage (N unscored ideas in backlog)
  → Run /cleanup (feature just completed)
  → Tell me what you want to build (/idea)
```

# Architecture Docs

This folder holds the project's architecture documentation: how the system is organized, where to make changes, and how concepts connect. Five docs are referenced by the workflow skills — fill them in as the project grows.

## Naming

Default file/folder names below are conventions used by the workflow skills. **Use whatever naming your project prefers** — lowercase (`architecture.md`), CamelCase (`Architecture.md`), or a different folder (`documentation/architecture/`). If you rename anything, update the **Architecture Docs** section in `AGENTS.md` so the agent can locate the files.

## Bootstrap order

When the project is young, fill these in this order:

1. **ARCHITECTURE.md** — even one paragraph plus a module list is enough to start.
2. **MODULE_MAP.md** — once you have ≥2 modules.
3. **CONTEXT.md** — when terminology starts to drift.
4. **GLOSSARY.md** — when CONTEXT.md is too big to skim.
5. **ARCHITECTURE_REVIEW.md** — created by `/cleanup` when first triggered.

---

## ARCHITECTURE.md — the system in one screen

**Purpose:** anyone (developer or agent) should grasp the system from this file alone.

**Sections to write:**
- One-screen architecture (text diagram or short prose)
- Main modules (one line each — what each owns)
- **Dependency rule** — which modules may depend on which, and which must not
- Extension rule — how to add a new module or feature without breaking layering
- Architecture change rule — when an ADR is required

**Update when:** module boundaries, dependency rules, or extension contracts change.

---

## MODULE_MAP.md — change routing

**Purpose:** "if I want to change X, which module do I start in?" — answered in seconds.

**Sections to write:**
- Read order for agents new to the codebase
- Module ownership table — module → responsibility → public interface → test location
- Change routing table — concern → start in module
- Test routing — where tests for each module live

**Update when:** a new module is added, ownership shifts, or test layout changes.

---

## CONTEXT.md — shared language and domain rules

**Purpose:** ground truth for terminology so the agent and the developer use the same words.

**Sections to write:**
- Terms (term → definition → where it appears in code)
- Domain rules (invariants and business rules that hold across modules)
- Open terminology questions (anything still being argued)

**Update when:** a new term enters the codebase, an old one shifts meaning, or a domain rule is locked.

---

## GLOSSARY.md — fast lookup

**Purpose:** quick A-Z index of project-specific terms. Often a subset/index of `CONTEXT.md`. Optional if `CONTEXT.md` stays small.

**Sections to write:**
- Term → one-sentence definition → link to deeper context
- Anti-glossary — terms to avoid and what to use instead

**Update when:** terms are added, retired, or replaced.

---

## ARCHITECTURE_REVIEW.md — periodic cleanup output

**Purpose:** record of structural problems found by `/cleanup` and the refactor slices proposed.

**Sections to write** (the `/cleanup` skill generates this):
- Trigger (what caused the review)
- Confusion points
- Scattered concepts
- Dependency health
- Test health issues
- Proposed refactor slices
- Decision (proceed / park / reject)

**Update when:** `/cleanup` runs. Treat older reviews as history — do not edit in place; append a new dated section instead.

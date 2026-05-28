# Future Skill Ideas

Candidate skills to consider adding to this workflow. Parking lot — not committed work.

## `/bug` — First-class bug pipeline

**Problem:** today a one-line fix has to go through `/idea` → `/triage` → `/feature` (heavyweight), or it sneaks in unstructured. Neither serves the control/verification goal.

**Sketch:** report → write a reproducible test (must fail) → root-cause memo → fix slice (TDD) → regression suite stays green → MR.

**Artifacts:** `docs/bugs/BUG-NNNN-slug/{REPORT.md, REPRO_TEST.md, ROOT_CAUSE.md, FIX.md}`.

**Notes for hardware/embedded:** the repro test may require a specific hardware setup — capture that in `REPORT.md` so the test is portable across benches.

## `/spike` — Time-boxed exploration

**Problem:** `/feature` forces every unit through TDD. Exploratory work (protocol reverse-engineering, hardware bring-up, "is this even feasible?") doesn't fit, so it happens off-process and the learnings vanish.

**Sketch:** set a time box (default 4h); the agent explores on a throwaway branch (not the worktree); output is a `SPIKE.md` decision memo: **continue** / **abandon** / **promote to feature**.

**Artifacts:** `docs/spikes/SPIKE-NNNN-slug/SPIKE.md` plus a link to the exploratory branch (kept or deleted per decision).

**Notes for hardware/embedded:** especially valuable for bring-up, errata hunting, and new-peripheral evaluation — where you cannot write a TDD test until you know what the peripheral actually does.

## `/resume` — Pay off the HANDOFF investment

**Problem:** `/implement` writes `HANDOFF.md` after every wave so a developer can resume after a break, but the workflow has no dedicated resume skill. `/workflow`'s state detection partially covers it; `/onboard` is for new developers (too verbose for a returning one).

**Sketch:** read `docs/features/[active]/HANDOFF.md` → run the regression suite → surface any drift since the last wave → give one clear next action.

**Artifacts:** none new — this skill consumes existing `HANDOFF.md`.

**Why it fits:** makes `HANDOFF.md` a load-bearing artifact instead of a write-once relic.

## `/postmortem` — Capture durable lessons

**Problem:** when a feature ships (or an incident happens), the team learns things — but those lessons aren't reliably captured. Especially painful for hardware: errata, timing constraints, and integration gotchas rediscovered every project.

**Sketch:** walk the developer through what worked, what failed, what we'll do differently. Output appends to `docs/knowledge-base/` (durable lessons) and `RISK_LOG.md` (active risks).

**Artifacts:** `docs/postmortems/POSTMORTEM-NNNN-slug.md`.

**Notes for hardware/embedded:** the biggest win is here — hardware lessons are gold and rarely written down anywhere durable.

## `/release` — Cut a release

**Problem:** feature MRs ship continuously, but cutting an actual release (SemVer bump, changelog, tag, build, hardware-compatibility check for embedded) is currently informal.

**Sketch:** SemVer decision → `CHANGELOG.md` update from completed features since last tag → tag + push → build artifacts → hardware-compatibility matrix update if relevant.

**Artifacts:** updates `CHANGELOG.md`; creates a git tag.

**Caveat:** the most project-specific of these skills — depends on language ecosystem (cargo, pypi, npm, custom embedded toolchain). May belong as per-project customization rather than a one-size skill.

---

## Priority (subjective)

1. **`/bug`** — daily leverage; closes the biggest current gap.
2. **`/spike`** — high-value for the embedded/HAL domain.
3. **`/resume`** — small skill, big quality-of-life payoff.
4. **`/postmortem`** — most durable value over multi-year project life.
5. **`/release`** — useful but project-specific; may live as project customization.

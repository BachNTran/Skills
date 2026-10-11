---
title: modgate · requirements
version: 4
status: draft
approved:
---

# modgate · requirements

- **REQ-MG-001** (parents: FEAT-MG-001) — Text files hash as SHA-256 of UTF-8 with CRLF → LF, trailing whitespace stripped per line and exactly one final newline; binary files (non-UTF-8 or containing NUL) hash raw.
- **REQ-MG-002** (parents: FEAT-MG-001) — A markdown file hashes its body only: the YAML frontmatter is excluded.
- **REQ-MG-003** (parents: FEAT-MG-001) — The module hash is SHA-256 of the sorted `<path>\t<file-hash>` lines of the module's files, excluding nested child modules, `*.trace.md`, `*.changelog.md`, `*.activity.md` and agent context (`CLAUDE.md`, `.claude/`), followed by one `dep:<module>\t<module-hash>` line per dependency in the overview's `deps:`.
- **REQ-MG-004** (parents: FEAT-MG-002) — The project root is the nearest ancestor holding `modgate.yaml`; a module is a directory `X/` holding `X.md` whose frontmatter has `kind:`. Modules nest; a directory with its own `modgate.yaml` is a separate project and is skipped.
- **REQ-MG-005** (parents: FEAT-MG-006) — A module's criticality is its overview's `criticality:`, else its nearest ancestor module's, else the project's.
- **REQ-MG-006** (parents: FEAT-MG-003) — Requirements are top-level list items `- **REQ-XXX-###**` with optional `(parents: …)` and indented continuation lines; each has a section hash of its normalized text.
- **REQ-MG-007** (parents: FEAT-MG-002) — DRIFT is reported when a file bound to a REQ in `<m>.bind.yaml` differs from its hash at the last approval of that REQ or of the module while the REQ's section hash is unchanged. It clears when the REQ is revisited and approved, or by `approve <m> REQ-…`.
- **REQ-MG-008** (parents: FEAT-MG-002) — A file under the module's source folders (`sources:`, default `src`, `include`) bound to no REQ is UNBOUND; bindings to missing files or unknown REQs are BADBIND. A bound directory binds every file below it.
- **REQ-MG-009** (parents: FEAT-MG-003) — `sync` regenerates `<m>.trace.md`: a state header line, a FEAT → REQ → TC → per-target result matrix and a `modgate-state:` yaml block that is preserved across regenerations. An unchanged trace is not rewritten.
- **REQ-MG-010** (parents: FEAT-MG-003) — Test cases are found textually in `test/` and `tests/`: pytest `@pytest.mark.req(…)` or `REQ_XXX_###` in the test name, C++ `TEST(Suite, REQ_XXX_###_…)`, JS/TS `it("REQ-XXX-### …")`.
- **REQ-MG-011** (parents: FEAT-MG-004) — `sync --test <target>` runs the target's command from `modgate.yaml` in each module in scope that lists the target; on exit 0 it keeps only the latest passing record (module hash, result, date, environment, dependency hashes); on failure it reports TESTFAIL and keeps the previous record.
- **REQ-MG-012** (parents: FEAT-MG-005) — Generic doc names (README, CHANGELOG, NOTES, TODO, INDEX …) are violations except tool-mandated names; markdown in a module's `docs/` must be prefixed with the module name.
- **REQ-MG-013** (parents: FEAT-MG-005) — A folder with more than 8 visible entries is a finding, more than 12 a violation. Hidden entries and `modgate.yaml` do not count.
- **REQ-MG-014** (parents: FEAT-MG-005) — Changelog headings follow `### YYYY-MM-DD-xxxx · vN · <doc> · <author>` with unique IDs; inside git the HEAD version must be a prefix of the working copy (append-only), else a violation.
- **REQ-MG-015** (parents: FEAT-MG-006) — An `ai-reviewer:<model>` approval of a gate the module's criticality preset reserves for the developer is rejected by `approve` and reported as a violation by `sync`. Presets are overridable in `modgate.yaml`.
- **REQ-MG-016** (parents: FEAT-MG-006) — `approve <m> <doc|REQ|all> [--by]` sets `status: approved`, `approved: <version> sha256:<12hex>` and `approved_by`, records per-file, per-REQ and module hashes in the trace state and appends a changelog entry. The default approver is `git config user.name`.
- **REQ-MG-017** (parents: FEAT-MG-007) — `pending` prints one line per open item (CONFIG, DRAFT, DRIFT, STALE, DEPCHANGED, UNTESTED, UNBOUND, BACKLOG) grouped into dependency-disjoint module sets.
- **REQ-MG-018** (parents: FEAT-MG-007) — Findings print as `CODE  module  id  files  → next action`; exit 0 clean, 1 findings, 2 violations, 3 error; `--json` only when asked; `--strict` makes findings fail.
- **REQ-MG-019** (parents: FEAT-MG-007) — Hook modes: `sync --hook` on PostToolUse syncs only the edited file's module and returns findings as `additionalContext`; on Stop it exits 2 with violations on stderr (not when `stop_hook_active`); `pending --hook` returns the pending list as SessionStart `additionalContext`.
- **REQ-MG-020** (parents: FEAT-MG-003) — `pending --report` writes `.modgate/report.html` (module tree with kind, criticality, state, hash; trace matrices; open items) and prints its path.
- **REQ-MG-021** (parents: FEAT-MG-005) — A `docs/diagrams/*.drawio` newer than its `.svg` is exported with the `drawio` CLI; without the CLI it is one DRAWIO finding, never a failure.
- **REQ-MG-022** (parents: FEAT-MG-001) — File hashes are cached in `.modgate/cache.json` by path with mtime and size and recomputed only when those change.
- **REQ-MG-023** (parents: FEAT-MG-002) — States are computed: draft, unreviewed change, stale (unexplained changes since approval), dependency changed (ICD unchanged → a passing re-test re-baselines; ICD changed → deep review), approved untested, verified.
- **REQ-MG-024** (parents: FEAT-MG-008) — `install.sh <project>` installs the CLI (uv, else pipx, else a project venv + shim), copies the skill, merges hooks and the `ask` rule for `modgate approve` into `.claude/settings.json` without clobbering, seeds `modgate.yaml` and `.gitignore`; re-running changes nothing. `--no-cli` skips the CLI (already on PATH) and wires the hooks to plain `modgate`.
- **REQ-MG-025** (parents: FEAT-MG-008) — The kit ships a skill of at most 40 lines, one template per module kind (overview + docs) and the approved guideline.
- **REQ-MG-026** (parents: FEAT-MG-008) — modgate has no runtime dependencies: third-party code is vendored under `src/modgate/_vendor/` with its license, and declared as `vendor:` in `modgate.yaml` (hashed, exempt from SIZE and UNBOUND). `package.sh` builds `dist/modgate-kit-v<guideline>/` (installer, `claude/` instructions, one universal wheel), `dist/weather-station/` (the example with the kit really installed) and a zip of both; it installs offline.

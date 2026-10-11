# modgate · changelog

### 2026-09-27-7a1c · v1 · modgate.md · AI
- Created the tool module: brief (FEAT-MG-001…008), req (REQ-MG-001…025), ICD (CLI contract, hooks, presets), test plan, bindings. Implements guideline v5 §7 as a provisional first version. Awaiting approval.
### 2026-09-27-29ee · v2 · modgate.req.md · AI
- REQ-MG-025 now includes shipping the approved guideline; new REQ-MG-026: zero runtime dependencies (PyYAML vendored, `vendor:` paths hashed but exempt from SIZE/UNBOUND) and `package.sh` builds the portable offline zip. Why: the developer asked for a full portable package (2026-09-27). Awaiting approval.
### 2026-09-27-56df · v3 · modgate.req.md · AI
- REQ-MG-003: agent context (`CLAUDE.md`, `.claude/`) is not module content — excluded from hashing and folder counts. Why: adding the example's project CLAUDE.md made the root module STALE. Awaiting approval.
### 2026-09-27-e3c7 · v4 · modgate.req.md · AI
- REQ-MG-024: `--no-cli`. REQ-MG-026: deliverables are two plain directories — the kit (installer + Claude instructions + wheel) and the example project with the kit installed — plus a zip. Why: the developer wanted a kit directory and a real-looking example project, not the tool's dev repo. Awaiting approval.
### 2026-10-11-5d09 · v1 · kit · AI
- Added crew skill `svg-animation` (kit/crew/skills/svg-animation): nudge to visualize docs that explain something moving, with an optional stdlib generator (one SMIL timeline, playback bar, raw SVG). Replaces the same-day `svg-flow-animation`. No requirement change.

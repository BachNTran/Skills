# weather-station — project context for Claude

Example project (never deployed). How we build here: the **modgate** skill
(`.claude/skills/modgate/SKILL.md`, full guideline next to it). Follow it; this file only adds
what is specific to this project.

## Project
- Solar weather station: firmware (sensing → storage → comms) → backend (ingest → telemetry_db) → dashboard.
  Map and interactions: `weather-station.md`.
- Criticality **L2** (product); children inherit. Override: `firmware/sensing/study_adc_noise_floor` is L0.
- Coding standard: Google (C++, Python, TypeScript). Diagrams: Mermaid, inline in the doc they explain.
- Approver: `Example Dev`.

## Where things are
| Area | Path | Notes |
|---|---|---|
| Firmware | `firmware/` | C++17; ports in `firmware/ports/` (shared fakes in `hal_ports/fakes/`), adapters `hal_linux_sim`, `osal_posix` |
| Protocol | `protocol/` | `weather.v1.Reading` schema — the ICD between firmware and backend |
| Backend | `backend/` | Python ingest service + `telemetry_db` data module |
| Dashboard | `dashboard/` | TypeScript feature module |
| Deploy / host | `deploy/prod/`, `host/probe_access/` | runbook + secrets map (locations only) |

## Commands (the hooks already run `modgate pending` and `modgate sync`)
- Test targets (from `modgate.yaml`): `modgate sync <module> --test linux-sim` (needs `c++`),
  `--test host` (needs `python3` with pytest), `--test web` (needs node ≥ 23).
- Whole-project view: `modgate pending --report`.

## Project rules
- Firmware modules never call POSIX or a vendor SDK directly — only `hal_ports` / `osal_ports`.
- Anything crossing firmware ↔ backend goes through `protocol/` first (schema change = deep review of both sides).
- Timing constants (debounce, sample periods) live in the REQ and the ICD, never only in code.

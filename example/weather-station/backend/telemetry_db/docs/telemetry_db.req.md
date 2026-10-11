---
title: telemetry_db · requirements
version: 1
status: approved
approved: 1 sha256:941421728014
approved_by: Example Dev
---

# telemetry_db · requirements

- **REQ-TDB-001** (parents: FEAT-TDB-001) — Table `readings` has station_id, seq, timestamp_s, rh_tenths, battery_mv with primary key (station_id, seq).
- **REQ-TDB-002** (parents: FEAT-TDB-001) — Migrations are numbered 001, 002, … without gaps and apply in order on an empty database.

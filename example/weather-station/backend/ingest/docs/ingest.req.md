---
title: ingest · requirements
version: 1
status: approved
approved: 1 sha256:ac1c2338fdb8
approved_by: Example Dev
---

# ingest · requirements

- **REQ-ING-001** (parents: FEAT-ING-001, REQ-BE-001) — Decode a Reading; a truncated message or a missing field 1–4 is rejected with `DecodeError`.
- **REQ-ING-002** (parents: FEAT-ING-001, REQ-BE-001, REQ-BE-002) — Store each reading exactly once per (station_id, seq); duplicates from re-sent batches are ignored.
- **REQ-ING-003** (parents: FEAT-ING-001) — Reject readings time-stamped more than 5 min in the future.

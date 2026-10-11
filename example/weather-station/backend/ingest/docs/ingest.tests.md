---
title: ingest · test plan
version: 1
status: approved
approved: 1 sha256:13903667fb70
approved_by: Example Dev
---

# ingest · test plan

## Strategy
pytest on the host, REQ markers; the store test builds a SQLite database from telemetry_db's migrations.

## REQ → TC
| REQ | TC |
|---|---|
| REQ-ING-001 | test_decode.py |
| REQ-ING-002 | test_store.py |
| REQ-ING-003 | test_decode.py |

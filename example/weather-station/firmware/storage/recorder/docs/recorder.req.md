---
title: recorder · requirements
version: 1
status: approved
approved: 1 sha256:e81f9dd217a5
approved_by: Example Dev
---

# recorder · requirements

- **REQ-REC-001** (parents: FEAT-REC-001, REQ-STOR-001) — `stop()` flushes pending blocks, then refuses further writes.
- **REQ-REC-002** (parents: FEAT-REC-001, REQ-STOR-001) — At most 4 blocks are pending, so a stop completes within 200 ms (50 ms worst-case write).

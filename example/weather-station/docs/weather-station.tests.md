---
title: weather-station · test plan
version: 1
status: approved
approved: 1 sha256:c4260b86e284
approved_by: Example Dev
---

# weather-station · test plan

## Strategy
L2. End-to-end: the firmware on `linux-sim` uploads to a local backend; the dashboard shows the reading.
Not automated in this example (no target); the requirements are allocated to subsystems whose tests run.

## REQ → TC
| REQ | Allocated to | Proof |
|---|---|---|
| REQ-WS-001 | firmware REQ-FW-001/004, backend REQ-BE-001 | subsystem tests |
| REQ-WS-002 | firmware REQ-FW-003 | storage integration test |
| REQ-WS-003 | firmware REQ-FW-002 | battery_monitor + storage tests |

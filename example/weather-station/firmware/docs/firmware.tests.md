---
title: firmware · test plan
version: 1
status: approved
approved: 1 sha256:473d014f7bf3
approved_by: Example Dev
---

# firmware · test plan

## Strategy
Requirements are allocated to subsystems; each is proven by the owning module's tests on `linux-sim`.

## REQ → TC
| REQ | Allocated to |
|---|---|
| REQ-FW-001 | sensing REQ-SENS-001 |
| REQ-FW-002 | sensing REQ-SENS-002, storage REQ-STOR-001 |
| REQ-FW-003 | storage REQ-STOR-001 |
| REQ-FW-004 | comms REQ-COMMS-001 |

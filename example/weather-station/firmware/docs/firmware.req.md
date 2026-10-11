---
title: firmware · requirements
version: 1
status: approved
approved: 1 sha256:ef09dc314f10
approved_by: Example Dev
---

# firmware · requirements

- **REQ-FW-001** (parents: REQ-WS-001) — Sample humidity every 60 s ± 1 s.
- **REQ-FW-002** (parents: REQ-WS-003) — On LOW_BATTERY, stop recording within 200 ms.
- **REQ-FW-003** (parents: REQ-WS-002) — Stop recording before the SD card fills.
- **REQ-FW-004** (parents: REQ-WS-001) — Upload each reading as a `weather.v1.Reading`; queue up to 7 days while offline.

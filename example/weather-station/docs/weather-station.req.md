---
title: weather-station · requirements
version: 1
status: approved
approved: 1 sha256:01b0ded1ea62
approved_by: Example Dev
---

# weather-station · requirements

- **REQ-WS-001** (parents: FEAT-WS-001) — A reading is visible on the dashboard within 5 min of measurement while the station is online.
- **REQ-WS-002** (parents: FEAT-WS-001) — No reading is lost while the station is offline for up to 7 days.
- **REQ-WS-003** (parents: FEAT-WS-002) — Recorded data survives a brown-out: recording stops cleanly before power is lost.

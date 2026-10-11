---
title: battery_monitor · requirements
version: 1
status: approved
approved: 1 sha256:8a9671c518a6
approved_by: Example Dev
---

# battery_monitor · requirements

- **REQ-BATMON-001** (parents: FEAT-BATMON-001) — `sample()` reports the battery voltage in mV (ADC pin voltage × 2).
- **REQ-BATMON-002** (parents: FEAT-BATMON-002, REQ-SENS-002) — Raise LOW_BATTERY when the voltage stays below 3300 mV for 1 s; clear it when it recovers.

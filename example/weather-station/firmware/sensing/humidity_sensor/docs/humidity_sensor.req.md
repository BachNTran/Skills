---
title: humidity_sensor · requirements
version: 1
status: approved
approved: 1 sha256:ef921c21c80d
approved_by: Example Dev
---

# humidity_sensor · requirements

- **REQ-HUM-001** (parents: FEAT-HUM-001, REQ-SENS-001) — `read()` returns relative humidity in 0.1 %RH steps, clamped to 0–100 %.
- **REQ-HUM-002** (parents: FEAT-HUM-001, REQ-SENS-001) — A NACK or CRC-8 mismatch returns `valid = false`.

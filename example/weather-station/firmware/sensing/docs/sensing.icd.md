---
title: sensing · ICD
version: 1
status: approved
approved: 1 sha256:b0f8841a0783
approved_by: Example Dev
---

# sensing · ICD

## External interfaces
- `humidity_sensor::HumiditySensor::read()` → `Reading{valid, rh_tenths}`
- `battery_monitor::BatteryMonitor::low_battery()`

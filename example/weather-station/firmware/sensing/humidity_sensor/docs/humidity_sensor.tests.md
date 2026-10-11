---
title: humidity_sensor · test plan
version: 1
status: approved
approved: 1 sha256:762bd0c53f92
approved_by: Example Dev
---

# humidity_sensor · test plan

## Strategy
Unit tests on linux-sim with `FakeI2c` from `hal_ports/fakes`. Conversion: both clamps and one
mid-scale value; CRC: the datasheet vector.

## REQ → TC
| REQ | TC |
|---|---|
| REQ-HUM-001 | HumiditySensor.REQ_HUM_001_* |
| REQ-HUM-002 | HumiditySensor.REQ_HUM_002_* |

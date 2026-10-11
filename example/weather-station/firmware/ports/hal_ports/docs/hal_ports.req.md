---
title: hal_ports · requirements
version: 1
status: approved
approved: 1 sha256:fafb3b1de434
approved_by: Example Dev
---

# hal_ports · requirements

- **REQ-HAL-001** (parents: FEAT-HAL-001) — `hal::Adc` returns a pin voltage in mV; `FakeAdc` returns a settable value.
- **REQ-HAL-002** (parents: FEAT-HAL-001) — `hal::I2c` performs a write-then-read transfer and reports NACK; `FakeI2c` replays a scripted response.
- **REQ-HAL-003** (parents: FEAT-HAL-001) — `hal::BlockDevice` appends 512-byte blocks and reports capacity; `FakeBlockDevice` counts rejected writes.

---
title: humidity_sensor
kind: code
deps: [hal_ports]
targets: [linux-sim]
version: 1
status: approved
approved: 1 sha256:6405574368c7
approved_by: Example Dev
---

# humidity_sensor · code

Driver for an SHT4x-style I²C humidity sensor.

## Owns
Command sequence, CRC-8 check, raw → %RH conversion.
## Does NOT own
Sampling schedule (firmware task), I²C timing (adapter).

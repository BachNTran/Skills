---
title: battery_monitor
kind: code
deps: [hal_ports, osal_ports]
targets: [linux-sim]
version: 1
status: approved
approved: 1 sha256:cf427133513e
approved_by: Example Dev
---

# battery_monitor · code

Samples the battery through a 1:2 divider and warns before brown-out, early enough to save state.

## Owns
Scaling, brown-out debounce, LOW_BATTERY flag.
## Does NOT own
What happens on LOW_BATTERY (storage stops recording).

---
title: storage
kind: system
deps: [sd_storage, recorder]
targets: [linux-sim]
sources: [include, src]
version: 1
status: approved
approved: 1 sha256:629f316c80ca
approved_by: Example Dev
---

# storage · system

Storage subsystem. Shows **requirement decomposition**: the firmware rule "stop recording before
the SD card fills" is split into the part each child can own and test; the parent keeps the rule
that connects them (`StorageGuard`) and its integration test.

```mermaid
flowchart LR
  P["REQ-STOR-001<br/>stop recording before the card fills"] --> A["sd_storage<br/>REQ-SD-001 report free space<br/>REQ-SD-002 LOW_SPACE below 5 %"]
  P --> B["recorder<br/>REQ-REC-001 stop cleanly on command<br/>REQ-REC-002 ≤ 4 pending blocks (200 ms)"]
  P --> G["StorageGuard (this module)<br/>wires the two · integration test"]
```

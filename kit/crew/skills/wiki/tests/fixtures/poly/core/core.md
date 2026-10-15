---
title: core
kind: system
deps: []
version: 1
status: draft
---

# core · system

Native libraries: a C utility layer and C++ geometry on top of it.

## Subsystems and interactions
```mermaid
flowchart LR
  GEO["geo"] -- "uses util" --> C["c"]
```

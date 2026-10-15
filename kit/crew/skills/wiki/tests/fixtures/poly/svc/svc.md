---
title: svc
kind: system
deps: []
version: 1
status: draft
---

# svc · system

The service: a Python package writing samples into a SQL database.

## Subsystems and interactions
```mermaid
flowchart LR
  PKG["pkg"] -- "INSERT samples" --> DB[("db")]
```

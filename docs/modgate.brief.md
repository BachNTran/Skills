---
title: modgate · brief
version: 1
status: draft
approved:
---

# modgate · brief

Intent: the LLM drafts, the developer gates, and a small tool does every mechanical step, so that
"approved docs, code and the latest passing test carry the same hash" is a fact, not a hope.
For now the design is provisional: routines that make the LLM reliable. Small, tested core over breadth.

## Features

- **FEAT-MG-001** — Trustworthy hashes: files, docs and modules hash the same on every machine; approving never changes a hash.
- **FEAT-MG-002** — Know what changed: module states computed, never guessed; code changed without its requirement is caught.
- **FEAT-MG-003** — Traceability: FEAT → REQ → TC → test result per module, and one whole-project report.
- **FEAT-MG-004** — Test records: the latest passing run per target, tied to the module hash and its environment.
- **FEAT-MG-005** — Structure lint: naming, folder size, append-only changelogs, diagram export.
- **FEAT-MG-006** — Human gates: approval is a deliberate, recorded act; AI sign-off only where criticality allows.
- **FEAT-MG-007** — Run by hooks, token-lean: one line per finding, silent on success, pending list at session start.
- **FEAT-MG-008** — Installable kit: one command puts CLI, skill, hooks, permission rule and templates into a project.

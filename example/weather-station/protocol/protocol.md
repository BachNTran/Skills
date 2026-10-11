---
title: protocol
kind: protocol
deps: []
targets: [host]
sources: [weather.proto]
version: 1
status: approved
approved: 1 sha256:0a04e82c48bb
approved_by: Example Dev
---

# protocol · protocol

The station ↔ backend contract. Code for every side follows it: `firmware/comms` (encoder),
`backend/ingest` (decoder), `dashboard` (field names). Its hash is a dependency of each side,
so a schema change triggers review on all of them.

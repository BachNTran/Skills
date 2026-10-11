---
title: prod
kind: deploy
deps: [ingest, telemetry_db]
targets: []
sources: [compose.yaml, smoke-test.sh, config]
version: 1
status: approved
approved: 1 sha256:acb22bb31f0c
approved_by: Example Dev
---

# prod · deploy

Production deployment of the backend: one host, one container, SQLite on a volume — the smallest
thing that meets REQ-BE-001/002. Never actually deployed (example); no smoke-test target is defined.

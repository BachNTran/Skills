---
title: telemetry_db · test plan
version: 1
status: approved
approved: 1 sha256:e2c0176abb7a
approved_by: Example Dev
---

# telemetry_db · test plan

## Strategy
pytest applies all migrations to an in-memory SQLite database and inspects the schema.

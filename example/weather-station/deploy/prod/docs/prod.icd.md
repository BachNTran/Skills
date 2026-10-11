---
title: prod · ICD
version: 1
status: approved
approved: 1 sha256:d9299c96b805
approved_by: Example Dev
---

# prod · ICD

## Runbook
1. `docker compose -f compose.yaml up -d` on the host.
2. `sh smoke-test.sh https://weather.example.net`.
3. Backups: nightly `telemetry_db/backup.sh` via systemd timer.

## Environment config
`config/prod.env` (non-secret values only).

## Secrets map (locations only — never values)
| Secret | Lives in | Rotated by |
|---|---|---|
| TLS certificate + key | host: `/etc/letsencrypt/` (certbot) | certbot, automatic |
| Station upload token | docker secret `station_token` | developer, yearly |

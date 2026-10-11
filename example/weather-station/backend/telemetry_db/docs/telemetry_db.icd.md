---
title: telemetry_db · ICD
version: 1
status: approved
approved: 1 sha256:071af74ae20f
approved_by: Example Dev
---

# telemetry_db · ICD

## Schema
```sql
readings(station_id INTEGER, seq INTEGER, timestamp_s INTEGER, rh_tenths INTEGER, battery_mv INTEGER,
         PRIMARY KEY (station_id, seq))
```
## Migration contract
Forward-only files `migrations/NNN_name.sql`; never edit an applied migration.
## Backup and restore
`backup.sh <db> <dir>` uses SQLite's online backup; restore = copy the file back while stopped.

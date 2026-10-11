---
title: weather-station · ICD
version: 1
status: approved
approved: 1 sha256:f2c32f30ba64
approved_by: Example Dev
---

# weather-station · ICD

## External interfaces
| Interface | Direction | Protocol | Rate |
|---|---|---|---|
| Uplink | station → backend | `protocol` (weather.v1.Reading) over HTTPS POST | 1 reading / 60 s, batched when offline |
| Dashboard | backend → browser | HTTP JSON (read-only) | on demand |
| Debug | host → station | SWD via ST-Link (`probe_access`) | development only |

## Rates and budgets
Uplink ≤ 2 kB per hour per station. SD card: ≥ 7 days of readings at 60 s.

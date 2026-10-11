---
title: firmware · ICD
version: 1
status: approved
approved: 1 sha256:e4b313f53470
approved_by: Example Dev
---

# firmware · ICD

## External interfaces
- Uplink: `weather.v1.Reading` (see `protocol`), HTTPS POST `/v1/readings`.
- SD card: FAT32, one file per day, 512-byte blocks.

## Rates and budgets
Tick 100 ms (budget 5 ms). Measurement task 60 s (budget 50 ms incl. I²C).

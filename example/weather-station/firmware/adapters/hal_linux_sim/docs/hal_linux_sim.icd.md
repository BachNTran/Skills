---
title: hal_linux_sim · ICD
version: 1
status: approved
approved: 1 sha256:78f8ee5bc489
approved_by: Example Dev
---

# hal_linux_sim · ICD

## Port implemented
`hal::Adc` (from hal_ports) as `hal_linux_sim::FileAdc(path)`.
## Limits and deviations
No sampling noise; use recorded samples (study_adc_noise_floor) if noise matters.

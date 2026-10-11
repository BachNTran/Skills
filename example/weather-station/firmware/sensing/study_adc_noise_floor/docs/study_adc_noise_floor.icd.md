---
title: study_adc_noise_floor · ICD
version: 1
status: approved
approved: 1 sha256:0a2add78e545
approved_by: Example Dev
---

# study_adc_noise_floor · ICD

## Question
Is the battery channel quiet enough for a plain 3300 mV threshold with a 1 s debounce?
## Method
200 samples at 100 ms on the bench supply at 3.30 V (`data/samples.csv`, first 20 kept here);
`analysis/noise_floor.py` prints mean and σ.
## Findings
σ ≈ 4 mV, mean within 5 mV of the supply. A 1 s debounce (10 samples) is enough; no averaging filter.
## Distilled into
battery_monitor ICD (timing section).

---
title: battery_monitor · ICD
version: 1
status: approved
approved: 1 sha256:353c3c238916
approved_by: Example Dev
---

# battery_monitor · ICD

## Public API
```cpp
class BatteryMonitor {
 public:
  BatteryMonitor(hal::Adc& adc, osal::Clock& clock);
  void sample();                  // call every 100 ms
  uint32_t battery_mv() const;
  bool low_battery() const;
};
```
## Timing
`sample()` every 100 ms; LOW_BATTERY after 1 s continuously below 3300 mV
(study_adc_noise_floor: noise σ ≈ 4 mV, so no extra filtering needed at this threshold).

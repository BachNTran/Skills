---
title: humidity_sensor · ICD
version: 2
status: draft
approved: 1 sha256:35a707b40986
approved_by: Example Dev
---

# humidity_sensor · ICD

## Public API
```cpp
namespace humidity_sensor {
struct Reading { bool valid; uint16_t rh_tenths; };   // 0..1000 = 0.0..100.0 %RH
class HumiditySensor { public: explicit HumiditySensor(hal::I2c& bus); Reading read(); };
uint8_t crc8(const uint8_t* data, size_t len);        // poly 0x31, init 0xFF
}
```
## Behaviour
`read()` sends 0xFD to address 0x44 and reads 3 bytes: raw MSB, raw LSB, CRC.
## Errors
NACK or CRC mismatch → `valid = false`, `rh_tenths = 0`.
## Timing
`read()` blocks for the measurement: ≤ 10 ms (8.3 ms typical at high precision). Call it from the 60 s task, never from the 100 ms tick.

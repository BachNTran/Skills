#pragma once
#include <cstddef>
#include <cstdint>

#include "hal/i2c.hpp"

namespace humidity_sensor {

constexpr uint8_t kAddress = 0x44;
constexpr uint8_t kMeasureHighPrecision = 0xFD;

struct Reading {
  bool valid;
  uint16_t rh_tenths;  // 0..1000 = 0.0..100.0 %RH
};

// CRC-8, polynomial 0x31, init 0xFF (sensor datasheet).
uint8_t crc8(const uint8_t* data, size_t len);

class HumiditySensor {
 public:
  explicit HumiditySensor(hal::I2c& bus) : bus_(bus) {}
  Reading read();

 private:
  hal::I2c& bus_;
};

}  // namespace humidity_sensor

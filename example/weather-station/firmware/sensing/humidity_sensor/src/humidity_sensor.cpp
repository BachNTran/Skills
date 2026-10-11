#include "humidity_sensor/humidity_sensor.hpp"

namespace humidity_sensor {

uint8_t crc8(const uint8_t* data, size_t len) {
  uint8_t crc = 0xFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0x31) : static_cast<uint8_t>(crc << 1);
    }
  }
  return crc;
}

Reading HumiditySensor::read() {
  const uint8_t cmd = kMeasureHighPrecision;
  uint8_t rx[3] = {};
  if (!bus_.transfer(kAddress, &cmd, 1, rx, sizeof rx) || crc8(rx, 2) != rx[2]) {
    return {false, 0};
  }
  const int32_t raw = (rx[0] << 8) | rx[1];
  int32_t tenths = -60 + (1250 * raw) / 65535;  // RH = -6 + 125 * raw / 65535
  if (tenths < 0) tenths = 0;
  if (tenths > 1000) tenths = 1000;
  return {true, static_cast<uint16_t>(tenths)};
}

}  // namespace humidity_sensor

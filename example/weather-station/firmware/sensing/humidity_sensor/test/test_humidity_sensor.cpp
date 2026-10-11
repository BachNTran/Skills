#include <gtest/gtest.h>

#include "fake_i2c.hpp"
#include "humidity_sensor/humidity_sensor.hpp"

using humidity_sensor::HumiditySensor;
using humidity_sensor::crc8;

static void respond(FakeI2c& bus, uint8_t msb, uint8_t lsb) {
  const uint8_t raw[2] = {msb, lsb};
  bus.response = {msb, lsb, crc8(raw, 2)};
}

TEST(HumiditySensor, REQ_HUM_001_converts_raw_to_tenths_of_percent) {
  FakeI2c bus;
  respond(bus, 0x80, 0x00);
  HumiditySensor sensor{bus};
  const auto r = sensor.read();
  EXPECT_TRUE(r.valid);
  EXPECT_EQ(r.rh_tenths, 565);
  EXPECT_EQ(bus.last_addr, 0x44);
}

TEST(HumiditySensor, REQ_HUM_001_clamps_to_0_and_100_percent) {
  FakeI2c bus;
  HumiditySensor sensor{bus};
  respond(bus, 0x00, 0x00);
  EXPECT_EQ(sensor.read().rh_tenths, 0);
  respond(bus, 0xFF, 0xFF);
  EXPECT_EQ(sensor.read().rh_tenths, 1000);
}

TEST(HumiditySensor, REQ_HUM_002_crc_datasheet_vector) {
  const uint8_t data[2] = {0xBE, 0xEF};
  EXPECT_EQ(crc8(data, 2), 0x92);
}

TEST(HumiditySensor, REQ_HUM_002_crc_mismatch_or_nack_is_invalid) {
  FakeI2c bus;
  HumiditySensor sensor{bus};
  bus.response = {0x80, 0x00, 0x00};
  EXPECT_FALSE(sensor.read().valid);
  respond(bus, 0x80, 0x00);
  bus.nack = true;
  EXPECT_FALSE(sensor.read().valid);
}

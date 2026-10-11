#pragma once
#include <cstring>
#include <vector>

#include "hal/i2c.hpp"

// Test double for hal::I2c: replays a scripted response, records the last command.
struct FakeI2c : hal::I2c {
  bool transfer(uint8_t addr, const uint8_t* tx, size_t tx_len, uint8_t* rx, size_t rx_len) override {
    last_addr = addr;
    last_cmd.assign(tx, tx + tx_len);
    if (nack || response.size() < rx_len) return false;
    std::memcpy(rx, response.data(), rx_len);
    return true;
  }
  std::vector<uint8_t> response;
  std::vector<uint8_t> last_cmd;
  uint8_t last_addr = 0;
  bool nack = false;
};

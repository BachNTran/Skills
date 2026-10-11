#pragma once
#include <cstddef>
#include <cstdint>

namespace hal {

// Port: an I2C bus master.
class I2c {
 public:
  virtual ~I2c() = default;
  // Writes tx, then reads rx_len bytes from 7-bit address addr. Returns false on NACK.
  virtual bool transfer(uint8_t addr, const uint8_t* tx, size_t tx_len, uint8_t* rx, size_t rx_len) = 0;
};

}  // namespace hal

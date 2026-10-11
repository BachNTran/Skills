#pragma once
#include <cstdint>

namespace hal {

// Port: one ADC channel.
class Adc {
 public:
  virtual ~Adc() = default;
  // Pin voltage in millivolts.
  virtual uint32_t read_mv() = 0;
};

}  // namespace hal

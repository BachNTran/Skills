#pragma once
#include "hal/adc.hpp"

// Test double for hal::Adc: returns whatever the test sets.
struct FakeAdc : hal::Adc {
  explicit FakeAdc(uint32_t mv) : mv(mv) {}
  uint32_t read_mv() override { return mv; }
  uint32_t mv;
};

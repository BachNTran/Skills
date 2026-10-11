#pragma once
#include "osal/clock.hpp"

// Test double for osal::Clock: time moves only when the test says so.
struct FakeClock : osal::Clock {
  uint32_t now_ms() const override { return t; }
  void advance(uint32_t ms) { t += ms; }
  uint32_t t = 0;
};

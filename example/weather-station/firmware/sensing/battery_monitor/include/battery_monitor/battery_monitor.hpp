#pragma once
#include <cstdint>

#include "hal/adc.hpp"
#include "osal/clock.hpp"

namespace battery_monitor {

constexpr uint32_t kDividerRatio = 2;
constexpr uint32_t kLowBatteryMv = 3300;

class BatteryMonitor {
 public:
  BatteryMonitor(hal::Adc& adc, osal::Clock& clock) : adc_(adc), clock_(clock) {}
  // Call every 100 ms.
  void sample();
  uint32_t battery_mv() const { return mv_; }
  bool low_battery() const { return low_; }

 private:
  void update_brownout(uint32_t now_ms);
  hal::Adc& adc_;
  osal::Clock& clock_;
  uint32_t mv_ = 0;
  bool low_ = false;
  bool below_ = false;
  uint32_t below_since_ms_ = 0;
};

}  // namespace battery_monitor

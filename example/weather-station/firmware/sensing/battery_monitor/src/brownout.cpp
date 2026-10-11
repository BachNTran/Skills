#include "battery_monitor/battery_monitor.hpp"

namespace battery_monitor {

namespace {
constexpr uint32_t kDebounceMs = 2000;
}  // namespace

void BatteryMonitor::update_brownout(uint32_t now_ms) {
  if (mv_ >= kLowBatteryMv) {
    below_ = false;
    low_ = false;
    return;
  }
  if (!below_) {
    below_ = true;
    below_since_ms_ = now_ms;
  }
  if (now_ms - below_since_ms_ >= kDebounceMs) low_ = true;
}

}  // namespace battery_monitor

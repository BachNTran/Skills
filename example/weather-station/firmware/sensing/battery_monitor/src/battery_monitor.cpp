#include "battery_monitor/battery_monitor.hpp"

namespace battery_monitor {

void BatteryMonitor::sample() {
  mv_ = adc_.read_mv() * kDividerRatio;
  update_brownout(clock_.now_ms());
}

}  // namespace battery_monitor

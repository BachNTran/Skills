#include <gtest/gtest.h>

#include "battery_monitor/battery_monitor.hpp"
#include "fake_adc.hpp"
#include "fake_clock.hpp"

using battery_monitor::BatteryMonitor;

TEST(BatteryMonitor, REQ_BATMON_001_reports_battery_mv_through_divider) {
  FakeAdc adc{1850};
  FakeClock clock;
  BatteryMonitor mon{adc, clock};
  mon.sample();
  EXPECT_EQ(mon.battery_mv(), 3700u);
}

#include <gtest/gtest.h>

#include "battery_monitor/battery_monitor.hpp"
#include "fake_adc.hpp"
#include "fake_clock.hpp"

using battery_monitor::BatteryMonitor;

TEST(BatteryMonitor, REQ_BATMON_002_raises_low_battery_after_2s_below_3300mV) {
  FakeAdc adc{1600};  // 3200 mV
  FakeClock clock;
  BatteryMonitor mon{adc, clock};
  mon.sample();
  clock.advance(1900);
  mon.sample();
  EXPECT_FALSE(mon.low_battery());
  clock.advance(100);
  mon.sample();
  EXPECT_TRUE(mon.low_battery());
}

TEST(BatteryMonitor, REQ_BATMON_002_clears_when_voltage_recovers) {
  FakeAdc adc{1600};
  FakeClock clock;
  BatteryMonitor mon{adc, clock};
  mon.sample();
  clock.advance(2000);
  mon.sample();
  EXPECT_TRUE(mon.low_battery());
  adc.mv = 1700;  // 3400 mV
  mon.sample();
  EXPECT_FALSE(mon.low_battery());
}

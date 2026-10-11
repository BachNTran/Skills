#include <gtest/gtest.h>

#include "fake_block_device.hpp"
#include "sd_storage/sd_storage.hpp"

using sd_storage::SdStorage;

TEST(SdStorage, REQ_SD_001_reports_free_space_percent) {
  FakeBlockDevice dev{200, 50};
  EXPECT_EQ(SdStorage{dev}.free_percent(), 75u);
  dev.used = 200;
  EXPECT_EQ(SdStorage{dev}.free_percent(), 0u);
}

TEST(SdStorage, REQ_SD_002_raises_low_space_below_5_percent) {
  FakeBlockDevice dev{100, 95};
  SdStorage sd{dev};
  EXPECT_FALSE(sd.low_space());
  dev.used = 96;
  EXPECT_TRUE(sd.low_space());
}

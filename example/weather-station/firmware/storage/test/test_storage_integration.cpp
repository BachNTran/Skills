#include <gtest/gtest.h>

#include "fake_block_device.hpp"
#include "storage/storage_guard.hpp"

TEST(Storage, REQ_STOR_001_stops_recording_before_card_fills) {
  static const uint8_t block[hal::kBlockSize] = {};
  FakeBlockDevice dev{100, 90};
  sd_storage::SdStorage sd{dev};
  recorder::Recorder rec{dev};
  storage::StorageGuard guard{sd, rec};
  for (int tick = 0; tick < 50 && rec.recording(); ++tick) {
    rec.record(block, sizeof block);
    guard.tick();
  }
  EXPECT_FALSE(rec.recording());
  EXPECT_EQ(dev.rejected, 0u);
  EXPECT_TRUE(dev.used <= dev.blocks);
}

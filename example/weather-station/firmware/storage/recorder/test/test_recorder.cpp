#include <gtest/gtest.h>

#include "fake_block_device.hpp"
#include "recorder/recorder.hpp"

using recorder::Recorder;

static const uint8_t kBlock[hal::kBlockSize] = {};

TEST(Recorder, REQ_REC_001_stop_flushes_pending_and_refuses_writes) {
  FakeBlockDevice dev{100, 0};
  Recorder rec{dev};
  rec.record(kBlock, sizeof kBlock);
  rec.record(kBlock, sizeof kBlock);
  rec.stop();
  EXPECT_EQ(dev.used, 2u);
  EXPECT_EQ(rec.pending(), 0u);
  EXPECT_FALSE(rec.recording());
  EXPECT_FALSE(rec.record(kBlock, sizeof kBlock));
}

TEST(Recorder, REQ_REC_002_never_more_than_4_blocks_pending) {
  FakeBlockDevice dev{100, 0};
  Recorder rec{dev};
  for (int i = 0; i < 10; ++i) {
    rec.record(kBlock, sizeof kBlock);
    EXPECT_TRUE(rec.pending() <= recorder::kMaxPending);
  }
  EXPECT_EQ(dev.used, 6u);
}

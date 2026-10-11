#pragma once
#include "hal/block_device.hpp"

// Test double for hal::BlockDevice: counts blocks and rejected writes.
struct FakeBlockDevice : hal::BlockDevice {
  FakeBlockDevice(uint32_t blocks, uint32_t used) : blocks(blocks), used(used) {}
  uint32_t block_count() const override { return blocks; }
  uint32_t used_blocks() const override { return used; }
  bool append(const uint8_t*, size_t) override {
    if (used >= blocks) {
      ++rejected;
      return false;
    }
    ++used;
    return true;
  }
  uint32_t blocks;
  uint32_t used;
  uint32_t rejected = 0;
};

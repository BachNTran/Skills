#pragma once
#include <cstdint>

#include "hal/block_device.hpp"

namespace sd_storage {

constexpr uint32_t kLowSpacePercent = 5;

class SdStorage {
 public:
  explicit SdStorage(hal::BlockDevice& dev) : dev_(dev) {}
  uint32_t free_percent() const;
  bool low_space() const { return free_percent() < kLowSpacePercent; }

 private:
  hal::BlockDevice& dev_;
};

}  // namespace sd_storage

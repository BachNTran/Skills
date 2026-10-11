#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

#include "hal/block_device.hpp"

namespace recorder {

// 4 blocks x 50 ms worst-case SD append = 200 ms stop budget.
constexpr size_t kMaxPending = 4;

class Recorder {
 public:
  explicit Recorder(hal::BlockDevice& dev) : dev_(dev) {}
  bool record(const uint8_t* block, size_t len);
  void stop();
  bool recording() const { return recording_; }
  size_t pending() const { return pending_.size(); }

 private:
  void flush_one();
  hal::BlockDevice& dev_;
  std::vector<std::vector<uint8_t>> pending_;
  bool recording_ = true;
};

}  // namespace recorder

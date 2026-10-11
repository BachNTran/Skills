#pragma once
#include <cstddef>
#include <cstdint>

namespace hal {

constexpr size_t kBlockSize = 512;

// Port: an append-only block device (the SD card).
class BlockDevice {
 public:
  virtual ~BlockDevice() = default;
  virtual uint32_t block_count() const = 0;
  virtual uint32_t used_blocks() const = 0;
  // Appends one block. Returns false when the device is full or the write fails.
  virtual bool append(const uint8_t* data, size_t len) = 0;
};

}  // namespace hal

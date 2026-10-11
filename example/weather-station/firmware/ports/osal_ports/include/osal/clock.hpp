#pragma once
#include <cstdint>

namespace osal {

// Port: a monotonic millisecond clock.
class Clock {
 public:
  virtual ~Clock() = default;
  virtual uint32_t now_ms() const = 0;
};

}  // namespace osal

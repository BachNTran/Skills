#pragma once
#include "osal/clock.hpp"

namespace osal_posix {

class PosixClock : public osal::Clock {
 public:
  uint32_t now_ms() const override;
};

}  // namespace osal_posix

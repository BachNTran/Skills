#include "osal_posix/posix_clock.hpp"

#include <time.h>

namespace osal_posix {

uint32_t PosixClock::now_ms() const {
  timespec ts{};
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return static_cast<uint32_t>(ts.tv_sec * 1000u + ts.tv_nsec / 1000000);
}

}  // namespace osal_posix

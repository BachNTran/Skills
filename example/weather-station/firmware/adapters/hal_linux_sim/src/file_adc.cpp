#include "hal_linux_sim/file_adc.hpp"

#include <fstream>

namespace hal_linux_sim {

uint32_t FileAdc::read_mv() {
  std::ifstream in(path_);
  uint32_t mv = 0;
  in >> mv;
  return in ? mv : 0;
}

}  // namespace hal_linux_sim

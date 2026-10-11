#pragma once
#include <string>

#include "hal/adc.hpp"

namespace hal_linux_sim {

// hal::Adc for linux-sim: the millivolt value is read from a text file.
class FileAdc : public hal::Adc {
 public:
  explicit FileAdc(std::string path) : path_(std::move(path)) {}
  uint32_t read_mv() override;

 private:
  std::string path_;
};

}  // namespace hal_linux_sim

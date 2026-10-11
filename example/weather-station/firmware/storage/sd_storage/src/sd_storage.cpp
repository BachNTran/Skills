#include "sd_storage/sd_storage.hpp"

namespace sd_storage {

uint32_t SdStorage::free_percent() const {
  const uint32_t total = dev_.block_count();
  if (total == 0) return 0;
  return (total - dev_.used_blocks()) * 100 / total;
}

}  // namespace sd_storage

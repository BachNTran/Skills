#include "storage/storage_guard.hpp"

namespace storage {

void StorageGuard::tick() {
  if (rec_.recording() && sd_.low_space()) rec_.stop();
}

}  // namespace storage

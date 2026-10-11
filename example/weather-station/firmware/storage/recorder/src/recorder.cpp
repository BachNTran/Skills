#include "recorder/recorder.hpp"

namespace recorder {

bool Recorder::record(const uint8_t* block, size_t len) {
  if (!recording_) return false;
  if (pending_.size() == kMaxPending) flush_one();
  pending_.emplace_back(block, block + len);
  return true;
}

void Recorder::stop() {
  while (!pending_.empty()) flush_one();
  recording_ = false;
}

void Recorder::flush_one() {
  dev_.append(pending_.front().data(), pending_.front().size());
  pending_.erase(pending_.begin());
}

}  // namespace recorder

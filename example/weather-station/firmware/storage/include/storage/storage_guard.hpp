#pragma once
#include "recorder/recorder.hpp"
#include "sd_storage/sd_storage.hpp"

namespace storage {

// Wires sd_storage and recorder: stop recording before the card fills (REQ-STOR-001).
class StorageGuard {
 public:
  StorageGuard(sd_storage::SdStorage& sd, recorder::Recorder& rec) : sd_(sd), rec_(rec) {}
  void tick();

 private:
  sd_storage::SdStorage& sd_;
  recorder::Recorder& rec_;
};

}  // namespace storage

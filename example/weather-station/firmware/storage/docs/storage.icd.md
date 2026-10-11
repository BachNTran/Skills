---
title: storage · ICD
version: 1
status: approved
approved: 1 sha256:3bcc2fd0bc65
approved_by: Example Dev
---

# storage · ICD

## Public API
```cpp
class StorageGuard {
 public:
  StorageGuard(sd_storage::SdStorage& sd, recorder::Recorder& rec);
  void tick();   // call every 100 ms: stops the recorder on LOW_SPACE
};
```

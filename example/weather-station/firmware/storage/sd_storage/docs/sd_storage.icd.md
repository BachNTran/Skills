---
title: sd_storage · ICD
version: 1
status: approved
approved: 1 sha256:bde3ddec41c5
approved_by: Example Dev
---

# sd_storage · ICD

## Public API
```cpp
class SdStorage {
 public:
  explicit SdStorage(hal::BlockDevice& dev);
  uint32_t free_percent() const;
  bool low_space() const;   // free_percent() < 5
};
```

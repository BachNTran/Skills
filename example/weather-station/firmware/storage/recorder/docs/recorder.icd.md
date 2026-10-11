---
title: recorder · ICD
version: 1
status: approved
approved: 1 sha256:4123bd96f8d6
approved_by: Example Dev
---

# recorder · ICD

## Public API
```cpp
class Recorder {
 public:
  explicit Recorder(hal::BlockDevice& dev);
  bool record(const uint8_t* block, size_t len);   // false once stopped
  void stop();
  bool recording() const;
  size_t pending() const;
};
```
## Timing
Worst-case SD append 50 ms; ≤ 4 pending → stop ≤ 200 ms.

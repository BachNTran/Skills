---
title: ingest · ICD
version: 1
status: approved
approved: 1 sha256:11fd50d9c3f0
approved_by: Example Dev
---

# ingest · ICD

## Public API
```python
decode(data: bytes) -> dict            # raises DecodeError
validate(reading: dict, now_s: int)    # raises ValueError
Store(conn).add(reading) -> bool       # False if already stored
```

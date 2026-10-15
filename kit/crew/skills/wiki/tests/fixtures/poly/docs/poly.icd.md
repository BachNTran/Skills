---
title: poly · ICD
version: 1
status: draft
---

# poly · ICD

## External interfaces
| Interface | Direction | Format |
|---|---|---|
| `GET /v1/latest` | web → svc | JSON `demo.v1.Sample` |
| `Feed.Push` | svc → clients | protobuf `demo.v1.Sample` |

---
title: probe_access · ICD
version: 1
status: approved
approved: 1 sha256:2c2f3c5a0050
approved_by: Example Dev
---

# probe_access · ICD

## Guarantees to the host
The ST-Link V2/V3 (vendor 0483) is openable by the developer's user.
## Install and verify per OS
| OS | Install | Verify |
|---|---|---|
| Linux | `linux/install-linux.sh` | `lsusb -d 0483:` |
| macOS | — | `macos/verify-macos.sh` |
| Windows | TODO (vendor driver) | — |

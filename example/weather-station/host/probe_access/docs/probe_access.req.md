---
title: probe_access · requirements
version: 1
status: approved
approved: 1 sha256:8eb199b4481a
approved_by: Example Dev
---

# probe_access · requirements

- **REQ-PROBE-001** (parents: FEAT-PROBE-001) — Linux: after `install-linux.sh`, members of `plugdev` can open the ST-Link (udev rule).
- **REQ-PROBE-002** (parents: FEAT-PROBE-001) — macOS: `verify-macos.sh` confirms the probe enumerates (no driver needed).

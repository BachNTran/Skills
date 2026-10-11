---
title: probe_access
kind: host-service
criticality: L1
deps: []
targets: []
sources: [linux, macos]
version: 1
status: approved
approved: 1 sha256:ce17bbfdacb1
approved_by: Example Dev
---

# probe_access · host-service

Sets up what flashing and debug tools need on a developer machine: access to the ST-Link probe
without root. Internal tooling, so criticality L1 (override of the project's L2).

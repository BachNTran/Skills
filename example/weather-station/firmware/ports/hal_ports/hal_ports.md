---
title: hal_ports
kind: code
deps: []
targets: []
sources: [include, fakes]
version: 1
status: approved
approved: 1 sha256:1c78c88b8105
approved_by: Example Dev
---

# hal_ports · code

Hardware ports: what modules need from the hardware, as abstract interfaces. Ships `fakes/` —
test doubles any module can use (`FakeAdc`, `FakeI2c`, `FakeBlockDevice`).

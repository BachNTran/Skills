---
title: linux-sim
kind: system
deps: [hal_linux_sim, osal_posix]
targets: []
sources: [run-module-tests.sh, gtest_shim]
version: 1
status: approved
approved: 1 sha256:c2fe2ea0d994
approved_by: Example Dev
---

# linux-sim · system

Composition root: the firmware built natively for the developer's machine. OSAL → POSIX,
HAL → simulated peripherals (ADC from a file). Every module and subsystem test runs here.

## Simulated peripherals
| Peripheral | Simulation |
|---|---|
| ADC | `hal_linux_sim::FileAdc`: mV read from a file |
| Clock | `osal_posix::PosixClock` |
| I²C, SD | module tests use the fakes from `hal_ports` |

## Build
`run-module-tests.sh` is the `linux-sim` target in `modgate.yaml`: run in a module directory, it
compiles that module's `src/` (and its children's, for subsystem tests) with its tests and runs them.
Tests use the GoogleTest API; `gtest_shim/` is a tiny stand-in so the example needs no install.

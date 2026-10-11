#!/bin/sh
# macOS needs no driver: check that an ST-Link enumerates.
system_profiler SPUSBDataType | grep -q "STM32 STLink\|ST-LINK" && echo "probe found" || { echo "no probe" >&2; exit 1; }

---
title: storage · test plan
version: 1
status: approved
approved: 1 sha256:83dbf77e0dc8
approved_by: Example Dev
---

# storage · test plan

## Strategy
Integration test on linux-sim with the real children and `FakeBlockDevice`: fill a card to the
threshold and check the recorder stops before any write is rejected.

## REQ → TC
| REQ | TC |
|---|---|
| REQ-STOR-001 | Storage.REQ_STOR_001_stops_recording_before_card_fills |

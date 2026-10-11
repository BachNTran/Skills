---
title: comms
kind: code
deps: [protocol]
targets: []
version: 1
status: approved
approved: 1 sha256:684f4ee40009
approved_by: Example Dev
---

# comms · code

Encodes readings as `weather.v1.Reading` (protobuf wire format, hand-rolled: five varint fields)
for the uplink. Transport (HTTPS) is an adapter concern and not modelled in this example.

#pragma once
#include <cstdint>
#include <vector>

namespace comms {

struct Reading {
  uint32_t station_id;
  uint32_t seq;
  uint32_t timestamp_s;
  uint32_t rh_tenths;
  uint32_t battery_mv;
};

// weather.v1.Reading in protobuf wire format (fields 1-5, varint).
std::vector<uint8_t> encode_reading(const Reading& r);

}  // namespace comms

#include "comms/uplink.hpp"

namespace comms {

namespace {
void put_varint_field(std::vector<uint8_t>& out, uint32_t field, uint32_t value) {
  out.push_back(static_cast<uint8_t>(field << 3));  // wire type 0
  do {
    uint8_t byte = value & 0x7F;
    value >>= 7;
    out.push_back(value ? (byte | 0x80) : byte);
  } while (value);
}
}  // namespace

std::vector<uint8_t> encode_reading(const Reading& r) {
  std::vector<uint8_t> out;
  put_varint_field(out, 1, r.station_id);
  put_varint_field(out, 2, r.seq);
  put_varint_field(out, 3, r.timestamp_s);
  put_varint_field(out, 4, r.rh_tenths);
  put_varint_field(out, 5, r.battery_mv);
  return out;
}

}  // namespace comms

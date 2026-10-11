"""weather.v1.Reading wire decoding (varint fields only, as in the protocol module)."""

FIELDS = {1: "station_id", 2: "seq", 3: "timestamp_s", 4: "rh_tenths", 5: "battery_mv"}
REQUIRED = ("station_id", "seq", "timestamp_s", "rh_tenths")
MAX_FUTURE_S = 300


class DecodeError(ValueError):
    pass


def _varint(data: bytes, i: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if i >= len(data):
            raise DecodeError("truncated varint")
        byte = data[i]
        value |= (byte & 0x7F) << shift
        i += 1
        if not byte & 0x80:
            return value, i
        shift += 7


def decode(data: bytes) -> dict:
    out: dict = {}
    i = 0
    while i < len(data):
        key, i = _varint(data, i)
        field, wire = key >> 3, key & 7
        if wire != 0:
            raise DecodeError(f"unsupported wire type {wire}")
        value, i = _varint(data, i)
        if field in FIELDS:
            out[FIELDS[field]] = value
    missing = [f for f in REQUIRED if f not in out]
    if missing:
        raise DecodeError(f"missing fields: {', '.join(missing)}")
    return out


def validate(reading: dict, now_s: int) -> None:
    if reading["timestamp_s"] > now_s + MAX_FUTURE_S:
        raise ValueError("timestamp more than 5 min in the future")

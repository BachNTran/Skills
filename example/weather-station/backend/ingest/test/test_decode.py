import pytest

from ingest import DecodeError, decode, validate


def encode(**fields):
    """Mirror of firmware/comms encode_reading (protobuf varint fields)."""
    numbers = {"station_id": 1, "seq": 2, "timestamp_s": 3, "rh_tenths": 4, "battery_mv": 5}
    out = bytearray()
    for name, value in fields.items():
        out.append(numbers[name] << 3)
        while True:
            byte, value = value & 0x7F, value >> 7
            out.append(byte | (0x80 if value else 0))
            if not value:
                break
    return bytes(out)


READING = dict(station_id=7, seq=300, timestamp_s=1_790_000_000, rh_tenths=565, battery_mv=3700)


@pytest.mark.req("REQ-ING-001")
def test_decodes_all_fields():
    assert decode(encode(**READING)) == READING


@pytest.mark.req("REQ-ING-001")
def test_rejects_truncated_and_incomplete_messages():
    with pytest.raises(DecodeError):
        decode(encode(**READING)[:-1])
    with pytest.raises(DecodeError, match="rh_tenths"):
        decode(encode(station_id=7, seq=1, timestamp_s=5))


@pytest.mark.req("REQ-ING-003")
def test_rejects_future_timestamps():
    now = READING["timestamp_s"]
    validate(READING, now - 300)
    with pytest.raises(ValueError):
        validate(READING, now - 301)

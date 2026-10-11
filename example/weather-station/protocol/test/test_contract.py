import re
from pathlib import Path

import pytest

PROTO = Path(__file__).parents[1] / "weather.proto"
FROZEN = {"station_id": 1, "seq": 2, "timestamp_s": 3, "rh_tenths": 4, "battery_mv": 5}


def fields():
    text = PROTO.read_text()
    return {m[1]: int(m[2]) for m in re.findall(r"^\s*(uint32|int32|string|bytes)\s+(\w+)\s*=\s*(\d+);", text, re.M)}


@pytest.mark.req("REQ-PROTO-001")
def test_frozen_field_numbers():
    assert fields() == FROZEN


@pytest.mark.req("REQ-PROTO-001")
def test_reserved_numbers_not_reused():
    reserved = {int(n) for n in re.findall(r"reserved\s+(\d+);", PROTO.read_text())}
    assert reserved == {6}
    assert not reserved & set(fields().values())

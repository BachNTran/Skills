import re
import sqlite3
from pathlib import Path

import pytest

MIGRATIONS = sorted((Path(__file__).parents[1] / "migrations").glob("*.sql"))


def migrated():
    conn = sqlite3.connect(":memory:")
    for sql in MIGRATIONS:
        conn.executescript(sql.read_text())
    return conn


@pytest.mark.req("REQ-TDB-001")
def test_readings_schema():
    cols = [row[1] for row in migrated().execute("PRAGMA table_info(readings)")]
    assert cols == ["station_id", "seq", "timestamp_s", "rh_tenths", "battery_mv"]
    pk = [row[1] for row in migrated().execute("PRAGMA table_info(readings)") if row[5]]
    assert pk == ["station_id", "seq"]


@pytest.mark.req("REQ-TDB-002")
def test_migrations_numbered_without_gaps():
    numbers = [int(re.match(r"(\d{3})_", p.name).group(1)) for p in MIGRATIONS]
    assert numbers == list(range(1, len(numbers) + 1))

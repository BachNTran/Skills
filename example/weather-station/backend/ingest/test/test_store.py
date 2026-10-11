import sqlite3
from pathlib import Path

import pytest

from ingest import Store

MIGRATIONS = Path(__file__).parents[2] / "telemetry_db" / "migrations"  # the data module's ICD


@pytest.fixture
def store():
    conn = sqlite3.connect(":memory:")
    for sql in sorted(MIGRATIONS.glob("*.sql")):
        conn.executescript(sql.read_text())
    return Store(conn)


@pytest.mark.req("REQ-ING-002")
def test_each_reading_stored_once(store):
    r = dict(station_id=7, seq=1, timestamp_s=100, rh_tenths=500, battery_mv=3700)
    assert store.add(r) is True
    assert store.add(r) is False
    assert store.conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 1

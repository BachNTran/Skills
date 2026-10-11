"""Idempotent storage in the telemetry_db schema."""

import sqlite3


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, reading: dict) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO readings (station_id, seq, timestamp_s, rh_tenths, battery_mv)"
            " VALUES (:station_id, :seq, :timestamp_s, :rh_tenths, :battery_mv)",
            {"battery_mv": None, **reading},
        )
        self.conn.commit()
        return cur.rowcount == 1

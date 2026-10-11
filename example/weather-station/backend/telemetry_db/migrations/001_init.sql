CREATE TABLE readings (
  station_id  INTEGER NOT NULL,
  seq         INTEGER NOT NULL,
  timestamp_s INTEGER NOT NULL,
  rh_tenths   INTEGER NOT NULL,
  PRIMARY KEY (station_id, seq)
);

-- Samples written by pkg Store.add.
CREATE TABLE samples (
    station_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    value_mv INTEGER,
    ts_s INTEGER,
    PRIMARY KEY (station_id, seq)
);

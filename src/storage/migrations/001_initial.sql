-- Iter 2.2 initial schema: telemetry wide tablo + composite index (spec § 5, § 7).
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    sensor TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    state TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device_sensor_ts
    ON telemetry (device_id, sensor, timestamp);

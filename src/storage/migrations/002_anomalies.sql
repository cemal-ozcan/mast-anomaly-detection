-- Iter 4.1 anomalies tablosu: kural dedektörlerinin yazdığı anomaliler (spec § 5).
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    sensor TEXT NOT NULL,
    severity TEXT NOT NULL,
    score REAL NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    value REAL NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anomalies_device_created
    ON anomalies (device_id, created_at);

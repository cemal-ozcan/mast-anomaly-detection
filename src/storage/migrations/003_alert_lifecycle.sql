-- Iter 7.1 uyarı yaşam döngüsü: anomalies satırları yönetilebilir uyarı olur (spec § 5).
-- Version-gated (migrator schema_version ile bir kez uygular).
ALTER TABLE anomalies ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE anomalies ADD COLUMN acknowledged_at TEXT;
ALTER TABLE anomalies ADD COLUMN resolved_at TEXT;
CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies (status, created_at);

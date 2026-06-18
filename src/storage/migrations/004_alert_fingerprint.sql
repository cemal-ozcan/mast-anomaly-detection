-- Iter 8.5 reconciliation: rule_set = uyarının fingerprint'i (sıralı, virgülle birleştirilmiş
-- kural adları). DB-tek-hakikat reconciliation'da açık-uyarı kimliği. Nullable (legacy satır NULL).
ALTER TABLE anomalies ADD COLUMN rule_set TEXT;

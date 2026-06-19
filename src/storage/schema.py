"""SQLite telemetry şeması: SQLAlchemy Core Table + composite index (spec § 5, § 7).

Bu modül DDL ÇALIŞTIRMAZ (metadata.create_all() çağrılmaz). Yalnızca insert/select
expression builder olarak kullanılır. Runtime DDL'in tek kaynağı: migrations/001_initial.sql
(migrator.apply_migrations çalıştırır). schema.py Table ile 001_initial.sql arasındaki
tutarlılık migrated_engine fixture üzerinden çalışan repository testleriyle implicit doğrulanır.
"""
from __future__ import annotations

from sqlalchemy import REAL, Column, Index, Integer, MetaData, Table, Text

metadata = MetaData()

telemetry = Table(
    "telemetry",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("device_id", Text, nullable=False),
    Column("sensor", Text, nullable=False),
    Column("timestamp", Text, nullable=False),  # ISO 8601 ms (lexicographic sortable)
    Column("state", Text, nullable=False),
    Column("value", REAL, nullable=False),
    Column("unit", Text, nullable=False),
)

# Dedektörler (Faz 4+) "şu cihazın şu sensörünün son N örneği" sorgular (spec § 7).
idx_telemetry_device_sensor_ts = Index(
    "idx_telemetry_device_sensor_ts",
    telemetry.c.device_id,
    telemetry.c.sensor,
    telemetry.c.timestamp,
)

anomalies = Table(
    "anomalies",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("device_id", Text, nullable=False),
    Column("rule_name", Text, nullable=False),
    Column("sensor", Text, nullable=False),
    Column("severity", Text, nullable=False),
    Column("score", REAL, nullable=False),
    Column("window_start", Text, nullable=False),
    Column("window_end", Text, nullable=False),
    Column("value", REAL, nullable=False),
    Column("description", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("status", Text, nullable=False),  # active | acknowledged | resolved (migration 003)
    Column("acknowledged_at", Text),  # nullable
    Column("resolved_at", Text),  # nullable
    Column("rule_set", Text),  # nullable — fingerprint (sıralı virgül-bağlı kural adları, Iter 8.5)
    Column("clean_streak", Integer, nullable=False),  # Iter 8.7 deadband sayacı (DB DEFAULT 0, migration 005)
)

# Dashboard (Iter 4.3) + doğrulama "son anomaliler" sorgular (spec § 5).
idx_anomalies_device_created = Index(
    "idx_anomalies_device_created",
    anomalies.c.device_id,
    anomalies.c.created_at,
)

# Dashboard durum filtresi (Faz 7 Iter 7.1, spec § 5).
idx_anomalies_status = Index(
    "idx_anomalies_status",
    anomalies.c.status,
    anomalies.c.created_at,
)

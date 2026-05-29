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

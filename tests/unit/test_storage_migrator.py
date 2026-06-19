"""storage.migrator apply + idempotency testleri (Iter 2.2, spec § 9)."""
from __future__ import annotations

from sqlalchemy import Engine, text


def _table_names(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).all()
    return {row[0] for row in rows}


def test_apply_creates_telemetry_and_records_version(in_memory_engine: Engine) -> None:
    """Boş db → apply → telemetry + anomalies + schema_version tabloları var, version 1+2 kayıtlı."""
    from storage.migrator import MIGRATIONS_DIR, apply_migrations

    apply_migrations(in_memory_engine, MIGRATIONS_DIR)

    assert {"telemetry", "anomalies", "schema_version"} <= _table_names(in_memory_engine)
    with in_memory_engine.connect() as conn:
        versions = [r[0] for r in conn.execute(text("SELECT version FROM schema_version")).all()]
    assert versions == [1, 2, 3, 4, 5]


def test_apply_creates_composite_index(in_memory_engine: Engine) -> None:
    """001_initial.sql ikinci statement'ı (CREATE INDEX) de uygulanır (multi-statement split)."""
    from storage.migrator import MIGRATIONS_DIR, apply_migrations

    apply_migrations(in_memory_engine, MIGRATIONS_DIR)

    with in_memory_engine.connect() as conn:
        idx_rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        ).all()
    assert any(r[0] == "idx_telemetry_device_sensor_ts" for r in idx_rows)


def test_apply_is_idempotent(in_memory_engine: Engine) -> None:
    """İkinci apply no-op: schema_version satır sayısı 5 kalır (re-run güvenli, migration başına 1 satır)."""
    from storage.migrator import MIGRATIONS_DIR, apply_migrations

    apply_migrations(in_memory_engine, MIGRATIONS_DIR)
    apply_migrations(in_memory_engine, MIGRATIONS_DIR)

    with in_memory_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar_one()
    assert count == 5

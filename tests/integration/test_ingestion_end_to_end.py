"""Ingestion uçtan uca: handler → BatchWriter → SQLite (Iter 2.3, spec § 12 integration).

paho/run() loop'u değil; wired handler + BatchWriter + gerçek tmp_path dosya engine.
Bitti kriteri 1, 2, 4, 5 doğrulanır.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

from ingestion.__main__ import _make_message_handler
from ingestion.batch_writer import BatchWriter
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository


def _msg(device: str, sensor: str, ts: str, value: float) -> MagicMock:
    fake = MagicMock()
    fake.topic = f"telemetry/{device}/{sensor}"
    fake.payload = json.dumps({
        "device_id": device,
        "sensor": sensor,
        "timestamp": ts,
        "state": "raising",
        "value": value,
        "unit": "A",
    }).encode("utf-8")
    return fake


def test_n_messages_persist_with_order(tmp_path: Path) -> None:
    """100 mesaj handler'a fire → SQL'de 100 satır, fetch_recent DESC sıralı."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    apply_migrations(engine, MIGRATIONS_DIR)
    repo = TelemetryRepository(engine)
    shutdown = threading.Event()
    batch_writer = BatchWriter(
        repository=repo,
        shutdown_event=shutdown,
        max_size=200,
        flush_interval_s=60.0,
    )
    batch_writer.start()
    handler = _make_message_handler(batch_writer)

    try:
        for i in range(100):
            handler(_msg("device_001", "motor_current", f"2026-05-29T00:{i // 60:02d}:{i % 60:02d}.000Z", float(i)))

        batch_writer.stop()  # flushes remaining messages
        assert repo.count() == 100
        recent = repo.fetch_recent("device_001", "motor_current", limit=3)
        assert [r.value for r in recent] == [99.0, 98.0, 97.0]
    finally:
        engine.dispose()


def test_restart_reapplies_no_migration_and_appends(tmp_path: Path) -> None:
    """Servis restart: ikinci migration apply no-op, eski veri + yeni veri korunur (kriter 4, 5)."""
    from sqlalchemy import text

    db_path = tmp_path / "telemetry.db"

    # İlk "çalışma": 1 satır yaz.
    engine1 = create_sqlite_engine(db_path)
    apply_migrations(engine1, MIGRATIONS_DIR)
    repo1 = TelemetryRepository(engine1)
    shutdown1 = threading.Event()
    batch_writer1 = BatchWriter(
        repository=repo1,
        shutdown_event=shutdown1,
        max_size=200,
        flush_interval_s=60.0,
    )
    batch_writer1.start()
    handler1 = _make_message_handler(batch_writer1)
    handler1(_msg("device_001", "motor_current", "2026-05-29T00:00:00.000Z", 1.0))
    batch_writer1.stop()
    engine1.dispose()

    # İkinci "çalışma" (restart): aynı dosya, migration tekrar apply → no-op.
    engine2 = create_sqlite_engine(db_path)
    apply_migrations(engine2, MIGRATIONS_DIR)
    repo2 = TelemetryRepository(engine2)
    try:
        # Migration idempotent: schema_version hâlâ tek satır.
        with engine2.connect() as conn:
            sv = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar_one()
        assert sv == 1

        # Eski veri duruyor + yeni veri eklenir.
        assert repo2.count() == 1
        shutdown2 = threading.Event()
        batch_writer2 = BatchWriter(
            repository=repo2,
            shutdown_event=shutdown2,
            max_size=200,
            flush_interval_s=60.0,
        )
        batch_writer2.start()
        handler2 = _make_message_handler(batch_writer2)
        handler2(_msg("device_001", "motor_current", "2026-05-29T00:00:01.000Z", 2.0))
        batch_writer2.stop()
        assert repo2.count() == 2
    finally:
        engine2.dispose()

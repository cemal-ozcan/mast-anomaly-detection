"""BatchWriter + _should_flush testleri (Iter 2.3, spec § 8, § 11)."""
from __future__ import annotations

import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from ingestion.batch_writer import BatchWriter, _should_flush
from ingestion.message_parser import IngestedReading
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository


@pytest.fixture
def thread_safe_engine() -> Iterator[Engine]:
    """Thread-safe SQLite engine (file-based, NullPool).

    StaticPool paylaşımlı bağlantısı çok-thread yazma/okuma testlerinde
    SQLite lock yarışına yol açabilir. Dosya tabanlı + NullPool her
    connect() için ayrı bağlantı kullanır; thread güvenliğini SQLite
    kendi mutex'i ile sağlar.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        apply_migrations(engine, MIGRATIONS_DIR)
        try:
            yield engine
        finally:
            engine.dispose()


def _reading(value: float) -> IngestedReading:
    return IngestedReading(
        device_id="device_001",
        sensor="motor_current",
        timestamp=f"2026-05-29T00:00:{int(value) % 60:02d}.000Z",
        state="idle",
        value=value,
        unit="A",
    )


# ---- _should_flush saf logic ----

def test_should_flush_empty_buffer_never() -> None:
    assert _should_flush(0, now=100.0, last_flush=0.0, max_size=10, flush_interval_s=1.0) is False


def test_should_flush_size_threshold() -> None:
    assert _should_flush(10, now=0.0, last_flush=0.0, max_size=10, flush_interval_s=1000.0) is True


def test_should_flush_time_threshold() -> None:
    assert _should_flush(1, now=2.0, last_flush=0.0, max_size=1000, flush_interval_s=1.0) is True


def test_should_flush_neither() -> None:
    assert _should_flush(3, now=0.5, last_flush=0.0, max_size=10, flush_interval_s=1.0) is False


# ---- drainer: shutdown final flush drains queue (kriter 3) ----

def test_stop_flushes_all_queued_messages(thread_safe_engine: Engine) -> None:
    """50 mesaj enqueue + stop → final flush kuyruğu boşaltır, hepsi yazılır (kriter 3)."""
    repo = TelemetryRepository(thread_safe_engine)
    shutdown = threading.Event()
    writer = BatchWriter(repo, shutdown, max_size=1000, flush_interval_s=1000.0)
    writer.start()
    for i in range(50):
        writer.enqueue(_reading(float(i)))
    writer.stop()

    assert repo.count() == 50


def test_size_threshold_flushes_while_running(thread_safe_engine: Engine) -> None:
    """max_size dolunca çalışırken flush eder (final flush beklemeden)."""
    repo = TelemetryRepository(thread_safe_engine)
    shutdown = threading.Event()
    writer = BatchWriter(repo, shutdown, max_size=10, flush_interval_s=1000.0)
    writer.start()
    for i in range(10):
        writer.enqueue(_reading(float(i)))

    deadline = time.monotonic() + 3.0
    while repo.count() < 10 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert repo.count() == 10
    writer.stop()


# ---- _flush_with_retry: bounded retry + persistent fail ----

def test_flush_retries_then_succeeds() -> None:
    """İlk deneme OperationalError, ikinci başarılı → True, sleep bir kez çağrılır."""
    mock_repo = MagicMock(spec=TelemetryRepository)
    mock_repo.insert_batch.side_effect = [OperationalError("stmt", {}, Exception("locked")), None]
    repo = cast(TelemetryRepository, mock_repo)
    sleeps: list[float] = []
    shutdown = threading.Event()
    writer = BatchWriter(
        repo, shutdown, max_size=10, flush_interval_s=1.0,
        max_retries=3, retry_backoff_s=5.0, sleep=sleeps.append,
    )
    ok = writer._flush_with_retry([_reading(1.0)])
    assert ok is True
    assert len(sleeps) == 1
    assert writer.failed is False
    assert not shutdown.is_set()


def test_flush_persistent_failure_signals_shutdown() -> None:
    """Tüm denemeler başarısız → False, failed=True, shutdown set, sleep max_retries-1 kez."""
    mock_repo = MagicMock(spec=TelemetryRepository)
    mock_repo.insert_batch.side_effect = OperationalError("stmt", {}, Exception("disk full"))
    repo = cast(TelemetryRepository, mock_repo)
    sleeps: list[float] = []
    shutdown = threading.Event()
    writer = BatchWriter(
        repo, shutdown, max_size=10, flush_interval_s=1.0,
        max_retries=3, retry_backoff_s=5.0, sleep=sleeps.append,
    )
    ok = writer._flush_with_retry([_reading(1.0)])
    assert ok is False
    assert writer.failed is True
    assert shutdown.is_set()
    assert len(sleeps) == 2  # 3 deneme → 2 bekleme

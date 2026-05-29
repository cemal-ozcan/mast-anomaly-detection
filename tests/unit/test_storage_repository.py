"""storage.repository CRUD + index kullanımı testleri (Iter 2.2, spec § 3, § 7)."""
from __future__ import annotations

from sqlalchemy import Engine, text

from ingestion.message_parser import IngestedReading


def _reading(ts: str, value: float, sensor: str = "motor_current", device: str = "device_001") -> IngestedReading:
    return IngestedReading(
        device_id=device, sensor=sensor, timestamp=ts, state="idle", value=value, unit="A"
    )


def test_insert_then_count_and_fetch_roundtrip(migrated_engine: Engine) -> None:
    """insert sonrası count==1 ve fetch_recent aynı değeri döndürür (roundtrip)."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("2026-05-29T00:00:00.000Z", 1.5))

    assert repo.count() == 1
    rows = repo.fetch_recent("device_001", "motor_current", limit=5)
    assert len(rows) == 1
    assert rows[0].value == 1.5
    assert rows[0].device_id == "device_001"


def test_fetch_recent_orders_desc_and_limits(migrated_engine: Engine) -> None:
    """fetch_recent timestamp DESC sıralar ve limit uygular."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    for i in range(5):
        repo.insert(_reading(f"2026-05-29T00:00:{i:02d}.000Z", float(i)))

    rows = repo.fetch_recent("device_001", "motor_current", limit=3)
    assert [r.value for r in rows] == [4.0, 3.0, 2.0]  # en yeni 3, DESC


def test_fetch_recent_filters_by_device_and_sensor(migrated_engine: Engine) -> None:
    """fetch_recent yalnızca eşleşen device_id + sensor satırlarını döndürür."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("2026-05-29T00:00:00.000Z", 1.0, sensor="motor_current"))
    repo.insert(_reading("2026-05-29T00:00:01.000Z", 2.0, sensor="vibration"))
    repo.insert(_reading("2026-05-29T00:00:02.000Z", 3.0, device="device_002"))

    rows = repo.fetch_recent("device_001", "motor_current", limit=10)
    assert len(rows) == 1
    assert rows[0].value == 1.0


def test_fetch_recent_query_uses_composite_index(migrated_engine: Engine) -> None:
    """EXPLAIN QUERY PLAN composite index'i kullanır (bitti kriteri 3)."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    for i in range(10):
        repo.insert(_reading(f"2026-05-29T00:00:{i:02d}.000Z", float(i)))

    with migrated_engine.connect() as conn:
        plan = conn.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT * FROM telemetry "
                "WHERE device_id='device_001' AND sensor='motor_current' "
                "ORDER BY timestamp DESC LIMIT 5"
            )
        ).all()
    detail = " ".join(str(row[-1]) for row in plan)
    assert "USING INDEX idx_telemetry_device_sensor_ts" in detail, detail


def test_insert_batch_writes_all_rows(migrated_engine: Engine) -> None:
    """insert_batch tüm satırları tek transaction'da yazar."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    batch = [_reading(f"2026-05-29T00:00:{i:02d}.000Z", float(i)) for i in range(5)]
    repo.insert_batch(batch)

    assert repo.count() == 5
    rows = repo.fetch_recent("device_001", "motor_current", limit=2)
    assert [r.value for r in rows] == [4.0, 3.0]


def test_insert_batch_empty_is_noop(migrated_engine: Engine) -> None:
    """Boş liste → hiçbir şey yazılmaz, hata fırlamaz."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert_batch([])
    assert repo.count() == 0

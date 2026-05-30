"""storage.repository anomalies yazma/okuma (Faz 4 Iter 4.1, spec § 5)."""
from __future__ import annotations

from sqlalchemy import Engine, text

from detectors.base import Anomaly
from storage.repository import TelemetryRepository


def _anomaly(
    *,
    device_id: str = "device_001",
    rule_name: str = "motor_temperature_high",
    score: float = 0.9,
    value: float = 92.0,
    window_end: str = "2026-05-30T00:01:00.000Z",
) -> Anomaly:
    return Anomaly(
        device_id=device_id,
        rule_name=rule_name,
        sensor="motor_temperature",
        severity="critical",
        score=score,
        window_start="2026-05-30T00:00:00.000Z",
        window_end=window_end,
        value=value,
        description="test anomali",
    )


def test_insert_anomaly_then_fetch_roundtrip(migrated_engine: Engine) -> None:
    """insert_anomaly sonrası fetch_recent_anomalies aynı alanları döndürür."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anomaly(value=92.0), created_at="2026-05-30T00:01:00.500Z")

    rows = repo.fetch_recent_anomalies(limit=10)
    assert len(rows) == 1
    assert rows[0].device_id == "device_001"
    assert rows[0].rule_name == "motor_temperature_high"
    assert rows[0].sensor == "motor_temperature"
    assert rows[0].severity == "critical"
    assert rows[0].value == 92.0
    assert rows[0].score == 0.9


def test_fetch_recent_anomalies_orders_by_created_desc_and_limits(
    migrated_engine: Engine,
) -> None:
    """fetch_recent_anomalies created_at DESC sıralar ve limit uygular."""
    repo = TelemetryRepository(migrated_engine)
    for i in range(5):
        repo.insert_anomaly(
            _anomaly(value=float(i)),
            created_at=f"2026-05-30T00:0{i}:00.000Z",
        )

    rows = repo.fetch_recent_anomalies(limit=3)
    assert [r.value for r in rows] == [4.0, 3.0, 2.0]  # en yeni created_at 3 tanesi


def test_fetch_recent_anomalies_empty(migrated_engine: Engine) -> None:
    """Boş tablo → boş liste."""
    repo = TelemetryRepository(migrated_engine)
    assert repo.fetch_recent_anomalies(limit=10) == []


def test_anomalies_table_has_device_created_index(migrated_engine: Engine) -> None:
    """002 migration index'i oluşturuldu (sqlite_master ile doğrula)."""
    with migrated_engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index'")
            ).all()
        }
    assert "idx_anomalies_device_created" in names

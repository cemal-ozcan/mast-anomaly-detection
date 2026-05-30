"""Integration: telemetry seed → build_window + detect → insert_anomaly → fetch (Faz 4 Iter 4.1).

tmp file-based SQLite (gerçek 001 + 002 migration). Iter 4.1 'bitti' kriteri: bir cihazın
motor_temperature eşiği aşınca anomali DB'ye yazılır ve geri okunur.
"""
from __future__ import annotations

from pathlib import Path

from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.service import SENSORS, build_window
from ingestion.message_parser import IngestedReading
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository


def _reading(sensor: str, ts: str, value: float) -> IngestedReading:
    return IngestedReading(
        device_id="device_001", sensor=sensor, timestamp=ts, state="holding",
        value=value, unit="celsius",
    )


def test_overtemp_seed_produces_persisted_anomaly(tmp_path: Path) -> None:
    """Eşik üstü motor_temperature seed → tek tur tespit → anomalies tablosunda satır."""
    db_path = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)

        # Eşik üstü sıcaklık serisi seed et (tepe 95°C, eşik 80°C).
        for i, temp in enumerate([78.0, 88.0, 95.0]):
            repo.insert(_reading("motor_temperature", f"2026-05-30T00:00:0{i}.000Z", temp))

        # Tek tur: pencere kur → detect → persist.
        window = build_window(repo, "device_001", SENSORS, since=None)
        rule = MotorTemperatureHigh(critical_threshold_c=80.0)
        anomalies = rule.detect(window)
        assert len(anomalies) == 1
        repo.insert_anomaly(anomalies[0], created_at="2026-05-30T00:00:03.000Z")

        stored = repo.fetch_recent_anomalies(limit=10)
        assert len(stored) == 1
        assert stored[0].device_id == "device_001"
        assert stored[0].rule_name == "motor_temperature_high"
        assert stored[0].value == 95.0
    finally:
        engine.dispose()


def test_normal_temp_seed_produces_no_anomaly(tmp_path: Path) -> None:
    """Eşik altı sıcaklık → anomalies tablosu boş (FP yok)."""
    db_path = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        for i, temp in enumerate([24.0, 25.0, 26.0]):
            repo.insert(_reading("motor_temperature", f"2026-05-30T00:00:0{i}.000Z", temp))

        window = build_window(repo, "device_001", SENSORS, since=None)
        rule = MotorTemperatureHigh(critical_threshold_c=80.0)
        for anomaly in rule.detect(window):
            repo.insert_anomaly(anomaly, created_at="2026-05-30T00:00:03.000Z")

        assert repo.fetch_recent_anomalies(limit=10) == []
    finally:
        engine.dispose()

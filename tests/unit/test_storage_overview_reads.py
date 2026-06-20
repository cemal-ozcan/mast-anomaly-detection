"""Açılış (Operasyon Merkezi) için salt-okuma repository metodları."""
from __future__ import annotations

from sqlalchemy import Engine

from detectors.base import Anomaly
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository


def _reading(ts: str) -> IngestedReading:
    return IngestedReading("device_001", "motor_current", ts, "idle", 1.0, "A")


def _anomaly() -> Anomaly:
    return Anomaly("device_001", "motor_current_high", "motor_current", "high", 0.5,
                   "2026-06-20T11:59:00.000Z", "2026-06-20T12:00:00.000Z", 10.0, "d")


def test_earliest_telemetry_timestamp(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    assert repo.earliest_telemetry_timestamp() is None
    repo.insert(_reading("2026-06-20T10:00:00.000Z"))
    repo.insert(_reading("2026-06-20T09:00:00.000Z"))
    assert repo.earliest_telemetry_timestamp() == "2026-06-20T09:00:00.000Z"


def test_fetch_recent_for_device(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    assert repo.fetch_recent_for_device("device_001", 10) == []
    repo.insert(IngestedReading("device_001", "motor_current", "2026-06-20T10:00:00.000Z",
                                "idle", 1.0, "A"))
    repo.insert(IngestedReading("device_001", "vibration", "2026-06-20T10:00:01.000Z",
                                "idle", 0.05, "g"))
    repo.insert(IngestedReading("device_002", "motor_current", "2026-06-20T10:00:02.000Z",
                                "idle", 2.0, "A"))
    rows = repo.fetch_recent_for_device("device_001", 10)
    assert len(rows) == 2  # yalnız device_001, tüm sensörler
    assert rows[0].timestamp == "2026-06-20T10:00:01.000Z"  # en yeni üstte (DESC)
    assert {r.sensor for r in rows} == {"motor_current", "vibration"}
    assert len(repo.fetch_recent_for_device("device_001", 1)) == 1  # limit


def test_count_anomalies_since(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    assert repo.count_anomalies_since("2026-06-20T00:00:00.000Z") == 0
    repo.insert_anomaly(_anomaly(), "2026-06-20T12:00:00.000Z", "motor_current_high")
    repo.insert_anomaly(_anomaly(), "2026-06-19T12:00:00.000Z", "motor_current_high")
    assert repo.count_anomalies_since("2026-06-20T00:00:00.000Z") == 1

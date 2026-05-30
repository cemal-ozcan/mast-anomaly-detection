"""service.build_window saf helper testi (Faz 4 Iter 4.1, spec § 7)."""
from __future__ import annotations

from sqlalchemy import Engine

from detectors.service import SENSORS, build_window
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository


def _reading(sensor: str, ts: str, value: float, device: str = "device_001") -> IngestedReading:
    return IngestedReading(
        device_id=device, sensor=sensor, timestamp=ts, state="holding", value=value, unit="x"
    )


def test_build_window_long_format_columns(migrated_engine: Engine) -> None:
    """Pencere [device_id, timestamp, sensor, state, value] kolonlarıyla kurulur."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))
    repo.insert(_reading("motor_current", "2026-05-30T00:00:00.000Z", 0.5))

    frame = build_window(repo, "device_001", SENSORS, since=None)

    assert list(frame.columns) == ["device_id", "timestamp", "sensor", "state", "value"]
    assert set(frame["sensor"]) == {"motor_temperature", "motor_current"}
    assert len(frame) == 2


def test_build_window_filters_by_device(migrated_engine: Engine) -> None:
    """Yalnız istenen cihazın satırları gelir."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0, device="device_001"))
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 99.0, device="device_002"))

    frame = build_window(repo, "device_001", SENSORS, since=None)
    assert list(frame["value"]) == [25.0]


def test_build_window_empty_device_returns_empty_frame(migrated_engine: Engine) -> None:
    """Veri olmayan cihaz → 0 satır ama doğru-şemalı DataFrame."""
    repo = TelemetryRepository(migrated_engine)
    frame = build_window(repo, "device_404", SENSORS, since=None)
    assert list(frame.columns) == ["device_id", "timestamp", "sensor", "state", "value"]
    assert len(frame) == 0

"""service._detect_once dedup + per-rule error-swallow testi (Faz 4 Iter 4.1, spec § 8)."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine

from detectors.base import Anomaly, Detector
from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.service import _detect_once
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository

# Cutoff'u geçmişte bırakıp seed edilen 2026 timestamp'lerinin tümünü pencereye almak için.
_BIG_WINDOW_S = 1_000_000_000
_NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)


def _temp_reading(ts: str, value: float, device: str = "device_001") -> IngestedReading:
    return IngestedReading(
        device_id=device, sensor="motor_temperature", timestamp=ts, state="holding",
        value=value, unit="celsius",
    )


class _FailingDetector(Detector):
    """detect() her zaman ValueError fırlatır — error-swallow davranışını test eder."""

    @property
    def name(self) -> str:
        return "always_fails"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        raise ValueError("kasıtlı test hatası")


def test_detect_once_persists_anomaly_over_threshold(migrated_engine: Engine) -> None:
    """Eşik üstü sıcaklık → bir tur sonrası anomalies tablosunda satır + seen güncellenir."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_temp_reading("2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    seen: set[tuple[str, str, str]] = set()

    _detect_once(repo, detectors, _BIG_WINDOW_S, seen, _NOW)

    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1
    assert stored[0].value == 95.0
    assert len(seen) == 1


def test_detect_once_dedups_repeated_runs(migrated_engine: Engine) -> None:
    """Aynı pencerede iki ardışık tur → anomali yalnız bir kez yazılır (seen dedup)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_temp_reading("2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    seen: set[tuple[str, str, str]] = set()

    _detect_once(repo, detectors, _BIG_WINDOW_S, seen, _NOW)
    _detect_once(repo, detectors, _BIG_WINDOW_S, seen, _NOW)

    assert len(repo.fetch_recent_anomalies(limit=10)) == 1


def test_detect_once_below_threshold_writes_nothing(migrated_engine: Engine) -> None:
    """Eşik altı sıcaklık → hiçbir anomali yazılmaz, seen boş kalır."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_temp_reading("2026-05-30T00:00:00.000Z", 25.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    seen: set[tuple[str, str, str]] = set()

    _detect_once(repo, detectors, _BIG_WINDOW_S, seen, _NOW)

    assert repo.fetch_recent_anomalies(limit=10) == []
    assert seen == set()


def test_detect_once_failing_rule_does_not_block_others(migrated_engine: Engine) -> None:
    """Bir kural ValueError fırlatsa bile diğer kurallar çalışır + servis çökmez (spec § 8)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_temp_reading("2026-05-30T00:00:00.000Z", 95.0))
    # Bozuk kural ÖNCE; sağlam kural sonra — bozuk olan turu durdurmamalı.
    detectors: list[Detector] = [
        _FailingDetector(),
        MotorTemperatureHigh(critical_threshold_c=80.0),
    ]
    seen: set[tuple[str, str, str]] = set()

    _detect_once(repo, detectors, _BIG_WINDOW_S, seen, _NOW)  # exception fırlamamalı

    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1
    assert stored[0].rule_name == "motor_temperature_high"

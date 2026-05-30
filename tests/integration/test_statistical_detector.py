"""Integration: uzun pencere → ThreeSigma tespit → fusion → anomalies (Faz 5 Iter 5.1).

Servis _detect_once iki-pencere yolu: kural (kısa) + istatistik (uzun) anomalileri aynı
cihazda birleşir → tek fused satır. Statistical dedektör on-the-fly rolling baseline'dan
güncel sapmayı yakalar.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from detectors.base import Detector
from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.service import _detect_once
from detectors.statistical.three_sigma import ThreeSigma
from ingestion.message_parser import IngestedReading
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository

_BIG_WINDOW_S = 1_000_000_000


def _reading(sensor: str, ts: str, value: float, state: str = "holding") -> IngestedReading:
    return IngestedReading(
        device_id="device_001", sensor=sensor, timestamp=ts, state=state, value=value, unit="x"
    )


def test_three_sigma_detects_and_fuses_with_rule(tmp_path: Path) -> None:
    """Geçmiş normal motor_current baseline + sapan güncel tail → three_sigma; temp_high ile fused(2)."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        # Baseline: 40 normal HOLDING motor_current (~0.5±0.08, varyanslı) geçmişte.
        for i in range(40):
            v = 0.5 + 0.1 * ((i % 3) - 1)
            repo.insert(_reading("motor_current", f"2026-05-30T11:{i:02d}:00.000Z", v))
        # Güncel tail: 6 yüksek motor_current (~2.0) son 60s içinde.
        for i in range(6):
            repo.insert(_reading("motor_current", f"2026-05-30T12:00:{i:02d}.000Z", 2.0))
        # Aynı turda bir kural da tetiklensin: motor_temperature 95°C (güncel).
        repo.insert(_reading("motor_temperature", "2026-05-30T12:00:03.000Z", 95.0))

        rule_detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
        stat_detectors: list[Detector] = [
            ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
        ]
        groups: list[tuple[list[Detector], int]] = [
            (rule_detectors, _BIG_WINDOW_S),
            (stat_detectors, _BIG_WINDOW_S),
        ]
        active: dict[str, frozenset[str]] = {}
        _detect_once(repo, groups, active, datetime(2026, 5, 30, 12, 0, 10, tzinfo=UTC))

        stored = repo.fetch_recent_anomalies(limit=10)
        assert len(stored) == 1
        assert stored[0].rule_name == "fused(2)"
        assert "three_sigma:motor_current" in stored[0].description
        assert "motor_temperature_high" in stored[0].description
    finally:
        engine.dispose()


def test_three_sigma_no_fire_on_normal_current(tmp_path: Path) -> None:
    """Güncel tail baseline'a yakınsa istatistik tetiklemez (FP yok)."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        for i in range(40):
            v = 0.5 + 0.1 * ((i % 3) - 1)
            repo.insert(_reading("motor_current", f"2026-05-30T11:{i:02d}:00.000Z", v))
        for i in range(6):
            repo.insert(_reading("motor_current", f"2026-05-30T12:00:{i:02d}.000Z", 0.5))

        stat_detectors: list[Detector] = [
            ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
        ]
        active: dict[str, frozenset[str]] = {}
        _detect_once(repo, [(stat_detectors, _BIG_WINDOW_S)], active, datetime(2026, 5, 30, 12, 0, 10, tzinfo=UTC))

        assert repo.fetch_recent_anomalies(limit=10) == []
    finally:
        engine.dispose()

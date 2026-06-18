"""service._detect_once cihaz-seviyesi reconciliation: in-place update + skor refresh + eskalasyon
+ severity banttan + re-activate (Faz 8 Iter 8.6, spec § 4-7)."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine, text

from alerts.models import Alert
from detectors.base import Anomaly, Detector
from detectors.config import SeverityBands
from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.rules.motor_voltage_erratic import MotorVoltageErratic
from detectors.service import _detect_once
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository

_BIG_WINDOW_S = 1_000_000_000
_NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
_BANDS = SeverityBands(high_cutoff=0.40, critical_cutoff=0.75)


def _reading(sensor: str, ts: str, value: float, state: str = "holding", device: str = "device_001") -> IngestedReading:
    return IngestedReading(device_id=device, sensor=sensor, timestamp=ts, state=state, value=value, unit="x")


def _temp_detectors() -> list[Detector]:
    # warn=80, trip=130 → band(95)=0.30 warning, band(100)=0.40 high, band(120)=0.80 critical.
    return [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]


def _active(repo: TelemetryRepository) -> list[Alert]:
    return repo.fetch_alerts(("active", "acknowledged"), limit=20)


class _FailingDetector(Detector):
    @property
    def name(self) -> str:
        return "always_fails"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        raise ValueError("kasıtlı test hatası")


def test_first_detection_inserts_one(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1 and stored[0].rule_name == "motor_temperature_high"
    assert stored[0].severity == "warning"  # band(95)=0.30 → türetilmiş


def test_refreshes_score_and_severity_in_place(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 100.0))  # band 0.40 → high
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    a1 = _active(repo)
    assert len(a1) == 1 and a1[0].severity == "high"
    first_id = a1[0].id

    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 120.0 WHERE sensor='motor_temperature'"))  # band 0.80
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)

    a2 = _active(repo)
    assert len(a2) == 1 and a2[0].id == first_id  # AYNI satır (yeni değil)
    assert a2[0].severity == "critical" and a2[0].value == 120.0  # refresh (donma yok)


def test_escalation_updates_in_place_single_row(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [
        MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0),
        MotorVoltageErratic(std_threshold_v=1.0, min_samples=10, trip_std_v=5.0),
    ]
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW, _BANDS)
    assert len(_active(repo)) == 1  # yalnız sıcaklık

    for i, v in enumerate([24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]):
        repo.insert(_reading("motor_voltage", f"2026-05-30T00:01:{i:02d}.000Z", v))
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW, _BANDS)

    open_now = _active(repo)
    assert len(open_now) == 1  # eskalasyon AYNI satırda (yeni satır yok)
    assert open_now[0].rule_name == "fused(2)"


def test_auto_resolves_on_clear(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 25.0 WHERE sensor='motor_temperature'"))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    assert _active(repo) == []
    assert len(repo.fetch_alerts(("resolved",), limit=10)) == 1


def test_resolves_preexisting_open_on_clean_device(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))  # temiz
    repo.insert_anomaly(
        Anomaly(device_id="device_001", rule_name="x", sensor="s", severity="warning", score=0.1,
                window_start="a", window_end="b", value=1.0, description="d"),
        "2026-05-30T00:00:00.000Z", "x")
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    assert _active(repo) == []


def test_restart_persisting_fault_updates_no_duplicate(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    repo.insert_anomaly(
        Anomaly(device_id="device_001", rule_name="motor_temperature_high", sensor="motor_temperature",
                severity="critical", score=0.5, window_start="a", window_end="b", value=95.0, description="d"),
        "2026-05-30T00:00:00.000Z", "motor_temperature_high")
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)  # soğuk başlangıç
    assert len(repo.fetch_recent_anomalies(limit=10)) == 1  # duplikat değil → update


def test_converges_legacy_multiple_open(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    for ts, rs in [("2026-05-30T00:00:00.000Z", "a"), ("2026-05-30T00:00:01.000Z", "b")]:  # iki açık (legacy)
        repo.insert_anomaly(
            Anomaly(device_id="device_001", rule_name=rs, sensor="s", severity="warning", score=0.1,
                    window_start="a", window_end="b", value=1.0, description="d"), ts, rs)
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    assert len(_active(repo)) == 1  # biri güncellendi, fazlalık resolve
    assert len(repo.fetch_alerts(("resolved",), limit=10)) == 1


def test_reactivates_acknowledged_on_escalation(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 100.0))  # band 0.40 high
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    alert_id = _active(repo)[0].id
    repo.acknowledge_alert(alert_id, "2026-05-30T00:00:30.000Z")

    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 125.0 WHERE sensor='motor_temperature'"))  # band 0.90 critical
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)

    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "active" and a.acknowledged_at is None and a.severity == "critical"


def test_keeps_acknowledged_within_band(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 100.0))  # high
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    repo.acknowledge_alert(_active(repo)[0].id, "2026-05-30T00:00:30.000Z")
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)  # aynı değer → band değişmez
    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "acknowledged" and a.acknowledged_at == "2026-05-30T00:00:30.000Z"


def test_below_threshold_writes_nothing(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    assert repo.fetch_recent_anomalies(limit=10) == [] and _active(repo) == []


def test_failing_rule_does_not_block_others(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    _detect_once(repo, [([_FailingDetector(), *_temp_detectors()], _BIG_WINDOW_S)], _NOW, _BANDS)
    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1 and stored[0].rule_name == "motor_temperature_high"

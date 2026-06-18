"""F + E imza testleri (Faz 8 Iter 8.3, spec § 10). Engine harness senaryoyu koşturur."""
from __future__ import annotations

import pytest

from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.rules.sensor_out_of_range import SensorOutOfRange
from tests.scenarios.conftest import FIXTURES, CountingClock, build_detector_window

# Demo ile aynı geniş fiziksel-imkânsızlık sınırları (spec § 6a / plan kalibrasyonu).
_BOUNDS = {
    "motor_current": [-5.0, 30.0],
    "motor_voltage": [-100.0, 100.0],
    "hydraulic_pressure": [-10.0, 400.0],
    "motor_temperature": [-20.0, 160.0],
    "mast_position": [-50.0, 12000.0],
    "vibration": [-1.0, 10.0],
}


def test_temperature_overshoot_triggers_motor_temperature_high(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """F penceresi motor_temperature_high'ı (eşik 95°C) tetikler."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_temperature_overshoot.yaml", max_iterations=300,
    )
    rule = MotorTemperatureHigh(critical_threshold_c=95.0, trip_c=130.0)
    assert len(rule.detect(window)) == 1


def test_temperature_overshoot_not_out_of_range(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """F'in yüksek sıcaklığı sensor_out_of_range'i tetiklemez (160 sınırının altında)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_temperature_overshoot.yaml", max_iterations=300,
    )
    rule = SensorOutOfRange(bounds=_BOUNDS)
    assert rule.detect(window) == []


def test_sensor_fault_triggers_out_of_range(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """E penceresi sensor_out_of_range'i (mast_position) tetikler."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_sensor_fault.yaml", max_iterations=300,
    )
    anomalies = SensorOutOfRange(bounds=_BOUNDS).detect(window)
    assert len(anomalies) >= 1
    assert all(a.sensor == "mast_position" for a in anomalies)


def test_sensor_fault_not_temperature_high(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """E sıcaklık kuralını tetiklemez (yalnız mast_position bozuk)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_sensor_fault.yaml", max_iterations=300,
    )
    assert MotorTemperatureHigh(critical_threshold_c=95.0, trip_c=130.0).detect(window) == []


def test_clean_baseline_no_iter83_rules(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """Clean cihaz ne temp_high ne out_of_range tetikler (FP yok)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_clean_baseline.yaml", max_iterations=300,
    )
    assert MotorTemperatureHigh(critical_threshold_c=95.0, trip_c=130.0).detect(window) == []
    assert SensorOutOfRange(bounds=_BOUNDS).detect(window) == []

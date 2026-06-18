"""MotorCurrentHigh birim testi (Faz 4 Iter 4.2, spec § 6 — A, eşik+süre)."""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly
from detectors.rules.motor_current_high import MotorCurrentHigh


def _window(values: list[float], state: str = "raising", sensor: str = "motor_current") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:00:{i:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": [state] * len(values),
            "value": values,
        }
    )


def test_triggers_when_raising_mean_above_threshold() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=11.0)
    window = _window([10.0] * 12)  # RAISING ort. 10.0 > 9.0, 12 ≥ 10 örnek
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert isinstance(a, Anomaly)
    assert a.rule_name == "motor_current_high"
    assert a.sensor == "motor_current"
    assert a.device_id == "device_001"
    assert a.value == 10.0  # pencere ortalaması
    assert a.severity == "warning"  # default
    assert 0.0 <= a.score <= 1.0


def test_severity_is_configurable() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=11.0, severity="high")
    assert rule.detect(_window([10.0] * 12))[0].severity == "high"


def test_no_trigger_when_mean_below_threshold() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=11.0)
    assert rule.detect(_window([8.0] * 12)) == []  # clean RAISING ~8.0


def test_no_trigger_when_too_few_samples() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=11.0)
    assert rule.detect(_window([10.0] * 5)) == []  # 5 < 10, süre koşulu sağlanmaz


def test_ignores_other_states_and_sensors() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=11.0)
    assert rule.detect(_window([10.0] * 12, state="holding")) == []
    assert rule.detect(_window([10.0] * 12, sensor="vibration")) == []


def test_empty_window_returns_empty() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=11.0)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []


def test_trip_not_greater_than_warn_raises() -> None:
    """trip_a <= threshold_a → ValueError (band tanımsız, Iter 8.4)."""
    import pytest

    with pytest.raises(ValueError):
        MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=9.0)


def test_score_is_band_position() -> None:
    """RAISING ort=10, warn=9, trip=11 → band-pozisyon 0.5 (Iter 8.4 spec § 3)."""
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=11.0)
    assert rule.detect(_window([10.0] * 12))[0].score == 0.5

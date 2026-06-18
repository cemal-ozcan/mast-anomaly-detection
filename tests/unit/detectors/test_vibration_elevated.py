"""VibrationElevated birim testi (Faz 4 Iter 4.2, spec § 6 — A, oran)."""
from __future__ import annotations

import pandas as pd

from detectors.rules.vibration_elevated import VibrationElevated


def _window(values: list[float], state: str = "raising", sensor: str = "vibration") -> pd.DataFrame:
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
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10, trip_g=0.50)
    anomalies = rule.detect(_window([0.45] * 12))  # MechanicalWear ~0.45
    assert len(anomalies) == 1
    assert anomalies[0].rule_name == "vibration_elevated"
    assert anomalies[0].sensor == "vibration"
    assert anomalies[0].value == 0.45
    assert anomalies[0].severity == "warning"


def test_no_trigger_when_below_threshold() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10, trip_g=0.50)
    assert rule.detect(_window([0.30] * 12)) == []  # clean RAISING ~0.30


def test_no_trigger_too_few_samples() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10, trip_g=0.50)
    assert rule.detect(_window([0.45] * 5)) == []


def test_ignores_other_states() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10, trip_g=0.50)
    assert rule.detect(_window([0.45] * 12, state="holding")) == []


def test_empty_window_returns_empty() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10, trip_g=0.50)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []


def test_trip_not_greater_than_warn_raises() -> None:
    """trip_g <= threshold_g → ValueError (band tanımsız, Iter 8.4)."""
    import pytest

    with pytest.raises(ValueError):
        VibrationElevated(state="raising", threshold_g=0.37, min_samples=10, trip_g=0.37)


def test_score_is_band_position() -> None:
    """RAISING ort=0.435, warn=0.37, trip=0.50 → band-pozisyon 0.5 (Iter 8.4 spec § 3)."""
    import pytest

    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10, trip_g=0.50)
    assert rule.detect(_window([0.435] * 12))[0].score == pytest.approx(0.5)

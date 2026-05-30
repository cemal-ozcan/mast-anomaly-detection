"""MotorVoltageErratic birim testi (Faz 4 Iter 4.2, spec § 6 — C, varyans)."""
from __future__ import annotations

import pandas as pd

from detectors.rules.motor_voltage_erratic import MotorVoltageErratic


def _window(values: list[float], sensor: str = "motor_voltage") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:00:{i:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": ["holding"] * len(values),
            "value": values,
        }
    )


def test_triggers_on_high_variance() -> None:
    # ElectricalFault: spike'lar + jitter → yüksek std. 24 etrafında ±20 salınım.
    values = [24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    anomalies = rule.detect(_window(values))
    assert len(anomalies) == 1
    assert anomalies[0].rule_name == "motor_voltage_erratic"
    assert anomalies[0].sensor == "motor_voltage"
    assert anomalies[0].value > 1.0  # std
    assert anomalies[0].severity == "warning"


def test_no_trigger_on_stable_voltage() -> None:
    # Clean: 24V ± 0.2 gürültü → std ~0.2 < 1.0.
    values = [24.0, 24.2, 23.8, 24.1, 23.9, 24.0, 24.2, 23.8, 24.1, 23.9, 24.0, 24.1]
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert rule.detect(_window(values)) == []


def test_no_trigger_too_few_samples() -> None:
    values = [24.0, 4.0, 44.0, 24.0, -3.0]
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert rule.detect(_window(values)) == []


def test_ignores_other_sensors() -> None:
    values = [24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert rule.detect(_window(values, sensor="motor_current")) == []


def test_empty_window_returns_empty() -> None:
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []

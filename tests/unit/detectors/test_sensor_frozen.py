"""SensorFrozen birim testi (Faz 4 Iter 4.2, spec § 6 — E universal, süre).

Simülatör donmuş sensör üretmez → yalnız sentetik birim test ile doğrulanır.
"""
from __future__ import annotations

import pandas as pd

from detectors.rules.sensor_frozen import SensorFrozen


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


def test_triggers_when_value_frozen() -> None:
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    anomalies = rule.detect(_window([24.0] * 20))  # son 20 örnek aynı → donmuş
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_name == "sensor_frozen"
    assert a.sensor == "motor_voltage"
    assert a.value == 24.0  # donmuş değer
    assert a.severity == "warning"


def test_no_trigger_when_varying() -> None:
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    values = [24.0 + (i % 2) * 0.2 for i in range(20)]  # gürültülü → aralık 0.2 > ε
    assert rule.detect(_window(values)) == []


def test_uses_only_last_min_samples() -> None:
    # İlk örnekler değişken ama SON 20 sabit → donmuş (kayan pencere kuyruğu).
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    values = [20.0, 21.0, 22.0] + [24.0] * 20
    assert len(rule.detect(_window(values))) == 1


def test_no_trigger_too_few_samples() -> None:
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    assert rule.detect(_window([24.0] * 10)) == []


def test_ignores_other_sensors() -> None:
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    assert rule.detect(_window([24.0] * 20, sensor="motor_current")) == []

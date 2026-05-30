"""MotorTemperatureHigh kuralı birim testi (Faz 4 Iter 4.1, spec § 6 — F universal)."""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly
from detectors.rules.motor_temperature_high import MotorTemperatureHigh


def _window(values: list[float], sensor: str = "motor_temperature") -> pd.DataFrame:
    """Tek-cihaz uzun-format pencere kurar (device_id, timestamp, sensor, state, value)."""
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:00:{i:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": ["holding"] * len(values),
            "value": values,
        }
    )


def test_name_is_rule_key() -> None:
    """name property registry anahtarıyla aynı."""
    assert MotorTemperatureHigh(critical_threshold_c=80.0).name == "motor_temperature_high"


def test_triggers_when_peak_exceeds_threshold() -> None:
    """Tepe sıcaklık eşiği aşınca tek Anomaly döner; alanları doğru."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    window = _window([70.0, 85.0, 92.0, 60.0])

    anomalies = rule.detect(window)

    assert len(anomalies) == 1
    a = anomalies[0]
    assert isinstance(a, Anomaly)
    assert a.device_id == "device_001"
    assert a.rule_name == "motor_temperature_high"
    assert a.sensor == "motor_temperature"
    assert a.severity == "critical"
    assert a.value == 92.0  # tepe değer
    assert a.window_start == "2026-05-30T00:00:00.000Z"
    assert a.window_end == "2026-05-30T00:00:03.000Z"
    assert 0.0 <= a.score <= 1.0


def test_no_trigger_when_below_threshold() -> None:
    """Tüm değerler eşik altındaysa boş liste."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    assert rule.detect(_window([60.0, 70.0, 79.9])) == []


def test_boundary_equal_threshold_does_not_trigger() -> None:
    """Eşiğe eşit değer tetiklemez (strict >)."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    assert rule.detect(_window([80.0, 80.0])) == []


def test_ignores_other_sensors() -> None:
    """Yalnız motor_temperature satırlarına bakar; başka sensör eşiği geçse bile yok sayar."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    window = _window([200.0, 300.0], sensor="motor_current")
    assert rule.detect(window) == []


def test_empty_window_returns_empty() -> None:
    """Boş pencere → boş liste (KeyError yok)."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []


def test_severity_is_configurable() -> None:
    """severity constructor ile override edilebilir (config-driven, spec § 5)."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0, severity="warning")
    window = pd.DataFrame(
        {
            "device_id": ["device_001"],
            "timestamp": ["2026-05-30T00:00:00.000Z"],
            "sensor": ["motor_temperature"],
            "state": ["holding"],
            "value": [95.0],
        }
    )
    assert rule.detect(window)[0].severity == "warning"

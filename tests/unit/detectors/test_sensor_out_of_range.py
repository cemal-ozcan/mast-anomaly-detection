"""SensorOutOfRange kuralı birim testleri (Faz 8 Iter 8.3 spec § 6a)."""
from __future__ import annotations

import pandas as pd

_BOUNDS = {
    "motor_voltage": [-100.0, 100.0],
    "mast_position": [-50.0, 12000.0],
}


def _window(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """rows: (sensor, timestamp, value). device_id sabit."""
    return pd.DataFrame(
        {
            "device_id": ["dev"] * len(rows),
            "sensor": [r[0] for r in rows],
            "timestamp": [r[1] for r in rows],
            "state": ["raising"] * len(rows),
            "value": [r[2] for r in rows],
        }
    )


def test_in_range_no_anomaly() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("mast_position", "t1", 3000.0), ("motor_voltage", "t2", 24.0)])
    assert rule.detect(window) == []


def test_out_of_range_below_triggers() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("mast_position", "t1", 3000.0), ("mast_position", "t2", -500.0)])
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_name == "sensor_out_of_range"
    assert a.sensor == "mast_position"
    assert a.value == -500.0
    assert a.severity == "high"
    assert 0.0 < a.score <= 1.0


def test_out_of_range_above_triggers() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("motor_voltage", "t1", 250.0)])  # > 100
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    assert anomalies[0].sensor == "motor_voltage"


def test_multiple_sensors_each_emit() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("mast_position", "t1", -500.0), ("motor_voltage", "t2", 999.0)])
    sensors = {a.sensor for a in rule.detect(window)}
    assert sensors == {"mast_position", "motor_voltage"}


def test_empty_window() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    assert rule.detect(pd.DataFrame()) == []


def test_score_is_one_binary_validity() -> None:
    """Sensör-sağlığı = ikili 'veri geçersiz' → skor sabit 1.0 (band-pozisyon değil, Iter 8.4 spec § 5)."""
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("mast_position", "t1", -500.0)])
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    assert anomalies[0].score == 1.0


def test_registered() -> None:
    from detectors.rules import RULE_REGISTRY

    assert "sensor_out_of_range" in RULE_REGISTRY

"""detectors.base: Anomaly dataclass + Detector ABC kontratı (Faz 4 Iter 4.1, spec § 5)."""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from detectors.base import Anomaly, Detector


def _anomaly(**overrides: object) -> Anomaly:
    base: dict[str, object] = {
        "device_id": "device_001",
        "rule_name": "motor_temperature_high",
        "sensor": "motor_temperature",
        "severity": "critical",
        "score": 0.9,
        "window_start": "2026-05-30T00:00:00.000Z",
        "window_end": "2026-05-30T00:01:00.000Z",
        "value": 92.0,
        "description": "motor_temperature 92.0°C eşik 80.0°C üstünde",
    }
    base.update(overrides)
    return Anomaly(**base)  # type: ignore[arg-type]


def test_anomaly_holds_all_fields() -> None:
    """Anomaly tüm spec § 5 alanlarını taşır."""
    a = _anomaly()
    assert a.device_id == "device_001"
    assert a.rule_name == "motor_temperature_high"
    assert a.sensor == "motor_temperature"
    assert a.severity == "critical"
    assert a.score == 0.9
    assert a.value == 92.0


def test_anomaly_is_frozen() -> None:
    """Anomaly immutable (frozen) — yazıldıktan sonra değişmez."""
    a = _anomaly()
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.score = 0.1  # type: ignore[misc]


def test_detector_cannot_be_instantiated_directly() -> None:
    """Detector ABC; abstract metotlar implemente edilmeden örneklenemez."""
    with pytest.raises(TypeError):
        Detector()  # type: ignore[abstract]


def test_detector_subclass_contract() -> None:
    """Somut alt sınıf name property + detect(window) sağlar."""

    class _Noop(Detector):
        @property
        def name(self) -> str:
            return "noop"

        def detect(self, window: pd.DataFrame) -> list[Anomaly]:
            return []

    det = _Noop()
    assert det.name == "noop"
    assert det.detect(pd.DataFrame()) == []


def test_validity_rules_constant() -> None:
    """VALIDITY_RULES base.py'de tek-kaynak; sensör-sağlığı kurallarını içerir (Iter 8.8)."""
    from detectors.base import VALIDITY_RULES

    assert VALIDITY_RULES == frozenset({"sensor_out_of_range", "sensor_frozen"})

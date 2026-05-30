"""HydraulicPressureDecline birim testi (Faz 4 Iter 4.2, spec § 6 — B, türev)."""
from __future__ import annotations

import pandas as pd

from detectors.rules.hydraulic_pressure_decline import HydraulicPressureDecline


def _window(
    values: list[float],
    state: str = "holding",
    sensor: str = "hydraulic_pressure",
) -> pd.DataFrame:
    """1Hz timestamp'lerle pencere kurar (slope bar/dk için zaman ekseni gerekli)."""
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:{i // 60:02d}:{i % 60:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": [state] * len(values),
            "value": values,
        }
    )


def test_triggers_on_declining_pressure() -> None:
    # 80'den dakikada ~5 bar düşüş: 120 sn boyunca 80 → 70 (slope -5/dk).
    values = [80.0 - 5.0 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    anomalies = rule.detect(_window(values))
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_name == "hydraulic_pressure_decline"
    assert a.sensor == "hydraulic_pressure"
    assert a.value < -1.5  # slope bar/dk, negatif
    assert a.severity == "warning"


def test_no_trigger_on_flat_pressure() -> None:
    values = [80.0, 80.1, 79.9, 80.0, 80.2, 79.8, 80.0, 80.1, 79.9, 80.0, 80.0, 80.1]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    assert rule.detect(_window(values)) == []  # slope ~0 > -1.5


def test_no_trigger_on_mild_decline_above_threshold() -> None:
    # Dakikada 1 bar düşüş (slope -1.0) > -1.5 eşiği → tetiklemez.
    values = [80.0 - 1.0 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    assert rule.detect(_window(values)) == []


def test_no_trigger_too_few_samples() -> None:
    values = [80.0 - 5.0 * (i / 60.0) for i in range(5)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    assert rule.detect(_window(values)) == []


def test_ignores_other_states() -> None:
    values = [80.0 - 5.0 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    assert rule.detect(_window(values, state="raising")) == []

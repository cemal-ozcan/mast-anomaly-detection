"""HydraulicPressureDecline birim testi (Faz 4 Iter 4.2, spec § 6 — B, türev)."""
from __future__ import annotations

import random

import pandas as pd
import pytest

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
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10, trip_slope_bar_per_min=6.0)
    anomalies = rule.detect(_window(values))
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_name == "hydraulic_pressure_decline"
    assert a.sensor == "hydraulic_pressure"
    assert a.value < -1.5  # slope bar/dk, negatif
    assert a.severity == "warning"


def test_no_trigger_on_flat_pressure() -> None:
    values = [80.0, 80.1, 79.9, 80.0, 80.2, 79.8, 80.0, 80.1, 79.9, 80.0, 80.0, 80.1]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10, trip_slope_bar_per_min=6.0)
    assert rule.detect(_window(values)) == []  # slope ~0 > -1.5


def test_no_trigger_on_mild_decline_above_threshold() -> None:
    # Dakikada 1 bar düşüş (slope -1.0) > -1.5 eşiği → tetiklemez.
    values = [80.0 - 1.0 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10, trip_slope_bar_per_min=6.0)
    assert rule.detect(_window(values)) == []


def test_no_trigger_too_few_samples() -> None:
    values = [80.0 - 5.0 * (i / 60.0) for i in range(5)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10, trip_slope_bar_per_min=6.0)
    assert rule.detect(_window(values)) == []


def test_ignores_other_states() -> None:
    values = [80.0 - 5.0 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10, trip_slope_bar_per_min=6.0)
    assert rule.detect(_window(values, state="raising")) == []


# --- Regresyon: canlı smoke'ta keşfedilen az-örnekli gürültü FP'si (üretim params 3.0/60) ---
# Gürültülü basınçta (σ=2 bar) az örnekli en-küçük-kareler eğimi çok oynaktır
# (slope std ~13 bar/dk @ n=10 → temiz veride ~%45 yanlış pozitif). Üretim min_samples=60
# guard'ı bunu yapısal olarak engeller; eşik 3.0 + n=60 (slope std ~0.9) → FP ~%0.02.


def test_regression_few_noisy_samples_skipped_by_min_samples() -> None:
    """Az sayıda gürültülü HOLDING örneği üretim min_samples=60 ile değerlendirilmeden atlanır.

    Bu, canlı smoke'taki FP'nin kök nedenini kapatır: oynak az-örnekli eğim hiç hesaplanmaz.
    """
    rng = random.Random(0)
    values = [80.0 + rng.gauss(0.0, 2.0) for _ in range(30)]  # 30 < 60 → guard
    rule = HydraulicPressureDecline(
        state="holding", slope_threshold_bar_per_min=3.0, min_samples=60, trip_slope_bar_per_min=6.0
    )
    assert rule.detect(_window(values)) == []


def test_regression_full_clean_noisy_window_no_fire() -> None:
    """60 örnekli temiz-gürültülü pencere (eğim ~0) üretim eşiği 3.0 bar/dk'da tetiklemez."""
    rng = random.Random(3)
    values = [80.0 + rng.gauss(0.0, 2.0) for _ in range(60)]
    rule = HydraulicPressureDecline(
        state="holding", slope_threshold_bar_per_min=3.0, min_samples=60, trip_slope_bar_per_min=6.0
    )
    assert rule.detect(_window(values)) == []


def test_regression_leak_still_detected_with_production_params() -> None:
    """Gerçek kaçak (-5 bar/dk) 60 örnekli pencerede üretim parametreleriyle (3.0, 60) tetiklenir.

    FP düzeltmesi (eşik/min_samples yükseltme) gerçek pozitifi bozmadı.
    """
    rng = random.Random(5)
    values = [80.0 - 5.0 * (i / 60.0) + rng.gauss(0.0, 2.0) for i in range(60)]
    rule = HydraulicPressureDecline(
        state="holding", slope_threshold_bar_per_min=3.0, min_samples=60, trip_slope_bar_per_min=6.0
    )
    anomalies = rule.detect(_window(values))
    assert len(anomalies) == 1
    assert anomalies[0].value < -3.0


def test_trip_not_greater_than_warn_raises() -> None:
    """trip_slope_bar_per_min <= slope_threshold_bar_per_min → ValueError (band tanımsız, Iter 8.4)."""
    with pytest.raises(ValueError):
        HydraulicPressureDecline(
            state="holding", slope_threshold_bar_per_min=3.0, min_samples=60, trip_slope_bar_per_min=3.0
        )


def test_score_is_band_position() -> None:
    """slope -4.5 bar/dk büyüklüğü, warn 3.0, trip 6.0 → band-pozisyon 0.5 (Iter 8.4 spec § 3)."""
    values = [80.0 - 4.5 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(
        state="holding", slope_threshold_bar_per_min=3.0, min_samples=10, trip_slope_bar_per_min=6.0
    )
    assert rule.detect(_window(values))[0].score == pytest.approx(0.5)

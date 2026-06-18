"""IQR istatistiksel dedektör birim testi (Faz 5 Iter 5.2, spec § 6)."""
from __future__ import annotations

import pandas as pd
import pytest

from detectors.base import Anomaly
from detectors.statistical.iqr import IQR


def _window(
    baseline_vals: list[float],
    current_vals: list[float],
    sensor: str = "motor_current",
    state: str = "holding",
) -> pd.DataFrame:
    """Baseline (geçmiş) + güncel (son tail) satırlı uzun pencere kurar (test_three_sigma deseni)."""
    rows: list[dict[str, object]] = []
    for i, v in enumerate(baseline_vals):
        rows.append({"device_id": "device_001", "timestamp": f"2026-05-30T00:{i // 60:02d}:{i % 60:02d}.000Z",
                     "sensor": sensor, "state": state, "value": v})
    for i, v in enumerate(current_vals):
        rows.append({"device_id": "device_001", "timestamp": f"2026-05-30T02:00:{i:02d}.000Z",
                     "sensor": sensor, "state": state, "value": v})
    return pd.DataFrame(rows, columns=["device_id", "timestamp", "sensor", "state", "value"])


# Varyanslı baseline (IQR>0): ~0.5 etrafında 0.4/0.5/0.6 döngüsü.
_BASELINE = [0.5 + 0.1 * ((i % 3) - 1) for i in range(40)]


def test_triggers_when_current_median_above_fence() -> None:
    """Güncel medyan baseline üst fence'in dışındaysa iqr:<sensor> anomalisi."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    anomalies = rule.detect(_window(_BASELINE, [2.0] * 6))
    assert len(anomalies) == 1
    a = anomalies[0]
    assert isinstance(a, Anomaly)
    assert a.rule_name == "iqr:motor_current"
    assert a.sensor == "motor_current"
    assert a.device_id == "device_001"
    assert a.value == 2.0  # güncel medyan
    assert a.severity == "warning"
    assert 0.0 <= a.score <= 1.0


def test_triggers_when_current_median_below_fence() -> None:
    """Güncel medyan alt fence'in altındaysa da tetikler (B kaçak yönü)."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    anomalies = rule.detect(_window(_BASELINE, [-2.0] * 6))
    assert len(anomalies) == 1
    assert anomalies[0].value == -2.0


def test_no_trigger_when_current_within_fence() -> None:
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    assert rule.detect(_window(_BASELINE, [0.5] * 6)) == []


def test_no_trigger_when_baseline_constant_iqr_zero() -> None:
    """Sabit baseline (IQR≈0) → güvenilir fence yok → atlanır (EPSILON koruması)."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    assert rule.detect(_window([0.5] * 40, [2.0] * 6)) == []


def test_no_trigger_when_insufficient_baseline() -> None:
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    assert rule.detect(_window(_BASELINE[:10], [2.0] * 6)) == []


def test_per_state_baseline_isolation() -> None:
    """Baseline HOLDING; güncel RAISING → eşleşen state baseline'ı yok → atlanır."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    window = _window(_BASELINE, [8.0] * 6, state="holding")
    window.loc[window["timestamp"].str.startswith("2026-05-30T02:00"), "state"] = "raising"
    assert rule.detect(window) == []


def test_sensors_filter_limits_evaluation() -> None:
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5,
               sensors=["vibration"])
    assert rule.detect(_window(_BASELINE, [2.0] * 6, sensor="motor_current")) == []


def test_empty_window_returns_empty() -> None:
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []


def test_score_is_band_position_far_out_fence() -> None:
    """score = distance/((far−1.5)·IQR) — Tukey far-out fence band-pozisyonu (Iter 8.4 spec § 3)."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, iqr_multiplier_critical=3.0, min_baseline=30, min_current=5)
    # baseline Q1=0.4 Q3=0.6 IQR=0.2; cur medyan 0.95 → iç-fence 0.9 dışı mesafe 0.05;
    # far-out span (3.0−1.5)·0.2=0.3 → band 0.05/0.3 ≈ 0.1667
    anomalies = rule.detect(_window(_BASELINE, [0.95] * 6))
    assert len(anomalies) == 1
    assert anomalies[0].score == pytest.approx(0.1667, abs=0.01)


def test_iqr_multiplier_critical_not_greater_raises() -> None:
    """iqr_multiplier_critical <= iqr_multiplier → ValueError (band tanımsız, Iter 8.4)."""
    with pytest.raises(ValueError):
        IQR(current_window_s=60, iqr_multiplier=3.0, iqr_multiplier_critical=3.0)

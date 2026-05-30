"""ThreeSigma istatistiksel dedektör birim testi (Faz 5 Iter 5.1, spec § 6)."""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly
from detectors.statistical.three_sigma import ThreeSigma


def _window(
    baseline_vals: list[float],
    current_vals: list[float],
    sensor: str = "motor_current",
    state: str = "holding",
) -> pd.DataFrame:
    """Baseline (geçmiş, dakikalar) + güncel (son ~saniyeler) satırlı uzun pencere kurar."""
    rows: list[dict[str, object]] = []
    for i, v in enumerate(baseline_vals):
        rows.append({"device_id": "device_001", "timestamp": f"2026-05-30T00:{i // 60:02d}:{i % 60:02d}.000Z",
                     "sensor": sensor, "state": state, "value": v})
    for i, v in enumerate(current_vals):
        rows.append({"device_id": "device_001", "timestamp": f"2026-05-30T02:00:{i:02d}.000Z",
                     "sensor": sensor, "state": state, "value": v})
    return pd.DataFrame(rows, columns=["device_id", "timestamp", "sensor", "state", "value"])


# Varyanslı baseline (σ>0): ~0.5 etrafında 0.4/0.5/0.6 döngüsü.
_BASELINE = [0.5 + 0.1 * ((i % 3) - 1) for i in range(40)]


def test_triggers_when_current_mean_far_from_baseline() -> None:
    """Güncel ort baseline μ±3σ dışındaysa three_sigma:<sensor> anomalisi."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    window = _window(_BASELINE, [2.0] * 6)  # baseline ~0.5±0.08, güncel 2.0 → çok dışında
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert isinstance(a, Anomaly)
    assert a.rule_name == "three_sigma:motor_current"
    assert a.sensor == "motor_current"
    assert a.device_id == "device_001"
    assert a.value == 2.0  # güncel ortalama
    assert a.severity == "warning"
    assert 0.0 <= a.score <= 1.0


def test_no_trigger_when_current_within_fence() -> None:
    """Güncel ort baseline'a yakınsa tetiklemez."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    assert rule.detect(_window(_BASELINE, [0.5] * 6)) == []


def test_no_trigger_when_baseline_constant_sigma_zero() -> None:
    """Sabit baseline (σ≈0) → güvenilir fence yok → atlanır (EPSILON koruması)."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    assert rule.detect(_window([0.5] * 40, [2.0] * 6)) == []


def test_no_trigger_when_insufficient_baseline() -> None:
    """Baseline < min_baseline → o (sensor,state) atlanır."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    assert rule.detect(_window(_BASELINE[:10], [2.0] * 6)) == []


def test_per_state_baseline_isolation() -> None:
    """Baseline HOLDING; güncel RAISING → eşleşen state baseline'ı yok → atlanır."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    window = _window(_BASELINE, [8.0] * 6, state="holding")
    # güncel satırların state'ini RAISING yap (baseline HOLDING kalır)
    window.loc[window["timestamp"].str.startswith("2026-05-30T02:00"), "state"] = "raising"
    assert rule.detect(window) == []


def test_sensors_filter_limits_evaluation() -> None:
    """sensors=['vibration'] → motor_current sapması yok sayılır."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5,
                      sensors=["vibration"])
    assert rule.detect(_window(_BASELINE, [2.0] * 6, sensor="motor_current")) == []


def test_empty_window_returns_empty() -> None:
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []

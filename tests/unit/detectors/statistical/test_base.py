"""statistical.base saf yardımcıları (Faz 5 Iter 5.1, spec § 5)."""
from __future__ import annotations

import pandas as pd

from detectors.statistical.base import iter_sensor_state_groups, split_recent


def _row(ts: str, value: float, sensor: str = "motor_current", state: str = "holding") -> dict[str, object]:
    return {"device_id": "device_001", "timestamp": ts, "sensor": sensor, "state": state, "value": value}


def test_split_recent_partitions_by_max_timestamp() -> None:
    """current = son current_window_s; baseline = öncesi (pencerenin max-ts'ine göre)."""
    rows = [_row(f"2026-05-30T00:00:{i:02d}.000Z", float(i)) for i in range(40)]  # 0..39 sn
    window = pd.DataFrame(rows)
    baseline, current = split_recent(window, current_window_s=10)
    # max_ts = ...:39; cutoff = ...:29 → current = [29..39] (11 satır), baseline = [0..28] (29 satır)
    assert list(current["value"]) == [float(i) for i in range(29, 40)]
    assert list(baseline["value"]) == [float(i) for i in range(0, 29)]


def test_split_recent_empty_window() -> None:
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    baseline, current = split_recent(empty, current_window_s=60)
    assert baseline.empty and current.empty


def test_iter_groups_yields_sufficient_only() -> None:
    """Yeterli baseline (≥min_baseline) + güncel (≥min_current) örnekli (sensor,state) yield edilir."""
    baseline = pd.DataFrame([_row(f"2026-05-30T00:{i:02d}:00.000Z", 0.5) for i in range(30)])
    current = pd.DataFrame([_row(f"2026-05-30T01:00:{i:02d}.000Z", 2.0) for i in range(5)])
    groups = list(iter_sensor_state_groups(baseline, current, None, min_baseline=30, min_current=5))
    assert len(groups) == 1
    sensor, state, base_vals, cur_vals = groups[0]
    assert sensor == "motor_current" and state == "holding"
    assert len(base_vals) == 30 and len(cur_vals) == 5


def test_iter_groups_skips_insufficient() -> None:
    """Az örnekli grup atlanır (abstain)."""
    baseline = pd.DataFrame([_row(f"2026-05-30T00:{i:02d}:00.000Z", 0.5) for i in range(10)])  # <30
    current = pd.DataFrame([_row(f"2026-05-30T01:00:{i:02d}.000Z", 2.0) for i in range(5)])
    assert list(iter_sensor_state_groups(baseline, current, None, min_baseline=30, min_current=5)) == []


def test_iter_groups_respects_sensor_filter() -> None:
    """sensors verilirse yalnız o sensörler değerlendirilir."""
    base = [_row(f"2026-05-30T00:{i:02d}:00.000Z", 0.5, sensor="motor_current") for i in range(30)]
    base += [_row(f"2026-05-30T00:{i:02d}:30.000Z", 0.05, sensor="vibration") for i in range(30)]
    cur = [_row(f"2026-05-30T01:00:{i:02d}.000Z", 2.0, sensor="motor_current") for i in range(5)]
    cur += [_row(f"2026-05-30T01:00:{i:02d}.500Z", 0.5, sensor="vibration") for i in range(5)]
    groups = list(iter_sensor_state_groups(
        pd.DataFrame(base), pd.DataFrame(cur), ["motor_current"], min_baseline=30, min_current=5
    ))
    assert [g[0] for g in groups] == ["motor_current"]

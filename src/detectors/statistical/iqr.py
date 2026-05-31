"""IQR: güncel pencere baseline Q1/Q3 ± m·IQR dışındaysa anomali (Faz 5, spec § 6).

On-the-fly rolling: uzun pencereyi recent-vs-rest böler, (sensor, state) başına baseline
Q1/Q3 + IQR hesaplar, güncel tail median'ı fence dışındaysa tetikler. Robust (median/IQR →
aykırı dirençli, ThreeSigma'nın mean/σ'sına tamamlayıcı). Saf — `now` gerekmez.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from detectors.base import Anomaly, Detector
from detectors.statistical.base import EPSILON, iter_sensor_state_groups, split_recent


class IQR(Detector):
    """Her (sensor, state) için baseline [Q1−m·IQR, Q3+m·IQR]; güncel tail median'ı dışındaysa tetikler."""

    def __init__(
        self,
        current_window_s: int,
        iqr_multiplier: float = 1.5,
        min_baseline: int = 30,
        min_current: int = 5,
        sensors: Sequence[str] | None = None,
        severity: str = "warning",
    ) -> None:
        """Args: current_window_s — güncel tail saniyesi (config'ten); iqr_multiplier — fence çarpanı;
        min_baseline/min_current — minimum örnek; sensors — izlenen sensörler (None=tümü); severity."""
        self._current_window_s = current_window_s
        self._iqr_multiplier = iqr_multiplier
        self._min_baseline = min_baseline
        self._min_current = min_current
        self._sensors = list(sensors) if sensors is not None else None
        self._severity = severity

    @property
    def name(self) -> str:
        return "iqr"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        baseline_df, current_df = split_recent(window, self._current_window_s)
        if current_df.empty:
            return []
        device_id = str(current_df["device_id"].iloc[0])
        win_start = str(current_df["timestamp"].min())
        win_end = str(current_df["timestamp"].max())
        anomalies: list[Anomaly] = []
        for sensor, state, base_vals, cur_vals in iter_sensor_state_groups(
            baseline_df, current_df, self._sensors, self._min_baseline, self._min_current
        ):
            q1 = float(base_vals.quantile(0.25))
            q3 = float(base_vals.quantile(0.75))
            iqr = q3 - q1
            if iqr < EPSILON:
                continue
            cur_median = float(cur_vals.median())
            fence = self._iqr_multiplier * iqr
            lower = q1 - fence
            upper = q3 + fence
            if lower <= cur_median <= upper:
                continue
            # Fence dışı mesafenin IQR'a oranı (spec § 6: "mesafenin IQR'a oranı"); ≥0, ≤1 clamp.
            distance = (lower - cur_median) if cur_median < lower else (cur_median - upper)
            score = min(1.0, distance / iqr)
            anomalies.append(
                Anomaly(
                    device_id=device_id,
                    rule_name=f"iqr:{sensor}",
                    sensor=sensor,
                    severity=self._severity,
                    score=score,
                    window_start=win_start,
                    window_end=win_end,
                    value=cur_median,
                    description=(
                        f"{sensor} {state} güncel medyan {cur_median:.2f} "
                        f"baseline IQR [{lower:.2f}, {upper:.2f}] dışı"
                    ),
                )
            )
        return anomalies

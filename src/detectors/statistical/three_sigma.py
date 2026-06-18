"""ThreeSigma: güncel pencere baseline μ±k·σ dışındaysa anomali (Faz 5, spec § 6).

On-the-fly rolling: uzun pencereyi recent-vs-rest böler, (sensor, state) başına baseline
mean μ + std σ hesaplar, güncel tail mean'i fence dışındaysa tetikler. Saf — `now` gerekmez.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from detectors.base import Anomaly, Detector
from detectors.scoring import band_position_score
from detectors.statistical.base import EPSILON, iter_sensor_state_groups, split_recent


class ThreeSigma(Detector):
    """Her (sensor, state) için baseline mean±k·σ; güncel tail mean'i fence dışındaysa tetikler."""

    def __init__(
        self,
        current_window_s: int,
        sigma_k: float = 3.0,
        sigma_k_critical: float = 6.0,
        min_baseline: int = 30,
        min_current: int = 5,
        sensors: Sequence[str] | None = None,
        severity: str = "warning",
    ) -> None:
        """Args: current_window_s — güncel tail saniyesi (config'ten); sigma_k — fence (warn)
        katsayısı; sigma_k_critical — band-pozisyon kritik katsayısı (skor 1.0; > sigma_k olmalı);
        min_baseline/min_current — minimum örnek; sensors — izlenen sensörler (None=tümü); severity."""
        if sigma_k_critical <= sigma_k:
            raise ValueError(
                f"ThreeSigma: sigma_k_critical ({sigma_k_critical}) > sigma_k ({sigma_k}) olmalı"
            )
        self._current_window_s = current_window_s
        self._sigma_k = sigma_k
        self._sigma_k_critical = sigma_k_critical
        self._min_baseline = min_baseline
        self._min_current = min_current
        self._sensors = list(sensors) if sensors is not None else None
        self._severity = severity

    @property
    def name(self) -> str:
        return "three_sigma"

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
            mu = float(base_vals.mean())
            sigma = float(base_vals.std())  # ddof=1
            if sigma < EPSILON:
                continue
            cur_mean = float(cur_vals.mean())
            deviation = abs(cur_mean - mu)
            fence = self._sigma_k * sigma
            if deviation <= fence:
                continue
            # Band-pozisyon: sapma fence (sigma_k·σ) → kritik fence (sigma_k_critical·σ) bandında (Iter 8.4).
            # Band orijini: burada q=μ'den SAPMA & warn=fence; IQR'da q=fence-DIŞI mesafe & warn=0 —
            # iki konvansiyon da "iç-fence → 0" verir (iqr.py ile çapraz-ref; yeni stat dedektörde dikkat).
            score = band_position_score(deviation, fence, self._sigma_k_critical * sigma)
            anomalies.append(
                Anomaly(
                    device_id=device_id,
                    rule_name=f"three_sigma:{sensor}",
                    sensor=sensor,
                    severity=self._severity,
                    score=score,
                    window_start=win_start,
                    window_end=win_end,
                    value=cur_mean,
                    description=(
                        f"{sensor} {state} güncel ort {cur_mean:.2f} "
                        f"baseline {mu:.2f}±{sigma:.2f} ({self._sigma_k:.0f}σ dışı)"
                    ),
                )
            )
        return anomalies

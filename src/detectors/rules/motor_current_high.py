"""MotorCurrentHigh: belirli state'te motor akımı pencere-ortalaması eşiği aşarsa anomali.

Spec § 6 (A, eşik+süre). Aktif state (raising) içinde motor_current'in pencere
ortalaması `threshold_a`'yı aşar VE en az `min_samples` örnek varsa (sürekli yük —
"süre" boyutu) tetikler. Eşik simülatör çıktısına kalibre: clean RAISING ort. ~8.0A,
MechanicalWear ~10.0A → 9.0A ayırma noktası.
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector
from detectors.scoring import band_position_score

SENSOR = "motor_current"


class MotorCurrentHigh(Detector):
    """RAISING (config'lenebilir state) motor_current pencere-ortalaması eşiği aşarsa tetikler."""

    def __init__(
        self,
        state: str,
        threshold_a: float,
        min_samples: int,
        trip_a: float,
        severity: str = "warning",
    ) -> None:
        """Args: state — aktif state ("raising"); threshold_a — akım (warn) eşiği (A);
        min_samples — minimum örnek (süre koşulu); trip_a — band-pozisyon kritik referansı
        (A, skor 1.0; trip_a > threshold_a olmalı); severity — anomali şiddeti."""
        if trip_a <= threshold_a:
            raise ValueError(f"MotorCurrentHigh: trip_a ({trip_a}) > threshold_a ({threshold_a}) olmalı")
        self._state = state
        self._threshold = threshold_a
        self._min_samples = min_samples
        self._trip_a = trip_a
        self._severity = severity

    @property
    def name(self) -> str:
        return "motor_current_high"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[(window["sensor"] == SENSOR) & (window["state"] == self._state)]
        if len(rows) < self._min_samples:
            return []
        mean_a = float(rows["value"].mean())
        if mean_a <= self._threshold:
            return []
        score = band_position_score(mean_a, self._threshold, self._trip_a)
        return [
            Anomaly(
                device_id=str(rows["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=str(rows["timestamp"].min()),
                window_end=str(rows["timestamp"].max()),
                value=mean_a,
                description=(
                    f"motor_current {self._state} ortalaması {mean_a:.2f}A "
                    f"eşik {self._threshold:.2f}A üstünde"
                ),
            )
        ]

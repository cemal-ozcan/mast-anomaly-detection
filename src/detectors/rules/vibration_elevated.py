"""VibrationElevated: belirli state'te titreşim pencere-ortalaması eşiği aşarsa anomali.

Spec § 6 (A, oran). Aktif state (raising) içinde vibration pencere ortalaması
`threshold_g`'yi aşar VE ≥ `min_samples` örnek varsa tetikler. Eşik state-baseline'a
relatif (clean RAISING ~0.30g, MechanicalWear ~0.45g → 0.37g ayırma; tek-örnek tepe
yerine ortalama, gürültü FP'sine karşı sağlam).
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector
from detectors.scoring import band_position_score

SENSOR = "vibration"


class VibrationElevated(Detector):
    """RAISING (config'lenebilir) titreşim pencere-ortalaması eşiği aşarsa tetikler."""

    def __init__(
        self,
        state: str,
        threshold_g: float,
        min_samples: int,
        trip_g: float,
        severity: str = "warning",
    ) -> None:
        """Args: state — aktif state; threshold_g — titreşim (warn) eşiği (g);
        min_samples — minimum örnek; trip_g — band-pozisyon kritik referansı (g, skor 1.0;
        trip_g > threshold_g olmalı); severity — anomali şiddeti."""
        if trip_g <= threshold_g:
            raise ValueError(f"VibrationElevated: trip_g ({trip_g}) > threshold_g ({threshold_g}) olmalı")
        self._state = state
        self._threshold = threshold_g
        self._min_samples = min_samples
        self._trip_g = trip_g
        self._severity = severity

    @property
    def name(self) -> str:
        return "vibration_elevated"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[(window["sensor"] == SENSOR) & (window["state"] == self._state)]
        if len(rows) < self._min_samples:
            return []
        mean_g = float(rows["value"].mean())
        if mean_g <= self._threshold:
            return []
        score = band_position_score(mean_g, self._threshold, self._trip_g)
        return [
            Anomaly(
                device_id=str(rows["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=str(rows["timestamp"].min()),
                window_end=str(rows["timestamp"].max()),
                value=mean_g,
                description=(
                    f"vibration {self._state} ortalaması {mean_g:.3f}g "
                    f"eşik {self._threshold:.3f}g üstünde"
                ),
            )
        ]

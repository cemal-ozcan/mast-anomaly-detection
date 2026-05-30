"""HydraulicPressureDecline: HOLDING'de basınç eğimi (slope) negatif eşiği aşarsa anomali.

Spec § 6 (B, türev). HOLDING içinde hydraulic_pressure'ın zaman-eğimi (en küçük kareler
doğru uydurma, bar/dakika) `-slope_threshold_bar_per_min`'in altındaysa (daha dik düşüş)
ve ≥ `min_samples` örnek varsa tetikler. Kalibre (üretim config'i): eşik 3.0 bar/dk +
min_samples 60. Az-örnekli gürültülü eğim çok oynaktır (slope std ~13 bar/dk @ n=10,
σ=2 bar) — büyük min_samples bunu hem yapısal (n<60 → skip) hem istatistiksel (n=60 →
slope std ~0.9) olarak bastırır: clean FP ~%0.02, kaçak (-5 bar/dk) TP ~%99 (canlı smoke
kalibrasyonu). poll'da window_s=120 ≥ 60 örnek için yeterli HOLDING penceresi sağlar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from detectors.base import Anomaly, Detector

SENSOR = "hydraulic_pressure"


class HydraulicPressureDecline(Detector):
    """HOLDING (config'lenebilir) basınç eğimi negatif eşiği aşarsa tetikler."""

    def __init__(
        self,
        state: str,
        slope_threshold_bar_per_min: float,
        min_samples: int,
        severity: str = "warning",
    ) -> None:
        """Args: state — aktif state ("holding"); slope_threshold_bar_per_min — pozitif
        eşik (slope < -bu değer → anomali); min_samples — eğim için min örnek; severity."""
        self._state = state
        self._threshold = slope_threshold_bar_per_min
        self._min_samples = min_samples
        self._severity = severity

    @property
    def name(self) -> str:
        return "hydraulic_pressure_decline"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[(window["sensor"] == SENSOR) & (window["state"] == self._state)]
        if len(rows) < self._min_samples:
            return []
        rows = rows.sort_values("timestamp")
        t = pd.to_datetime(rows["timestamp"], format="ISO8601", utc=True)
        x = (t - t.iloc[0]).dt.total_seconds().to_numpy()
        if x[-1] == x[0]:  # sıfır zaman aralığı (tüm örnekler aynı an) → eğim tanımsız
            return []
        y = rows["value"].to_numpy()
        slope_per_min = float(np.polyfit(x, y, 1)[0]) * 60.0
        if slope_per_min >= -self._threshold:
            return []
        score = min(1.0, (-slope_per_min) / (self._threshold * 4.0))
        return [
            Anomaly(
                device_id=str(rows["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=str(rows["timestamp"].min()),
                window_end=str(rows["timestamp"].max()),
                value=slope_per_min,
                description=(
                    f"hydraulic_pressure {self._state} eğimi {slope_per_min:.2f} bar/dk "
                    f"(eşik -{self._threshold:.2f})"
                ),
            )
        ]

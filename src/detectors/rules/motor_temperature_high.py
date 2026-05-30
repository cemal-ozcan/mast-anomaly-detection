"""MotorTemperatureHigh: motor sıcaklığı kritik eşiği aşınca anomali (spec § 6).

Universal eşik kuralı (DOMAIN Senaryo F — Sıcaklık Aşımı). Simülatör F üretmediğinden
yalnız birim test (sentetik pencere) ile doğrulanır. Eşik constructor ile enjekte edilir
(DI); Iter 4.2 bunu config'ten okuyup kalibre eder.
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector

SENSOR = "motor_temperature"


class MotorTemperatureHigh(Detector):
    """Pencere içindeki tepe motor sıcaklığı `critical_threshold_c`'yi (strict) aşarsa tetikler."""

    def __init__(self, critical_threshold_c: float) -> None:
        """Args: critical_threshold_c — kritik sıcaklık eşiği (°C). value > eşik → anomali."""
        self._threshold = critical_threshold_c

    @property
    def name(self) -> str:
        return "motor_temperature_high"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        """motor_temperature satırlarında tepe değer eşiği aşarsa tek Anomaly döndür."""
        if window.empty:
            return []
        sub = window[window["sensor"] == SENSOR]
        if sub.empty:
            return []

        peak = float(sub["value"].max())
        if peak <= self._threshold:
            return []

        device_id = str(sub["device_id"].iloc[0])
        window_start = str(sub["timestamp"].iloc[0])
        window_end = str(sub["timestamp"].iloc[-1])
        # Skor: eşik üstü aşımın eşiğe oranı, [0, 1]'e clamp (basit normalize, Iter 4.3 fusion).
        score = min(1.0, (peak - self._threshold) / self._threshold)
        description = (
            f"motor_temperature {peak:.1f}°C kritik eşik {self._threshold:.1f}°C üstünde"
        )
        return [
            Anomaly(
                device_id=device_id,
                rule_name=self.name,
                sensor=SENSOR,
                severity="critical",
                score=score,
                window_start=window_start,
                window_end=window_end,
                value=peak,
                description=description,
            )
        ]

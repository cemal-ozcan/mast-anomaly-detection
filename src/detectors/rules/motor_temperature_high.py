"""MotorTemperatureHigh: motor sıcaklığı kritik eşiği aşınca anomali (spec § 6).

Universal eşik kuralı (DOMAIN Senaryo F — Sıcaklık Aşımı). Simülatör F üretmediğinden
yalnız birim test (sentetik pencere) ile doğrulanır. Eşik constructor ile enjekte edilir
(DI); Iter 4.2 bunu config'ten okuyup kalibre eder.
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector
from detectors.scoring import band_position_score

SENSOR = "motor_temperature"


class MotorTemperatureHigh(Detector):
    """Pencere içindeki tepe motor sıcaklığı `critical_threshold_c`'yi (strict) aşarsa tetikler."""

    def __init__(
        self, critical_threshold_c: float, trip_c: float, severity: str = "critical"
    ) -> None:
        """Args: critical_threshold_c — kritik (warn) sıcaklık eşiği (°C), value > eşik → anomali;
        trip_c — band-pozisyon kritik referansı (°C, skor 1.0); severity (config-driven)."""
        if trip_c <= critical_threshold_c:
            raise ValueError(
                f"MotorTemperatureHigh: trip_c ({trip_c}) > critical_threshold_c "
                f"({critical_threshold_c}) olmalı"
            )
        self._threshold = critical_threshold_c
        self._trip_c = trip_c
        self._severity = severity

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
        # Skor: band-pozisyon (warn=eşik → 0, trip → 1), dedektörler arası karşılaştırılabilir (Iter 8.4).
        score = band_position_score(peak, self._threshold, self._trip_c)
        description = (
            f"motor_temperature {peak:.1f}°C kritik eşik {self._threshold:.1f}°C üstünde"
        )
        return [
            Anomaly(
                device_id=device_id,
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=window_start,
                window_end=window_end,
                value=peak,
                description=description,
            )
        ]

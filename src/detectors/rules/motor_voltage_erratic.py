"""MotorVoltageErratic: motor_voltage pencere standart sapması eşiği aşarsa anomali.

Spec § 6 (C, varyans). State-agnostik (ElectricalFault tüm state'lerde aktif).
Pencere içindeki motor_voltage örneklerinin std'si `std_threshold_v`'yi aşar VE
≥ `min_samples` örnek varsa tetikler. Kalibre: clean std ~0.2V, ElectricalFault
~4.0V → 1.0V ayırma (geniş marj).
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector
from detectors.scoring import band_position_score

SENSOR = "motor_voltage"


class MotorVoltageErratic(Detector):
    """motor_voltage pencere std'si eşiği aşarsa tetikler (state filtresi YOK)."""

    def __init__(
        self,
        std_threshold_v: float,
        min_samples: int,
        trip_std_v: float,
        severity: str = "warning",
    ) -> None:
        """Args: std_threshold_v — std (warn) eşiği (V); min_samples — min örnek;
        trip_std_v — band-pozisyon kritik referansı (V, skor 1.0; > std_threshold_v olmalı); severity."""
        if trip_std_v <= std_threshold_v:
            raise ValueError(f"MotorVoltageErratic: trip_std_v ({trip_std_v}) > std_threshold_v ({std_threshold_v}) olmalı")
        self._threshold = std_threshold_v
        self._min_samples = min_samples
        self._trip = trip_std_v
        self._severity = severity

    @property
    def name(self) -> str:
        return "motor_voltage_erratic"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[window["sensor"] == SENSOR]
        if len(rows) < self._min_samples:
            return []
        std_v = float(rows["value"].std())  # pandas ddof=1
        if std_v <= self._threshold:
            return []
        score = band_position_score(std_v, self._threshold, self._trip)
        return [
            Anomaly(
                device_id=str(rows["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=str(rows["timestamp"].min()),
                window_end=str(rows["timestamp"].max()),
                value=std_v,
                description=f"motor_voltage std {std_v:.2f}V eşik {self._threshold:.2f}V üstünde",
            )
        ]

"""SensorFrozen: bir sensör son N örnekte (neredeyse) sabit kalırsa donmuş-sensör anomalisi.

Spec § 6 (E universal, süre). Konfigüre edilen sensörün en yeni `min_samples` örneğinin
değer aralığı (max - min) `epsilon`'u aşmıyorsa "donmuş" kabul edilir. Simülatör donmuş
sensör üretmediğinden (her sensör gauss gürültülü) yalnız birim test ile doğrulanır;
gerçek gürültülü veride asla tetiklenmez (FP güvenli).

Skor ikili validity (sabit 1.0) — `sensor_out_of_range` ile aynı veri-kalitesi sınıfı
(band-pozisyon değil; donmuş sensör = geçersiz veri, Iter 8.4 spec § 5).
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector


class SensorFrozen(Detector):
    """Konfigüre edilen sensör son `min_samples` örnekte sabitse tetikler."""

    def __init__(
        self,
        sensor: str,
        min_samples: int,
        epsilon: float,
        severity: str = "warning",
    ) -> None:
        """Args: sensor — izlenen sensör adı; min_samples — kuyruk penceresi boyutu;
        epsilon — "sabit" toleransı (max-min ≤ ε → donmuş); severity."""
        self._sensor = sensor
        self._min_samples = min_samples
        self._epsilon = epsilon
        self._severity = severity

    @property
    def name(self) -> str:
        return "sensor_frozen"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[window["sensor"] == self._sensor]
        if len(rows) < self._min_samples:
            return []
        recent = rows.sort_values("timestamp").tail(self._min_samples)
        spread = float(recent["value"].max() - recent["value"].min())
        if spread > self._epsilon:
            return []
        frozen_value = float(recent["value"].iloc[-1])
        return [
            Anomaly(
                device_id=str(recent["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=self._sensor,
                severity=self._severity,
                score=1.0,
                window_start=str(recent["timestamp"].min()),
                window_end=str(recent["timestamp"].max()),
                value=frozen_value,
                description=(
                    f"{self._sensor} son {self._min_samples} örnekte donmuş "
                    f"(aralık {spread:.4f} ≤ {self._epsilon})"
                ),
            )
        ]

"""SensorOutOfRange: bir sensör fiziksel imkânsızlık sınırları dışında değer üretirse anomali.

Faz 8 Iter 8.3 spec § 6a. sensor_frozen'ın kardeşi (sensör-sağlığı). Sınırlar "imkânsızlık"
sınırıdır, "normal" değil: meşru arıza değerleri (F'in yüksek sıcaklığı, C'nin voltaj spike'ları,
B'nin düşük basıncı) sınır İÇİNDE kalır → bu kuralı tetiklemez (onları eşik kuralları yakalar).
Yalnız fiziksel saçmalık (örn. negatif mast pozisyonu) tetikler. Read-only / gözlem modu.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from detectors.base import Anomaly, Detector


class SensorOutOfRange(Detector):
    """Pencerede herhangi bir sensör [min, max] fiziksel sınırı dışındaysa, o sensör için anomali."""

    def __init__(
        self,
        bounds: Mapping[str, Sequence[float]],
        severity: str = "high",
    ) -> None:
        """Args: bounds — sensör adı → [min, max] fiziksel imkânsızlık sınırı; severity."""
        self._bounds: dict[str, tuple[float, float]] = {
            sensor: (float(b[0]), float(b[1])) for sensor, b in bounds.items()
        }
        self._severity = severity

    @property
    def name(self) -> str:
        return "sensor_out_of_range"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        anomalies: list[Anomaly] = []
        for sensor, (lo, hi) in self._bounds.items():
            sub = window[window["sensor"] == sensor]
            if sub.empty:
                continue
            vals = sub["value"].to_numpy(dtype=float)
            # Her okuma için sınır-aşımı: alt sınır altı VEYA üst sınır üstü mesafe (>0 ise dışında).
            excess = np.maximum(lo - vals, vals - hi)
            worst = int(excess.argmax())
            if excess[worst] <= 0.0:
                continue  # hepsi sınır içinde
            row = sub.iloc[worst]
            value = float(row["value"])
            margin = hi - lo
            score = min(1.0, float(excess[worst]) / margin) if margin > 0 else 1.0
            anomalies.append(
                Anomaly(
                    device_id=str(row["device_id"]),
                    rule_name=self.name,
                    sensor=sensor,
                    severity=self._severity,
                    score=score,
                    window_start=str(sub["timestamp"].iloc[0]),
                    window_end=str(sub["timestamp"].iloc[-1]),
                    value=value,
                    description=(
                        f"{sensor} {value:.2f} fiziksel sınır [{lo:.1f}, {hi:.1f}] dışında "
                        f"(sensör arızası)"
                    ),
                )
            )
        return anomalies

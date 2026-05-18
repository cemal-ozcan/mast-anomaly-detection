"""Iterasyon 1: Minimal motor akımı sensörü. Sabit baseline + Gauss gürültü."""
from __future__ import annotations

import random

from src.simulator.config import SensorConfig


class MotorCurrentSensor:
    """Motor akımı (A) ölçer. Iterasyon 1'de state machine yok — sabit baseline."""

    def __init__(self, config: SensorConfig, rng: random.Random) -> None:
        """Motor akımı sensörü oluştur.

        Args:
            config: Sensör yapılandırması (name, unit, baseline, noise_std).
            rng: Rastgele sayı üreteci.

        Raises:
            ValueError: config.name != "motor_current" ise.
        """
        if config.name != "motor_current":
            raise ValueError(
                f"MotorCurrentSensor sensör adı 'motor_current' bekler, alınan: {config.name!r}"
            )
        self.config = config
        self._rng = rng

    def sample(self) -> float:
        """Bu tick için (baseline + Gauss gürültü) değerini döndür.

        Returns:
            Motor akımı değeri (A) — baseline + Gaussian(0, noise_std).
        """
        return self.config.baseline + self._rng.gauss(0.0, self.config.noise_std)

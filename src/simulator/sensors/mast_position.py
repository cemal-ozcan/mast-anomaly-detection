"""Mast pozisyon sensörü. compute_position'dan gelen değeri passthrough yapar.
DOMAIN.md sat. 63."""
from __future__ import annotations

from simulator.config import SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor


class MastPositionSensor(BaseSensor):
    """Mast pozisyonu (mm). Engine compute_position() ile hesaplanan değeri
    direkt döner; engine üzerine ±1 mm gauss gürültü ekler.

    DOMAIN.md sat. 63: pozisyon doğrusal artış/azalış, ideal hızda eğim sabit.
    Lineer hesap zaten runtime.compute_position()'da; sensör ekstra mantık yapmaz.
    """

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "mast_position":
            raise ValueError(
                f"MastPositionSensor 'mast_position' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """Engine'in hesapladığı pozisyonu passthrough — state'e duyarlı değil."""
        return position_mm

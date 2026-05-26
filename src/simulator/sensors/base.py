"""Sensör sözleşmesi: tüm sensörler bu ABC'yi uygular (spec § 5)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from simulator.config import SensorConfig
from simulator.runtime import DeviceRuntimeState


class BaseSensor(ABC):
    """Bir sensörün davranışını temsil eder.

    Sözleşme:
        - Aynı sensör instance'ı + aynı runtime tick sırası → aynı çıktı sırası
          (deterministik). RNG yok.
        - Gürültü engine tarafından eklenir (spec § 8): clean → fault → noise.
          Sensörler saf değer döndürür.
        - Sensör instance'ı internal state tutabilir (örn. motor_temperature
          Iterasyon 2b'de). Diğer sensörler stateless.
    """

    config: SensorConfig

    def __init__(self, config: SensorConfig) -> None:
        self.config = config

    @abstractmethod
    def compute(
        self,
        runtime: DeviceRuntimeState,
        position_mm: float,
    ) -> float:
        """Bu sensör için bu tick'teki TEMİZ (arızasız, gürültüsüz) değer.

        Args:
            runtime: Cihazın anlık durumu.
            position_mm: Engine tarafından compute_position() ile hesaplanmış pozisyon.

        Returns:
            Sensörün bu tick'teki temiz çıktısı.
        """

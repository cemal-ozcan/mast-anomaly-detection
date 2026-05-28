"""Titreşim sensörü (g RMS). motor_current şablonu: motor enerjili kategori.
DOMAIN.md sat. 64, spec § 6 LOWERING notu."""
from __future__ import annotations

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# DOMAIN.md sat. 64 değerleri:
_IDLE_VIBRATION_G = 0.05    # sabit durumda çok düşük
_ACTIVE_VIBRATION_G = 0.3   # hareket halinde 0.1-0.5 RMS (aralık ortası)


class VibrationSensor(BaseSensor):
    """Titreşim (g). IDLE/HOLDING'de düşük, RAISING/LOWERING'de yüksek."""

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "vibration":
            raise ValueError(
                f"VibrationSensor 'vibration' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """State'e göre temiz titreşim değeri."""
        match runtime.state:
            case DeviceState.IDLE | DeviceState.HOLDING:
                return _IDLE_VIBRATION_G
            case DeviceState.RAISING | DeviceState.LOWERING:
                return _ACTIVE_VIBRATION_G

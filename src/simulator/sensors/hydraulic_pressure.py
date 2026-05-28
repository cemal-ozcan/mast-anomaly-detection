"""Hidrolik basınç sensörü. State-bazlı 4 baseline. DOMAIN.md sat. 60, spec § 6."""
from __future__ import annotations

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# DOMAIN.md sat. 60 değerleri (aralık ortaları):
_IDLE_PRESSURE_BAR = 10.0       # 5-20 boşta
_RAISING_PRESSURE_BAR = 150.0   # 100-200 hareket
_HOLDING_PRESSURE_BAR = 80.0    # 50-150 tutucu
_LOWERING_PRESSURE_BAR = 80.0   # spec § 6 LOWERING notu: HOLDING ile aynı kategori


class HydraulicPressureSensor(BaseSensor):
    """Hidrolik basınç (bar). State'e göre 4 farklı baseline."""

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "hydraulic_pressure":
            raise ValueError(
                f"HydraulicPressureSensor 'hydraulic_pressure' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """State'e göre temiz hidrolik basıncı."""
        match runtime.state:
            case DeviceState.IDLE:
                return _IDLE_PRESSURE_BAR
            case DeviceState.RAISING:
                return _RAISING_PRESSURE_BAR
            case DeviceState.HOLDING:
                return _HOLDING_PRESSURE_BAR
            case DeviceState.LOWERING:
                return _LOWERING_PRESSURE_BAR

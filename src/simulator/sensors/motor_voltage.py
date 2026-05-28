"""Motor besleme gerilimi sensörü. Sabit 24V, state-agnostic. DOMAIN.md sat. 21."""
from __future__ import annotations

from simulator.config import SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# DOMAIN.md sat. 21 — motor besleme gerilimi nominal 24V. State'e duyarlı değil;
# Iter 4 ElectricalFault senaryosu bu sensörün üzerinde dalgalanma üretecek.
_BASELINE_V = 24.0


class MotorVoltageSensor(BaseSensor):
    """Motor besleme gerilimi (V). Tüm state'lerde sabit 24V baseline."""

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "motor_voltage":
            raise ValueError(
                f"MotorVoltageSensor 'motor_voltage' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """Sabit 24V — state ve pozisyondan bağımsız."""
        return _BASELINE_V

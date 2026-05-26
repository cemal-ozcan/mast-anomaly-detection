"""Iterasyon 2: state-aware motor akımı sensörü. State'e göre baseline değişir."""
from __future__ import annotations

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# DOMAIN.md sat. 58 — hareket halinde 5-15A kararlı tüketim. 8.0 bu aralığın
# merkezi-altı, gerçekçi nominal yük. RAISING ve LOWERING aynı kategori.
_ACTIVE_BASELINE_A = 8.0


class MotorCurrentSensor(BaseSensor):
    """Motor akımı (A). IDLE/HOLDING'de düşük (config.baseline), RAISING/LOWERING'de yüksek."""

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "motor_current":
            raise ValueError(
                f"MotorCurrentSensor 'motor_current' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """State'e göre temiz motor akımı değeri.

        IDLE/HOLDING: config.baseline (sensör boşta, motor durmuş).
        RAISING/LOWERING: _ACTIVE_BASELINE_A (motor enerjili, yük altında).
        """
        match runtime.state:
            case DeviceState.IDLE | DeviceState.HOLDING:
                return self.config.baseline
            case DeviceState.RAISING | DeviceState.LOWERING:
                return _ACTIVE_BASELINE_A

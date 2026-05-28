"""Motor sıcaklığı sensörü — TEK STATEFUL sensör. Lineer ısınma/soğuma.
DOMAIN.md sat. 67, spec § 5 stateful pattern + § 6 + invaryant 5."""
from __future__ import annotations

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# Spec § 6 değerleri (DOMAIN.md sat. 67):
_AMBIENT_C = 25.0                # çevre sıcaklığı / alt sınır
_MAX_TEMP_C = 35.0               # motor enerjili üst sınır
_HEATING_RATE_C_PER_S = 0.08     # motor enerjili (RAISING/HOLDING/LOWERING)
_COOLING_RATE_C_PER_S = 0.04     # IDLE
_DELTA_PER_TICK_S = 1.0          # spec § 5 tick interval varsayımı: 1 Hz


class MotorTemperatureSensor(BaseSensor):
    """Motor sıcaklığı (°C). TEK STATEFUL sensör — instance attribute olarak son
    sıcaklığı taşır. Motor enerjili durumlarda (RAISING/HOLDING/LOWERING) lineer
    ısınır (0.08 °C/s, üst 35); IDLE'da lineer soğur (0.04 °C/s, alt 25).

    Spec § 5 invaryant 5: state transition'lar instance state'i reset etmez.
    Tick interval = 1.0 s varsayımı (spec § 5 stateful sensor notu).
    """

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "motor_temperature":
            raise ValueError(
                f"MotorTemperatureSensor 'motor_temperature' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)
        # Instance state — cihaz yaşam süresi boyunca taşınır.
        self._current_temp_c: float = _AMBIENT_C

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """State'e göre lineer ısınma veya soğuma; alt/üst sınırlarla saturate."""
        if runtime.state == DeviceState.IDLE:
            self._current_temp_c = max(
                _AMBIENT_C,
                self._current_temp_c - _COOLING_RATE_C_PER_S * _DELTA_PER_TICK_S,
            )
        else:  # RAISING, HOLDING, LOWERING — motor enerjili
            self._current_temp_c = min(
                _MAX_TEMP_C,
                self._current_temp_c + _HEATING_RATE_C_PER_S * _DELTA_PER_TICK_S,
            )
        return self._current_temp_c

"""Kural registry: ad → Detector factory (Faz 4). build_detectors config-driven kurar."""
from __future__ import annotations

from collections.abc import Callable

from detectors.base import Detector
from detectors.rules.hydraulic_pressure_decline import HydraulicPressureDecline
from detectors.rules.motor_current_high import MotorCurrentHigh
from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.rules.motor_voltage_erratic import MotorVoltageErratic
from detectors.rules.sensor_frozen import SensorFrozen
from detectors.rules.vibration_elevated import VibrationElevated

# Callable[..., Detector]: kurallar farklı __init__ imzalı; build_detectors generic
# cls(severity=..., **params) çağırır → tip imza-agnostik olmalı (mypy-strict).
RULE_REGISTRY: dict[str, Callable[..., Detector]] = {
    "hydraulic_pressure_decline": HydraulicPressureDecline,
    "motor_current_high": MotorCurrentHigh,
    "motor_temperature_high": MotorTemperatureHigh,
    "motor_voltage_erratic": MotorVoltageErratic,
    "sensor_frozen": SensorFrozen,
    "vibration_elevated": VibrationElevated,
}

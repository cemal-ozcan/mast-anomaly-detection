"""Kural registry: ad → Detector sınıfı (Faz 4 Iter 4.1; tam config-driven aktivasyon Iter 4.2)."""
from __future__ import annotations

from detectors.base import Detector
from detectors.rules.motor_temperature_high import MotorTemperatureHigh

RULE_REGISTRY: dict[str, type[Detector]] = {
    "motor_temperature_high": MotorTemperatureHigh,
}

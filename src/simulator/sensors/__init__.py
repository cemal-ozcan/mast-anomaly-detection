"""Sensör registry — YAML sensör adı string'ini sınıfa eşler."""
from __future__ import annotations

from simulator.sensors.base import BaseSensor
from simulator.sensors.mast_position import MastPositionSensor
from simulator.sensors.motor_current import MotorCurrentSensor
from simulator.sensors.motor_voltage import MotorVoltageSensor

SENSOR_REGISTRY: dict[str, type[BaseSensor]] = {
    "mast_position": MastPositionSensor,
    "motor_current": MotorCurrentSensor,
    "motor_voltage": MotorVoltageSensor,
}

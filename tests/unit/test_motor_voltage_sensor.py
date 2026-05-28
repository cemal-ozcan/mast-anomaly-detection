"""MotorVoltageSensor için unit testler — sabit 24V, state-agnostic."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.motor_voltage import MotorVoltageSensor


def _config() -> SensorConfig:
    return SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2)


def _make_runtime(state: DeviceState) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10.0,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(42),
        started_at_monotonic=0.0,
    )


def test_motor_voltage_sensor_is_base_sensor() -> None:
    assert isinstance(MotorVoltageSensor(_config()), BaseSensor)


def test_compute_returns_24v_in_all_states() -> None:
    sensor = MotorVoltageSensor(_config())
    for state in DeviceState:
        runtime = _make_runtime(state)
        assert sensor.compute(runtime, position_mm=0.0) == 24.0


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="motor_voltage"):
        MotorVoltageSensor(bad)

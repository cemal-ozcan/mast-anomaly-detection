"""MastPositionSensor için unit testler — position_mm passthrough."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.mast_position import MastPositionSensor


def _config() -> SensorConfig:
    return SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0)


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


def test_mast_position_sensor_is_base_sensor() -> None:
    assert isinstance(MastPositionSensor(_config()), BaseSensor)


def test_compute_returns_position_mm_passthrough() -> None:
    sensor = MastPositionSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    for pos in [0.0, 1234.5, 5000.0]:
        assert sensor.compute(runtime, position_mm=pos) == pos


def test_compute_does_not_depend_on_state() -> None:
    """Pozisyon engine tarafından compute_position ile zaten state'e göre hesaplandı.
    Sensör sadece parametreyi geri verir, state'i kendi yorumlamaz."""
    sensor = MastPositionSensor(_config())
    for state in DeviceState:
        runtime = _make_runtime(state)
        assert sensor.compute(runtime, position_mm=2500.0) == 2500.0


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="mast_position"):
        MastPositionSensor(bad)

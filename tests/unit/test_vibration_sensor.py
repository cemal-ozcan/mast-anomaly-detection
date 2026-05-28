"""VibrationSensor için unit testler — motor_current şablonu (motor enerjili kategori)."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.vibration import VibrationSensor


def _config() -> SensorConfig:
    return SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01)


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


def test_vibration_sensor_is_base_sensor() -> None:
    assert isinstance(VibrationSensor(_config()), BaseSensor)


def test_compute_idle_returns_low() -> None:
    """DOMAIN.md sat. 64: sabit durumda çok düşük (≈0.05g RMS)."""
    sensor = VibrationSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(runtime, position_mm=0.0)
    assert value == 0.05


def test_compute_holding_same_as_idle() -> None:
    """Motor durmuş kategori — IDLE ile aynı."""
    sensor = VibrationSensor(_config())
    runtime = _make_runtime(DeviceState.HOLDING)
    assert sensor.compute(runtime, position_mm=5000.0) == 0.05


def test_compute_raising_returns_active() -> None:
    """DOMAIN.md sat. 64: hareket halinde 0.1-0.5g RMS."""
    sensor = VibrationSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    value = sensor.compute(runtime, position_mm=1000.0)
    assert 0.1 <= value <= 0.5


def test_compute_lowering_same_as_raising() -> None:
    """Spec § 6 LOWERING notu: RAISING kategorisi (motor enerjili hareket)."""
    sensor = VibrationSensor(_config())
    runtime_raising = _make_runtime(DeviceState.RAISING)
    runtime_lowering = _make_runtime(DeviceState.LOWERING)
    assert sensor.compute(runtime_lowering, 0.0) == sensor.compute(runtime_raising, 0.0)


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="vibration"):
        VibrationSensor(bad)

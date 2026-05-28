"""HydraulicPressureSensor için unit testler — state-bazlı 4 baseline."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.hydraulic_pressure import HydraulicPressureSensor


def _config() -> SensorConfig:
    return SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0)


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


def test_hydraulic_pressure_sensor_is_base_sensor() -> None:
    assert isinstance(HydraulicPressureSensor(_config()), BaseSensor)


def test_compute_idle_returns_low() -> None:
    """DOMAIN.md sat. 60: boşta 5-20 bar."""
    sensor = HydraulicPressureSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(runtime, position_mm=0.0)
    assert 5.0 <= value <= 20.0


def test_compute_raising_returns_high() -> None:
    """DOMAIN.md sat. 60: RAISING'de 100-200 bar (spec § 3 Iter 2 kriter 3: ≥100)."""
    sensor = HydraulicPressureSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    value = sensor.compute(runtime, position_mm=1000.0)
    assert 100.0 <= value <= 200.0


def test_compute_holding_returns_medium() -> None:
    """DOMAIN.md sat. 60: HOLDING'de 50-150 bar (tutucu)."""
    sensor = HydraulicPressureSensor(_config())
    runtime = _make_runtime(DeviceState.HOLDING)
    value = sensor.compute(runtime, position_mm=5000.0)
    assert 50.0 <= value <= 150.0


def test_compute_lowering_same_as_holding() -> None:
    """Spec § 6 LOWERING notu: HOLDING kategorisi (motor enerjili tutucu basınç)."""
    sensor = HydraulicPressureSensor(_config())
    runtime_holding = _make_runtime(DeviceState.HOLDING)
    runtime_lowering = _make_runtime(DeviceState.LOWERING)
    assert sensor.compute(runtime_lowering, 0.0) == sensor.compute(runtime_holding, 0.0)


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="hydraulic_pressure"):
        HydraulicPressureSensor(bad)

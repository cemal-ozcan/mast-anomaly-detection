"""MotorCurrentSensor state-aware compute() davranışı için unit testler."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.motor_current import MotorCurrentSensor


def _config(baseline: float = 0.5, noise_std: float = 0.1) -> SensorConfig:
    return SensorConfig(
        name="motor_current",
        unit="A",
        baseline=baseline,
        noise_std=noise_std,
    )


def _make_runtime(state: DeviceState) -> DeviceRuntimeState:
    """Minimal runtime for compute() — sadece state field'i lazım."""
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10.0,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(42),
        started_at_monotonic=0.0,
    )


def test_motor_current_sensor_is_base_sensor() -> None:
    sensor = MotorCurrentSensor(_config())
    assert isinstance(sensor, BaseSensor)


def test_compute_in_idle_returns_config_baseline() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.IDLE)
    assert sensor.compute(runtime, position_mm=0.0) == 0.5


def test_compute_in_holding_returns_config_baseline() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.HOLDING)
    assert sensor.compute(runtime, position_mm=5000.0) == 0.5


def test_compute_in_raising_returns_active_baseline() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.RAISING)
    value = sensor.compute(runtime, position_mm=1000.0)
    # DOMAIN.md sat. 58: hareket halinde 5-15 A aralığı. _ACTIVE_BASELINE_A=8.0.
    assert value == 8.0


def test_compute_in_lowering_returns_active_baseline() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.LOWERING)
    value = sensor.compute(runtime, position_mm=2500.0)
    # LOWERING aynı kategori (motor enerjili). Spec § 6 LOWERING notu.
    assert value == 8.0


def test_compute_is_deterministic_no_rng() -> None:
    """Sensör saf — gürültü engine'in işi (spec § 8). Aynı runtime → aynı çıktı."""
    sensor = MotorCurrentSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    values = [sensor.compute(runtime, position_mm=1000.0) for _ in range(5)]
    assert all(v == values[0] for v in values)


def test_idle_baseline_within_domain_range() -> None:
    """DOMAIN.md sat. 58: IDLE'da 0-1A. config.baseline=0.5 bu aralığa düşer."""
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(runtime, position_mm=0.0)
    assert 0.0 <= value <= 1.0


def test_active_baseline_within_domain_range() -> None:
    """DOMAIN.md sat. 58: RAISING/LOWERING'de 5-15A. _ACTIVE_BASELINE_A=8.0 bu aralık."""
    sensor = MotorCurrentSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    value = sensor.compute(runtime, position_mm=1000.0)
    assert 5.0 <= value <= 15.0


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0)
    with pytest.raises(ValueError, match="motor_current"):
        MotorCurrentSensor(bad)


def test_base_sensor_cannot_be_instantiated() -> None:
    """BaseSensor ABC abstract — direkt instance edilemez."""
    config = SensorConfig(name="x", unit="X", baseline=0.0, noise_std=0.0)
    with pytest.raises(TypeError, match="abstract"):
        BaseSensor(config)  # type: ignore[abstract]


def test_sensor_registry_contains_motor_current() -> None:
    from simulator.sensors import SENSOR_REGISTRY

    assert "motor_current" in SENSOR_REGISTRY
    assert SENSOR_REGISTRY["motor_current"] is MotorCurrentSensor


def test_sensor_registry_only_iterasyon_2a_sensors() -> None:
    """Iterasyon 2b Task 4'de hydraulic_pressure eklendi. 4 sensör: motor_current, motor_voltage, mast_position, hydraulic_pressure."""
    from simulator.sensors import SENSOR_REGISTRY

    assert set(SENSOR_REGISTRY.keys()) == {"motor_current", "motor_voltage", "mast_position", "hydraulic_pressure"}

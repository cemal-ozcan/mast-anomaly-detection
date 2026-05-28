"""MotorTemperatureSensor için unit testler — TEK STATEFUL sensör.
Lineer ısınma 0.08 °C/s (motor enerjili), soğuma 0.04 °C/s (IDLE)."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.motor_temperature import MotorTemperatureSensor


def _config() -> SensorConfig:
    return SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5)


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


def test_motor_temperature_sensor_is_base_sensor() -> None:
    assert isinstance(MotorTemperatureSensor(_config()), BaseSensor)


def test_initial_temperature_is_ambient() -> None:
    """Yeni instance çevre sıcaklığında (25°C) başlar."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    # IDLE'da hemen soğutmaya başlar ama zaten 25'te → alt sınır 25, aynı kalır.
    assert sensor.compute(runtime, position_mm=0.0) == pytest.approx(25.0)


def test_heating_in_raising_lineer_per_tick() -> None:
    """RAISING'de her tick 0.08°C artar (1 Hz varsayımı, spec § 5 tick interval notu)."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    # 5 ardışık tick: 25 → 25.08 → 25.16 → 25.24 → 25.32 → 25.40
    values = [sensor.compute(runtime, position_mm=1000.0) for _ in range(5)]
    expected = [25.08, 25.16, 25.24, 25.32, 25.40]
    for v, e in zip(values, expected, strict=True):
        assert v == pytest.approx(e)


def test_heating_caps_at_35() -> None:
    """Üst sınır 35°C — uzun süre RAISING'de bile aşmaz."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.HOLDING)  # motor enerjili
    # 25'ten 35'e (10°C) çıkmak 10 / 0.08 = 125 tick. 200 tick'te kapağa otururuz.
    for _ in range(200):
        sensor.compute(runtime, position_mm=5000.0)
    final = sensor.compute(runtime, position_mm=5000.0)
    assert final == pytest.approx(35.0)


def test_cooling_in_idle_lineer_per_tick() -> None:
    """IDLE'da her tick 0.04°C azalır."""
    sensor = MotorTemperatureSensor(_config())
    # Önce ısıt
    hot_runtime = _make_runtime(DeviceState.RAISING)
    for _ in range(125):  # 25 → ~35
        sensor.compute(hot_runtime, position_mm=1000.0)
    # Sonra soğut
    cool_runtime = _make_runtime(DeviceState.IDLE)
    before = sensor.compute(cool_runtime, position_mm=0.0)
    after = sensor.compute(cool_runtime, position_mm=0.0)
    assert before - after == pytest.approx(0.04)


def test_cooling_caps_at_ambient_25() -> None:
    """Alt sınır 25°C — uzun IDLE'da çevre sıcaklığının altına inmez."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    # Zaten 25'te; çok tick'te de aynı kalmalı.
    for _ in range(100):
        sensor.compute(runtime, position_mm=0.0)
    final = sensor.compute(runtime, position_mm=0.0)
    assert final == pytest.approx(25.0)


def test_lowering_heats_same_as_raising() -> None:
    """Spec § 6: motor enerjili durumlarda (RAISING/HOLDING/LOWERING) aynı ısınma hızı."""
    s1 = MotorTemperatureSensor(_config())
    s2 = MotorTemperatureSensor(_config())
    raising = _make_runtime(DeviceState.RAISING)
    lowering = _make_runtime(DeviceState.LOWERING)
    for _ in range(10):
        v1 = s1.compute(raising, position_mm=1000.0)
        v2 = s2.compute(lowering, position_mm=2500.0)
    assert v1 == pytest.approx(v2)


def test_state_change_preserves_instance_state() -> None:
    """Spec § 5 invaryant 5: state transition reset etmez."""
    sensor = MotorTemperatureSensor(_config())
    raising = _make_runtime(DeviceState.RAISING)
    sensor.compute(raising, position_mm=1000.0)  # 25 → 25.08
    sensor.compute(raising, position_mm=1000.0)  # 25.08 → 25.16
    # Şimdi IDLE'a geç — son sıcaklık taşınmalı (reset değil)
    idle = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(idle, position_mm=0.0)
    # 25.16 - 0.04 = 25.12
    assert value == pytest.approx(25.12)


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="motor_temperature"):
        MotorTemperatureSensor(bad)

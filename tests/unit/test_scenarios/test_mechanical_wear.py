"""MechanicalWear (spec § 9 A) modify behavior testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState) -> DeviceRuntimeState:
    """Test fixture: minimal runtime, state belirli."""
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=60.0,
        position_mm=0.0,
        cycle_count=0,
        rng=random.Random(42),
        started_at_monotonic=0.0,
        clock=lambda: 0.0,
    )


def test_mechanical_wear_requires_severity_and_ramp_up_s() -> None:
    """Eksik params → boot-time ValueError."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    with pytest.raises(ValueError, match="severity"):
        MechanicalWear(params={"ramp_up_s": 300})
    with pytest.raises(ValueError, match="ramp_up_s"):
        MechanicalWear(params={"severity": 0.2})
    # Tam set → OK
    MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})


def test_mechanical_wear_idle_returns_clean_value() -> None:
    """IDLE'da motor dönmez → aşınma görünmez → identity."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE), scenario_elapsed_s=600.0)
    assert scenario.modify("motor_current", 0.5, ctx) == 0.5
    assert scenario.modify("vibration", 0.05, ctx) == 0.05


def test_mechanical_wear_lowering_returns_clean_value() -> None:
    """LOWERING'de aktif değil (spec § 9 A: sadece RAISING + HOLDING)."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.LOWERING), scenario_elapsed_s=600.0)
    assert scenario.modify("motor_current", 8.0, ctx) == 8.0


def test_mechanical_wear_raising_increases_motor_current() -> None:
    """RAISING'de motor_current * (1 + factor), factor = elapsed/ramp_up * severity (capped 1.0)."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=300.0)
    # elapsed/ramp_up = 1.0, capped → factor = 1.0 * 0.2 = 0.2
    # clean=8.0 → 8.0 * (1 + 0.2) = 9.6
    assert scenario.modify("motor_current", 8.0, ctx) == pytest.approx(9.6)


def test_mechanical_wear_factor_caps_at_severity() -> None:
    """elapsed_s ≥ ramp_up_s sonrası factor sabit kalır (cap)."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.3, "ramp_up_s": 60})
    ctx_early = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=60.0)
    ctx_late = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=3600.0)
    # Her ikisinde factor = 0.3 (capped)
    assert scenario.modify("motor_current", 10.0, ctx_early) == pytest.approx(13.0)
    assert scenario.modify("motor_current", 10.0, ctx_late) == pytest.approx(13.0)


def test_mechanical_wear_holding_applies_all_four_sensor_formulas() -> None:
    """HOLDING'de motor_current, mast_position, vibration, motor_temperature modifiye."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING), scenario_elapsed_s=300.0)
    # factor = 0.2
    assert scenario.modify("motor_current", 0.5, ctx) == pytest.approx(0.5 * 1.2)
    # mast_position → clean / (1 + factor * 0.7) → yavaş yükseliş
    assert scenario.modify("mast_position", 5000.0, ctx) == pytest.approx(5000.0 / (1 + 0.2 * 0.7))
    # vibration → clean * (1 + factor * 2)
    assert scenario.modify("vibration", 0.05, ctx) == pytest.approx(0.05 * (1 + 0.2 * 2))
    # motor_temperature → clean + factor * 8.0
    assert scenario.modify("motor_temperature", 30.0, ctx) == pytest.approx(30.0 + 0.2 * 8.0)


def test_mechanical_wear_unaffected_sensors_return_clean() -> None:
    """motor_voltage, hydraulic_pressure formüllere dahil değil → identity."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=300.0)
    assert scenario.modify("motor_voltage", 24.0, ctx) == 24.0
    assert scenario.modify("hydraulic_pressure", 150.0, ctx) == 150.0


def test_mechanical_wear_registered_in_global_registry() -> None:
    """SCENARIO_REGISTRY['mechanical_wear'] mevcut ve MechanicalWear class'ına işaret eder."""
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.mechanical_wear import MechanicalWear

    assert SCENARIO_REGISTRY["mechanical_wear"] is MechanicalWear

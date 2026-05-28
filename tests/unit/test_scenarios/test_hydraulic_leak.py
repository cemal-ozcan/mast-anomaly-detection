"""HydraulicLeak (spec § 9 B, DOMAIN.md sat. 90-93) modify behavior testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState, elapsed_in_state_s: float = 0.0) -> DeviceRuntimeState:
    """Test fixture: state + elapsed_in_state_s belirli runtime.

    `runtime.elapsed_in_state_s` property `clock() - state_entered_at_monotonic`;
    bu yüzden clock=lambda: elapsed_in_state_s + state_entered_at_monotonic=0.0 ile
    istenen elapsed elde edilir.
    """
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10000.0,
        position_mm=0.0,
        cycle_count=0,
        rng=random.Random(42),
        started_at_monotonic=0.0,
        clock=lambda: elapsed_in_state_s,
    )


def test_hydraulic_leak_requires_leak_rate_and_position_sag() -> None:
    """Eksik params → boot-time ValueError."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    with pytest.raises(ValueError, match="leak_rate_bar_per_min"):
        HydraulicLeak(params={"position_sag_mm": 2.0})
    with pytest.raises(ValueError, match="position_sag_mm"):
        HydraulicLeak(params={"leak_rate_bar_per_min": 5.0})
    # Tam set → OK
    HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})


def test_hydraulic_leak_idle_returns_clean_value() -> None:
    """IDLE'da pompa kapalı → kaçak görünmez → identity."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE, 600.0), scenario_elapsed_s=600.0)
    assert scenario.modify("hydraulic_pressure", 10.0, ctx) == 10.0
    assert scenario.modify("mast_position", 0.0, ctx) == 0.0


def test_hydraulic_leak_raising_returns_clean_value() -> None:
    """RAISING'de pompa basıncı kaçağı maskeler (spec § 9 B notu)."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING, 600.0), scenario_elapsed_s=600.0)
    assert scenario.modify("hydraulic_pressure", 150.0, ctx) == 150.0
    assert scenario.modify("mast_position", 2500.0, ctx) == 2500.0


def test_hydraulic_leak_lowering_returns_clean_value() -> None:
    """LOWERING'de basınç zaten düşüyor → modifiye yok (spec § 9 B notu)."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.LOWERING, 600.0), scenario_elapsed_s=600.0)
    assert scenario.modify("hydraulic_pressure", 80.0, ctx) == 80.0


def test_hydraulic_leak_holding_pressure_drops_linearly_with_held_minutes() -> None:
    """HOLDING'de hydraulic_pressure → clean - leak_rate * held_minutes."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    # elapsed_in_state_s = 120s → held_minutes = 2.0 → pressure_drop = 10.0
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, 120.0), scenario_elapsed_s=120.0)
    # clean=80.0 → 80.0 - 10.0 = 70.0
    assert scenario.modify("hydraulic_pressure", 80.0, ctx) == pytest.approx(70.0)


def test_hydraulic_leak_holding_position_sags_linearly() -> None:
    """HOLDING'de mast_position → clean - position_sag_mm * held_minutes."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    # held_minutes = 3.0 → sag = 6.0 mm
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, 180.0), scenario_elapsed_s=180.0)
    assert scenario.modify("mast_position", 5000.0, ctx) == pytest.approx(4994.0)


def test_hydraulic_leak_pressure_floor_at_5_bar() -> None:
    """Çok uzun HOLDING → hydraulic_pressure max(5.0, clean - drop) ile alt sınırda kalır."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    # 60 dakika HOLDING → drop = 300 bar; clean=80 → -220 olurdu, floor 5.0 olmalı
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, 3600.0), scenario_elapsed_s=3600.0)
    assert scenario.modify("hydraulic_pressure", 80.0, ctx) == pytest.approx(5.0)


def test_hydraulic_leak_unaffected_sensors_return_clean() -> None:
    """motor_current, motor_voltage, motor_temperature, vibration etkilenmez → identity."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, 120.0), scenario_elapsed_s=120.0)
    assert scenario.modify("motor_current", 0.5, ctx) == 0.5
    assert scenario.modify("motor_voltage", 24.0, ctx) == 24.0
    assert scenario.modify("motor_temperature", 30.0, ctx) == 30.0
    assert scenario.modify("vibration", 0.05, ctx) == 0.05


def test_hydraulic_leak_registered_in_global_registry() -> None:
    """SCENARIO_REGISTRY['hydraulic_leak'] mevcut ve HydraulicLeak class'ına işaret eder."""
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    assert SCENARIO_REGISTRY["hydraulic_leak"] is HydraulicLeak

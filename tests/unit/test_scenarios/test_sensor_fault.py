"""SensorFault (Faz 8 Iter 8.3 E, DOMAIN.md § E imkânsız-değer) modify testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState, seed: int = 42) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=60.0,
        position_mm=0.0,
        cycle_count=0,
        rng=random.Random(seed),
        started_at_monotonic=0.0,
        clock=lambda: 0.0,
    )


def test_requires_params() -> None:
    from simulator.scenarios.sensor_fault import SensorFault

    with pytest.raises(ValueError, match="spike_prob"):
        SensorFault(params={"impossible_value": -500.0})
    with pytest.raises(ValueError, match="impossible_value"):
        SensorFault(params={"spike_prob": 0.3})
    SensorFault(params={"spike_prob": 0.3, "impossible_value": -500.0})


def test_only_affects_mast_position() -> None:
    """Diğer sensörler her zaman identity (spike olsa bile)."""
    from simulator.scenarios.sensor_fault import SensorFault

    sc = SensorFault(params={"spike_prob": 1.0, "impossible_value": -500.0})  # her tick spike
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING), scenario_elapsed_s=10.0)
    assert sc.modify("motor_current", 8.0, ctx) == 8.0
    assert sc.modify("hydraulic_pressure", 150.0, ctx) == 150.0


def test_spike_returns_impossible_value() -> None:
    """spike_prob=1.0 → mast_position daima imkânsız değere döner."""
    from simulator.scenarios.sensor_fault import SensorFault

    sc = SensorFault(params={"spike_prob": 1.0, "impossible_value": -500.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=10.0)
    assert sc.modify("mast_position", 3000.0, ctx) == -500.0


def test_no_spike_returns_clean() -> None:
    """spike_prob=0.0 → mast_position temiz değer."""
    from simulator.scenarios.sensor_fault import SensorFault

    sc = SensorFault(params={"spike_prob": 0.0, "impossible_value": -500.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=10.0)
    assert sc.modify("mast_position", 3000.0, ctx) == 3000.0


def test_active_in_all_states() -> None:
    """Sensör arızası harekete bağlı değil — IDLE'da da spike (mast_position)."""
    from simulator.scenarios.sensor_fault import SensorFault

    sc = SensorFault(params={"spike_prob": 1.0, "impossible_value": -500.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE), scenario_elapsed_s=10.0)
    assert sc.modify("mast_position", 0.0, ctx) == -500.0


def test_registered() -> None:
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.sensor_fault import SensorFault

    assert SCENARIO_REGISTRY["sensor_fault"] is SensorFault

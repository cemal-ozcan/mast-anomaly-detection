"""TemperatureOvershoot (Faz 8 Iter 8.3 F, DOMAIN.md § F) modify testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState) -> DeviceRuntimeState:
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


def test_requires_params() -> None:
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    with pytest.raises(ValueError, match="overshoot_rate_c_per_s"):
        TemperatureOvershoot(params={"max_overshoot_c": 60})
    with pytest.raises(ValueError, match="max_overshoot_c"):
        TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8})
    TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})


def test_idle_returns_clean() -> None:
    """IDLE'da aktif değil (motor enerjili değil) → identity."""
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    sc = TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE), scenario_elapsed_s=100.0)
    assert sc.modify("motor_temperature", 60.0, ctx) == 60.0


def test_raising_adds_overshoot_linearly() -> None:
    """RAISING'de motor_temperature += rate * elapsed (cap'e kadar)."""
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    sc = TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=50.0)
    # overshoot = min(60, 0.8*50=40) = 40 → 60 + 40 = 100
    assert sc.modify("motor_temperature", 60.0, ctx) == pytest.approx(100.0)


def test_overshoot_caps_at_max() -> None:
    """elapsed büyükse overshoot max_overshoot_c'de sabitlenir."""
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    sc = TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING), scenario_elapsed_s=10000.0)
    assert sc.modify("motor_temperature", 70.0, ctx) == pytest.approx(130.0)  # 70 + 60 cap


def test_only_affects_temperature() -> None:
    """Diğer sensörler identity."""
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    sc = TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=100.0)
    assert sc.modify("motor_current", 8.0, ctx) == 8.0
    assert sc.modify("hydraulic_pressure", 150.0, ctx) == 150.0


def test_registered() -> None:
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    assert SCENARIO_REGISTRY["temperature_overshoot"] is TemperatureOvershoot

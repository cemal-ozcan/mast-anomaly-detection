"""FaultScenario ABC + ScenarioContext + active_scenarios_at helper testleri (Iter 4a)."""
from __future__ import annotations

import pytest

from simulator.config import ScenarioWindow


def test_fault_scenario_cannot_be_instantiated_directly() -> None:
    """ABC: abstract method (modify) implement edilmeden instantiate edilemez."""
    from simulator.scenarios.base import FaultScenario

    with pytest.raises(TypeError, match="abstract"):
        FaultScenario(params={})  # type: ignore[abstract]


def test_scenario_context_is_frozen() -> None:
    """ScenarioContext immutable — modify(...) çağrıları arasında değişmesin."""
    from dataclasses import FrozenInstanceError

    from simulator.scenarios.base import ScenarioContext

    ctx = ScenarioContext(runtime=None, scenario_elapsed_s=10.0)  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        ctx.scenario_elapsed_s = 20.0  # type: ignore[misc]


def test_active_scenarios_at_returns_empty_when_no_windows() -> None:
    """Boş windows listesi → boş aktif liste."""
    from simulator.scenarios import active_scenarios_at

    assert active_scenarios_at([], 100.0) == []


def test_active_scenarios_at_returns_active_window_within_range() -> None:
    """start_after_s ≤ t < start_after_s + duration_s → aktif."""
    from simulator.scenarios import SCENARIO_REGISTRY, active_scenarios_at
    from simulator.scenarios.base import FaultScenario, ScenarioContext

    # Test-only dummy scenario, registry'ye geçici ekle
    class _Dummy(FaultScenario):
        name = "dummy"
        def modify(self, sensor_name: str, clean_value: float, ctx: ScenarioContext) -> float:
            return clean_value
    SCENARIO_REGISTRY["dummy"] = _Dummy
    try:
        windows = [ScenarioWindow(name="dummy", start_after_s=60.0, duration_s=120.0, params={})]
        active = active_scenarios_at(windows, device_elapsed_s=90.0)
        assert len(active) == 1
        scenario, window = active[0]
        assert isinstance(scenario, _Dummy)
        assert window.name == "dummy"
    finally:
        del SCENARIO_REGISTRY["dummy"]


def test_active_scenarios_at_excludes_window_before_start_and_after_end() -> None:
    """t < start_after_s veya t ≥ start_after_s + duration_s → aktif değil."""
    from simulator.scenarios import SCENARIO_REGISTRY, active_scenarios_at
    from simulator.scenarios.base import FaultScenario, ScenarioContext

    class _Dummy(FaultScenario):
        name = "dummy"
        def modify(self, sensor_name: str, clean_value: float, ctx: ScenarioContext) -> float:
            return clean_value
    SCENARIO_REGISTRY["dummy"] = _Dummy
    try:
        windows = [ScenarioWindow(name="dummy", start_after_s=60.0, duration_s=120.0, params={})]
        assert active_scenarios_at(windows, device_elapsed_s=59.9) == []
        assert active_scenarios_at(windows, device_elapsed_s=180.0) == []  # 60+120=180, exclusive
        assert active_scenarios_at(windows, device_elapsed_s=60.0) != []   # inclusive lower
        assert active_scenarios_at(windows, device_elapsed_s=179.999) != []
    finally:
        del SCENARIO_REGISTRY["dummy"]

"""ElectricalFault (spec § 9 C, DOMAIN.md sat. 102-106) modify behavior testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState, seed: int = 42) -> DeviceRuntimeState:
    """Test fixture: state + seed'li RNG."""
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10000.0,
        position_mm=0.0,
        cycle_count=0,
        rng=random.Random(seed),
        started_at_monotonic=0.0,
        clock=lambda: 0.0,
    )


def test_electrical_fault_requires_spike_prob_and_voltage_jitter_std() -> None:
    """Eksik params → boot-time ValueError."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    with pytest.raises(ValueError, match="spike_prob"):
        ElectricalFault(params={"voltage_jitter_std": 0.6})
    with pytest.raises(ValueError, match="voltage_jitter_std"):
        ElectricalFault(params={"spike_prob": 0.05})
    # Tam set → OK
    ElectricalFault(params={"spike_prob": 0.05, "voltage_jitter_std": 0.6})


def test_electrical_fault_active_in_all_states() -> None:
    """spike_prob=1.0 → her state'te motor_voltage değişir (state filter YOK)."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 1.0, "voltage_jitter_std": 0.6})
    for state in (DeviceState.IDLE, DeviceState.RAISING, DeviceState.HOLDING, DeviceState.LOWERING):
        ctx = ScenarioContext(runtime=_runtime(state), scenario_elapsed_s=0.0)
        # spike_prob=1.0 → spike kesin → motor_voltage clean+uniform(-30,30) → 24 ± 30 aralığında
        result = scenario.modify("motor_voltage", 24.0, ctx)
        assert -6.0 <= result <= 54.0, f"state={state}: motor_voltage {result} aralık dışında"


def test_electrical_fault_spike_branch_motor_current() -> None:
    """spike_prob=1.0 + seed deterministik → motor_current clean + uniform(-2, 4)."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 1.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    # rng deterministic; clean=8.0 → 8.0 + uniform(-2, 4) ∈ [6.0, 12.0]
    result = scenario.modify("motor_current", 8.0, ctx)
    assert 6.0 <= result <= 12.0


def test_electrical_fault_spike_branch_motor_voltage() -> None:
    """spike_prob=1.0 → motor_voltage clean + uniform(-30, 30) ∈ [clean-30, clean+30]."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 1.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, seed=42), scenario_elapsed_s=0.0)
    result = scenario.modify("motor_voltage", 24.0, ctx)
    assert -6.0 <= result <= 54.0


def test_electrical_fault_non_spike_branch_motor_voltage_gauss_jitter() -> None:
    """spike_prob=0.0 → motor_voltage clean + gauss(0, voltage_jitter_std)."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 0.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE, seed=42), scenario_elapsed_s=0.0)
    # 100 örnekleme: ortalama ≈ 24.0 ± 0.6 σ, std ≈ 0.6
    samples = [scenario.modify("motor_voltage", 24.0, ctx) for _ in range(100)]
    mean = sum(samples) / len(samples)
    assert abs(mean - 24.0) < 0.2, f"Ortalama {mean} 24.0'dan çok sapmış"


def test_electrical_fault_non_spike_branch_motor_current_unchanged() -> None:
    """spike_prob=0.0 → motor_current değişmez (sadece spike branch etkiler)."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 0.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    assert scenario.modify("motor_current", 8.0, ctx) == 8.0


def test_electrical_fault_unaffected_sensors_return_clean() -> None:
    """hydraulic_pressure, motor_temperature, mast_position, vibration etkilenmez."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 1.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    assert scenario.modify("hydraulic_pressure", 150.0, ctx) == 150.0
    assert scenario.modify("motor_temperature", 30.0, ctx) == 30.0
    assert scenario.modify("mast_position", 2500.0, ctx) == 2500.0
    assert scenario.modify("vibration", 0.3, ctx) == 0.3


def test_electrical_fault_deterministic_with_same_seed() -> None:
    """Aynı rng seed + aynı modify çağrı sırası → birebir aynı çıktı."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario_a = ElectricalFault(params={"spike_prob": 0.5, "voltage_jitter_std": 0.6})
    scenario_b = ElectricalFault(params={"spike_prob": 0.5, "voltage_jitter_std": 0.6})
    ctx_a = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    ctx_b = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)

    seq_a = [scenario_a.modify("motor_voltage", 24.0, ctx_a) for _ in range(20)]
    seq_b = [scenario_b.modify("motor_voltage", 24.0, ctx_b) for _ in range(20)]
    assert seq_a == seq_b


def test_electrical_fault_different_seeds_produce_different_sequences() -> None:
    """Negatif kontrol: farklı seed → farklı dizi."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario_a = ElectricalFault(params={"spike_prob": 0.5, "voltage_jitter_std": 0.6})
    scenario_b = ElectricalFault(params={"spike_prob": 0.5, "voltage_jitter_std": 0.6})
    ctx_a = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    ctx_b = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=7), scenario_elapsed_s=0.0)

    seq_a = [scenario_a.modify("motor_voltage", 24.0, ctx_a) for _ in range(20)]
    seq_b = [scenario_b.modify("motor_voltage", 24.0, ctx_b) for _ in range(20)]
    assert seq_a != seq_b


def test_electrical_fault_registered_in_global_registry() -> None:
    """SCENARIO_REGISTRY['electrical_fault'] mevcut ve ElectricalFault class'ına işaret eder."""
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.electrical_fault import ElectricalFault

    assert SCENARIO_REGISTRY["electrical_fault"] is ElectricalFault

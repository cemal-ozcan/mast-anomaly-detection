"""DeviceRuntimeState + state machine + position için unit testler."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, StateDurations
from simulator.runtime import DeviceRuntimeState, advance_state_machine, compute_position


class FakeClock:
    """Test'te zamanı manuel kontrol et (DI pattern, monkeypatch yerine)."""

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _fixed_durations() -> StateDurations:
    """Test'te deterministik kullanım için min == max."""
    return StateDurations(
        idle=(5.0, 5.0),
        raising=(10.0, 10.0),
        holding=(60.0, 60.0),
        lowering=(10.0, 10.0),
    )


def _make_runtime(
    *,
    clock: FakeClock,
    state: DeviceState = DeviceState.IDLE,
    duration: float = 5.0,
    start: float = 0.0,
    seed: int = 42,
) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=start,
        current_state_duration_s=duration,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(seed),
        started_at_monotonic=start,
        clock=clock,
    )


def test_runtime_can_be_constructed_with_all_fields() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock)
    assert runtime.state == DeviceState.IDLE
    assert runtime.current_state_duration_s == 5.0
    assert runtime.cycle_count == 0
    assert runtime.position_mm == 0.0


def test_elapsed_in_state_uses_clock_difference() -> None:
    clock = FakeClock(100.0)
    runtime = _make_runtime(clock=clock, start=100.0)
    assert runtime.elapsed_in_state_s == 0.0
    clock.advance(7.5)
    assert runtime.elapsed_in_state_s == 7.5


def test_device_elapsed_uses_started_at_monotonic() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, start=0.0)
    clock.advance(30.0)
    # State'e 30s önce girdik, cihaz spawn'dan da 30s geçti
    assert runtime.device_elapsed_s == 30.0
    assert runtime.elapsed_in_state_s == 30.0


def test_no_transition_before_duration_elapses() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    clock.advance(4.999)
    advance_state_machine(runtime, _fixed_durations())
    assert runtime.state == DeviceState.IDLE


def test_transition_happens_when_duration_elapses() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    clock.advance(5.0)
    advance_state_machine(runtime, _fixed_durations())
    assert runtime.state == DeviceState.RAISING


def test_transition_resamples_current_state_duration() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    clock.advance(5.0)
    advance_state_machine(runtime, _fixed_durations())
    # _fixed_durations: raising=(10, 10), so resampled value must be 10.0
    assert runtime.current_state_duration_s == 10.0


def test_transition_updates_state_entered_at_to_clock() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    clock.advance(5.0)
    advance_state_machine(runtime, _fixed_durations())
    assert runtime.state_entered_at_monotonic == 5.0


def test_full_cycle_returns_to_idle_and_increments_count() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    durations = _fixed_durations()

    # IDLE → RAISING
    clock.advance(5.0)
    advance_state_machine(runtime, durations)
    assert runtime.state == DeviceState.RAISING
    assert runtime.cycle_count == 0

    # RAISING → HOLDING
    # Not: advance_state_machine runtime'ı mutate eder ama mypy önceki assert'ten
    # gelen literal narrowing'i fonksiyon çağrısından sonra sıfırlamaz (bilinen mypy
    # kısıtı). Karşılaştırma runtime'da doğru; comparison-overlap false positive bastırılır.
    # İlk pragma'dan sonra mypy narrowing'i bıraktığı için sonraki assert'ler temiz.
    clock.advance(10.0)
    advance_state_machine(runtime, durations)
    assert runtime.state == DeviceState.HOLDING  # type: ignore[comparison-overlap]

    # HOLDING → LOWERING
    clock.advance(60.0)
    advance_state_machine(runtime, durations)
    assert runtime.state == DeviceState.LOWERING

    # LOWERING → IDLE (cycle complete)
    clock.advance(10.0)
    advance_state_machine(runtime, durations)
    assert runtime.state == DeviceState.IDLE
    assert runtime.cycle_count == 1


def test_compute_position_idle_returns_zero() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    assert compute_position(runtime, target_mm=5000.0) == 0.0


def test_compute_position_raising_returns_linear_progress() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.RAISING, duration=10.0)
    # 0 elapsed → 0 progress
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(0.0)
    clock.advance(5.0)
    # 5/10 elapsed → 50% progress
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(2500.0)
    clock.advance(5.0)
    # 10/10 elapsed → 100% progress
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(5000.0)


def test_compute_position_holding_returns_target() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.HOLDING, duration=60.0)
    clock.advance(30.0)
    assert compute_position(runtime, target_mm=5000.0) == 5000.0


def test_compute_position_lowering_returns_decreasing() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.LOWERING, duration=10.0)
    # 0 elapsed → still at target
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(5000.0)
    clock.advance(5.0)
    # 5/10 elapsed → 50% down
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(2500.0)
    clock.advance(5.0)
    # 10/10 elapsed → fully down
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(0.0)

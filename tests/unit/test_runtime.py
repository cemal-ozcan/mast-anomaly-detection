"""DeviceRuntimeState + state machine + position için unit testler."""
from __future__ import annotations

from random import Random

from simulator.config import DeviceState, StateDurations
from simulator.runtime import DeviceRuntimeState


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

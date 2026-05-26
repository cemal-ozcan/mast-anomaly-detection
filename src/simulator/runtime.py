"""Cihaz çalışma zamanı durumu, state machine geçişleri ve pozisyon hesabı."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random

from simulator.config import DeviceState, StateDurations


@dataclass
class DeviceRuntimeState:
    """Bir cihazın anlık çalışma durumu (mutable).

    Iterasyon 1'in DeviceConfig (immutable) ile karıştırılmamalı: DeviceConfig
    YAML'den okunan sabit yapılandırma; DeviceRuntimeState engine tarafından
    mutate edilen canlı durum.

    Invaryantlar (spec § 5):
        1. current_state_duration_s sadece state transition anında seçilir.
        2. clock() monotonic (default time.monotonic).
        3. rng per-device, seed'li → testler tekrarlanabilir.
        4. State geçişi tek yönlü: IDLE → RAISING → HOLDING → LOWERING → IDLE.
    """

    state: DeviceState
    state_entered_at_monotonic: float
    current_state_duration_s: float
    position_mm: float
    cycle_count: int
    rng: Random
    started_at_monotonic: float
    clock: Callable[[], float] = field(default=time.monotonic)

    @property
    def elapsed_in_state_s(self) -> float:
        """Mevcut state'e girişten beri geçen süre (saniye)."""
        return self.clock() - self.state_entered_at_monotonic

    @property
    def device_elapsed_s(self) -> float:
        """Cihaz engine'de spawn olduğundan beri geçen toplam süre (senaryolar için)."""
        return self.clock() - self.started_at_monotonic


_NEXT_STATE: dict[DeviceState, DeviceState] = {
    DeviceState.IDLE: DeviceState.RAISING,
    DeviceState.RAISING: DeviceState.HOLDING,
    DeviceState.HOLDING: DeviceState.LOWERING,
    DeviceState.LOWERING: DeviceState.IDLE,
}


def _state_bounds(state: DeviceState, durations: StateDurations) -> tuple[float, float]:
    """State için (min_s, max_s) süre aralığı döndür."""
    match state:
        case DeviceState.IDLE:
            return durations.idle
        case DeviceState.RAISING:
            return durations.raising
        case DeviceState.HOLDING:
            return durations.holding
        case DeviceState.LOWERING:
            return durations.lowering


def advance_state_machine(runtime: DeviceRuntimeState, durations: StateDurations) -> None:
    """State süresi dolduysa sıradaki state'e geç. Aksi halde no-op.

    Transition anında current_state_duration_s YENİDEN seçilir (invaryant 1).
    Tam IDLE→IDLE döngüsünde cycle_count artar.

    Args:
        runtime: Mutate edilecek runtime durumu.
        durations: State başına (min, max) süre aralıkları.
    """
    if runtime.elapsed_in_state_s < runtime.current_state_duration_s:
        return

    next_state = _NEXT_STATE[runtime.state]
    next_min, next_max = _state_bounds(next_state, durations)

    runtime.state = next_state
    runtime.current_state_duration_s = runtime.rng.uniform(next_min, next_max)
    runtime.state_entered_at_monotonic = runtime.clock()
    if next_state == DeviceState.IDLE:
        runtime.cycle_count += 1


def compute_position(runtime: DeviceRuntimeState, target_mm: float) -> float:
    """State ve elapsed'e göre lineer pozisyon hesabı.

    Saf fonksiyon — runtime'ı mutate etmez. Sensörler (özellikle mast_position
    Iterasyon 2b'de) bu fonksiyondan pozisyon okur.

    Args:
        runtime: Cihaz çalışma durumu.
        target_mm: Cihazın hedef yüksekliği (config'den).

    Returns:
        Şu anki pozisyon (mm). IDLE→0, RAISING→0..target lineer,
        HOLDING→target, LOWERING→target..0 lineer.
    """
    progress = min(1.0, runtime.elapsed_in_state_s / runtime.current_state_duration_s)
    match runtime.state:
        case DeviceState.IDLE:
            return 0.0
        case DeviceState.RAISING:
            return target_mm * progress
        case DeviceState.HOLDING:
            return target_mm
        case DeviceState.LOWERING:
            return target_mm * (1.0 - progress)

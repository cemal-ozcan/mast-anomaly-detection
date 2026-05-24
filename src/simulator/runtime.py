"""Cihaz çalışma zamanı durumu, state machine geçişleri ve pozisyon hesabı."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random

from simulator.config import DeviceState


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

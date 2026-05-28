"""Shared fixtures for statistical signature tests (Iter 4b refactor).

CountingClock + _ticking_sleep monkeypatch pattern: engine'in `asyncio.sleep`
çağrılarını no-op'lar AMA her tick'te bir saniyelik clock advance eder. Sonuç:
- Gerçek wall-clock beklemesi YOK (test mikrosaniyede koşar)
- `runtime.clock()` ardışık tick'lerde 1.0s ilerler (state machine doğal akar)
- `runtime.device_elapsed_s` + `runtime.elapsed_in_state_s` doğru değerler döner
- Senaryo aktivasyon pencereleri (start_after_s, duration_s) doğru çalışır

Iter 4a `test_mechanical_wear_signature.py` ve Iter 4b'nin 2 yeni signature
test'i aynı pattern'i kullanır → DRY.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


class CountingClock:
    """Her tick için 1 saniye ilerleyen test-only clock.

    Engine içinde `clock()` çağrıları sıralı yapılır; her tick'te `tick()`
    çağrılınca dahili sayaç 1.0 artar. `_ticking_sleep` monkeypatch'i
    `asyncio.sleep` her çağrısında `tick()` tetikler — böylece state machine
    ve senaryo elapsed'leri doğal akar.
    """

    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        return self._t

    def tick(self) -> None:
        self._t += 1.0


@pytest.fixture
def patched_engine_clock(monkeypatch: pytest.MonkeyPatch) -> CountingClock:
    """Engine'in `asyncio.sleep`'ini tick-advancing no-op ile monkeypatch eder.

    Returns:
        CountingClock instance — test bunu `run(clock=...)` parametresine geçer.
    """
    original_sleep = asyncio.sleep
    clock = CountingClock()

    async def _ticking_sleep(_s: float) -> None:
        clock.tick()
        await original_sleep(0)

    monkeypatch.setattr("simulator.engine.asyncio.sleep", _ticking_sleep)
    return clock

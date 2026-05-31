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
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pandas as pd

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


def _run_segment(
    monkeypatch: pytest.MonkeyPatch,
    clock: CountingClock,
    devices_path: Path,
    max_iterations: int,
    mock_publisher: object,
) -> None:
    """Engine'i bir fixture ile koşturur; publish_reading çağrıları paylaşılan mock_publisher'a birikir."""
    from simulator.engine import run

    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=devices_path,
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=max_iterations,
        seed=None,
        clock=clock,
    )


def _frame_from_publisher(mock_publisher: object) -> pd.DataFrame:
    """Birikmiş publish_reading çağrılarına PER-(device,sensor) monoton 1sn timestamp atayıp uzun-format DataFrame döndürür.

    Çağrı sırası korunur → önce koşan segment(ler) daha eski timestamp alır (baseline),
    son segment en yeni (current). state DeviceState StrEnum value'suna çevrilir.
    """
    from collections import defaultdict
    from datetime import UTC, datetime, timedelta

    import pandas as pd  # gövde içi import (build_detector_window deseni; TYPE_CHECKING dışı runtime kullanımı)

    from simulator.config import DeviceState

    base = datetime(2026, 5, 30, 0, 0, 0, tzinfo=UTC)
    counters: dict[tuple[str, str], int] = defaultdict(int)
    records: list[dict[str, object]] = []
    for c in mock_publisher.publish_reading.call_args_list:  # type: ignore[attr-defined]
        device_id = c.kwargs["device_id"]
        sensor = c.kwargs["sensor"]
        state = c.kwargs["state"]
        state_str = state.value if isinstance(state, DeviceState) else str(state)
        k = counters[(device_id, sensor)]
        counters[(device_id, sensor)] += 1
        ts = (base + timedelta(seconds=k)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        records.append(
            {
                "device_id": device_id,
                "timestamp": ts,
                "sensor": sensor,
                "state": state_str,
                "value": c.kwargs["value"],
            }
        )
    return pd.DataFrame(records, columns=["device_id", "timestamp", "sensor", "state", "value"])


def build_detector_window(
    monkeypatch: pytest.MonkeyPatch,
    clock: CountingClock,
    devices_path: Path,
    max_iterations: int,
) -> pd.DataFrame:
    """Engine'i tek fixture ile koşturup dedektör-hazır uzun-format pencere döndürür (kural imza testleri)."""
    from unittest.mock import MagicMock

    mock_publisher = MagicMock()
    _run_segment(monkeypatch, clock, devices_path, max_iterations, mock_publisher)
    return _frame_from_publisher(mock_publisher)


def build_statistical_window(
    monkeypatch: pytest.MonkeyPatch,
    clock: CountingClock,
    segments: list[tuple[Path, int]],
) -> pd.DataFrame:
    """Birden çok (fixture, iterations) segmentini SIRAYLA koşturup tek uzun-format pencere döndürür.

    İlk segment(ler) baseline (eski timestamp), son segment güncel (yeni timestamp) olur →
    statistical dedektör split_recent ile içeride ayırır. Tüm segmentler tek mock_publisher'a
    birikir (çağrı sırası = timestamp sırası). current_window_s'i son segmentin iterasyon
    sayısına (~saniye) eşitleyen test, son segmenti "current" yapar.

    NOT (off-by-one): current_window_s = son segment iterasyonu olduğunda split_recent cutoff'u
    son baseline örneğine denk gelir → "current"e 1 clean satır sızar; arıza tail (60-600 örnek)
    yanında önemsiz. Bu yüzden A/B testleri membership/scoped set assertion kullanır.

    Args:
        segments: [(devices_yaml_path, max_iterations), ...]. En az 2 önerilir (baseline + tail).

    Returns:
        [device_id, timestamp, sensor, state, value] kolonlu uzun pencere.
    """
    from unittest.mock import MagicMock

    mock_publisher = MagicMock()
    for devices_path, max_iterations in segments:
        _run_segment(monkeypatch, clock, devices_path, max_iterations, mock_publisher)
    return _frame_from_publisher(mock_publisher)

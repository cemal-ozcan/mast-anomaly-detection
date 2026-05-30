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


def build_detector_window(
    monkeypatch: pytest.MonkeyPatch,
    clock: CountingClock,
    devices_path: Path,
    max_iterations: int,
) -> pd.DataFrame:
    """Engine'i fixture ile koşturup dedektör-hazır uzun-format pencere döndürür.

    Publisher timestamp üretmediğinden (publish anında kendi üretir), collected
    reading'lere PER-SENSÖR monoton 1sn timestamp atanır (slope bar/dk doğru çıksın).
    state DeviceState StrEnum value'suna ("raising" vb.) çevrilir.

    Args:
        monkeypatch: pytest monkeypatch (publisher mock için).
        clock: patched_engine_clock fixture'ından CountingClock.
        devices_path: fixture device YAML yolu.
        max_iterations: engine tick sayısı.

    Returns:
        [device_id, timestamp, sensor, state, value] kolonlu pencere.
    """
    from collections import defaultdict
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    import pandas as pd

    from simulator.config import DeviceState
    from simulator.engine import run

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=devices_path,
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=max_iterations,
        seed=None,
        clock=clock,
    )

    base = datetime(2026, 5, 30, 0, 0, 0, tzinfo=UTC)
    counters: dict[tuple[str, str], int] = defaultdict(int)
    records: list[dict[str, object]] = []
    for c in mock_publisher.publish_reading.call_args_list:
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

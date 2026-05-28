"""run_device(...) direct async loop body testleri (Iter 3 asyncio)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from simulator.engine import run_device
from simulator.sensors import SENSOR_REGISTRY
from tests.unit.conftest import SIX_SENSOR_CONFIGS, make_device, make_runtime
from tests.unit.test_runtime import FakeClock


async def test_run_device_respects_max_iterations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_device max_iterations'a ulaşınca temiz biter (shutdown.set path Task 4'te ayrı test)."""
    device = make_device("d1", seed=42)
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in SIX_SENSOR_CONFIGS]
    runtime = make_runtime(device, clock=FakeClock(0.0))
    publisher = MagicMock()
    shutdown = asyncio.Event()

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    await run_device(
        device=device, runtime=runtime, sensors=sensors,
        publisher=publisher, tick_interval=1.0,
        shutdown_event=shutdown, max_iterations=3,
    )
    # 3 tick × 6 sensör = 18 publish
    assert publisher.publish_reading.call_count == 18


async def test_run_device_exits_when_shutdown_event_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """shutdown.set() çağrılınca run_device bir sonraki tick öncesinde çıkar."""
    device = make_device("d1", seed=42)
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in SIX_SENSOR_CONFIGS]
    runtime = make_runtime(device, clock=FakeClock(0.0))
    publisher = MagicMock()

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    shutdown = asyncio.Event()

    async def runner() -> None:
        await run_device(
            device=device, runtime=runtime, sensors=sensors,
            publisher=publisher, tick_interval=1.0,
            shutdown_event=shutdown, max_iterations=None,  # sonsuz, sadece shutdown ile bitsin
        )

    task = asyncio.create_task(runner())
    # Birkaç tick geçsin
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    shutdown.set()
    await asyncio.wait_for(task, timeout=1.0)

    assert publisher.publish_reading.call_count > 0


async def test_run_device_max_iterations_zero_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """max_iterations=0 → hiç tick yapmaz (loop body bir kez bile çalışmaz)."""
    device = make_device("d1", seed=42)
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in SIX_SENSOR_CONFIGS]
    runtime = make_runtime(device, clock=FakeClock(0.0))
    publisher = MagicMock()
    shutdown = asyncio.Event()

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    await run_device(
        device=device, runtime=runtime, sensors=sensors,
        publisher=publisher, tick_interval=1.0,
        shutdown_event=shutdown, max_iterations=0,
    )
    assert publisher.publish_reading.call_count == 0

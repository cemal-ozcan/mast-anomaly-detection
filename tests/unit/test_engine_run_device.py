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


async def test_run_device_applies_active_scenario_modify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAISING'de MechanicalWear aktifken motor_current değeri arttırılır.

    Senaryo penceresi engine_boot_at = 0'dan itibaren [0, 600) aralığında aktif;
    runtime RAISING state'inde başlatılır, scenario_elapsed_s = ramp_up_s = 60
    olacak şekilde clock advance edilir → factor = 1.0 * severity = 0.3.

    Bu test asyncio.sleep no-op + FakeClock manuel advance pattern'i kullanır.
    """
    import asyncio as _asyncio
    import random
    from unittest.mock import MagicMock

    from simulator.config import DeviceState, ScenarioWindow
    from simulator.engine import run_device
    from simulator.runtime import DeviceRuntimeState
    from simulator.sensors import SENSOR_REGISTRY
    from tests.unit.conftest import SIX_SENSOR_CONFIGS, make_device
    from tests.unit.test_runtime import FakeClock

    device = make_device(
        "d1",
        seed=42,
        scenarios=[
            ScenarioWindow(
                name="mechanical_wear",
                start_after_s=0.0,
                duration_s=600.0,
                params={"severity": 0.3, "ramp_up_s": 60},
            )
        ],
    )
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in SIX_SENSOR_CONFIGS]
    clock = FakeClock(60.0)  # device_elapsed_s = 60.0 → scenario_elapsed_s = 60.0
    # NOT: make_runtime kullanmıyoruz — current_state_duration_s'i ÇOK büyük yapıp
    # advance_state_machine transition tetiklemesin (RAISING korunur).
    runtime = DeviceRuntimeState(
        state=DeviceState.RAISING,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10000.0,  # transition tetiklenmez
        position_mm=2500.0,                 # RAISING ortası, sensor.compute için makul
        cycle_count=0,
        rng=random.Random(42),
        started_at_monotonic=0.0,
        clock=clock,
    )
    publisher = MagicMock()
    shutdown = _asyncio.Event()

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    await run_device(
        device=device, runtime=runtime, sensors=sensors,
        publisher=publisher, tick_interval=1.0,
        shutdown_event=shutdown, max_iterations=1,
    )

    # 1 tick × 6 sensor = 6 publish. motor_current değerini bul.
    motor_current_call = next(
        c for c in publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "motor_current"
    )
    # RAISING baseline 8.0; factor=0.3 → 8.0 * 1.3 = 10.4 (± noise std 0.1).
    # advance_state_machine RAISING state'i koruyabilir veya değiştirebilir; bu test
    # değerin baseline'dan ANLAMLI ölçüde yüksek olduğunu doğrular (10.4 ± 0.3 σ).
    value = motor_current_call.kwargs["value"]
    assert 10.0 < value < 11.0, f"Beklenen ~10.4, alınan {value}"


async def test_run_device_no_scenario_keeps_clean_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """device.scenarios=[] → fault.modify zinciri YOK → değer yalnızca sensor.compute + noise."""
    import asyncio as _asyncio
    from unittest.mock import MagicMock

    from simulator.engine import run_device
    from simulator.sensors import SENSOR_REGISTRY
    from tests.unit.conftest import SIX_SENSOR_CONFIGS, make_device, make_runtime
    from tests.unit.test_runtime import FakeClock

    device = make_device("d1", seed=42)  # scenarios default = []
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in SIX_SENSOR_CONFIGS]
    runtime = make_runtime(device, clock=FakeClock(0.0), started_at=0.0)
    publisher = MagicMock()
    shutdown = _asyncio.Event()

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    await run_device(
        device=device, runtime=runtime, sensors=sensors,
        publisher=publisher, tick_interval=1.0,
        shutdown_event=shutdown, max_iterations=1,
    )

    motor_current_call = next(
        c for c in publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "motor_current"
    )
    value = motor_current_call.kwargs["value"]
    # IDLE baseline 0.5, noise std 0.1 → ~0.5 ± 0.3 σ
    assert 0.0 < value < 1.0, f"Beklenen ~0.5 (IDLE baseline), alınan {value}"

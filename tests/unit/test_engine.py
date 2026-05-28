"""Engine 6 sensör entegrasyonu için unit testler (Iter 2b + Iter 3 asyncio)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulator.config import DeviceState
from simulator.engine import run
from tests.unit.test_runtime import FakeClock

FIXTURES = Path(__file__).parent.parent / "fixtures"


_EXPECTED_SENSORS = {
    "motor_current",
    "motor_voltage",
    "hydraulic_pressure",
    "motor_temperature",
    "mast_position",
    "vibration",
}


def test_run_publishes_all_six_sensors_per_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Her tick'te 6 sensör için publish_reading çağrılır (6 mesaj/tick)."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    _original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: _original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=2,
        seed=42,
        clock=clock,
    )

    # 2 tick × 6 sensör = 12 publish çağrısı
    assert mock_publisher.publish_reading.call_count == 12

    # Her tick'te 6 farklı sensör adı yayınlandı
    first_tick_sensors = {
        c.kwargs["sensor"]
        for c in mock_publisher.publish_reading.call_args_list[:6]
    }
    assert first_tick_sensors == _EXPECTED_SENSORS


def test_run_publishes_state_field_idle_when_clock_not_advanced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """clock advance edilmediğinde tüm sensörler IDLE state ile publish edilir."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    _original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: _original_sleep(0))

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=1,
        seed=42,
        clock=FakeClock(0.0),
    )

    for call in mock_publisher.publish_reading.call_args_list:
        assert call.kwargs["state"] == DeviceState.IDLE


def test_run_rejects_duplicate_device_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aynı device.id iki kez → ValueError 'unique' (Iter 3 _validate_devices)."""
    devices_yaml = tmp_path / "devices.yaml"
    six_sensors_block = """
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}"""
    sd_block = """
    target_height_mm: 5000
    state_durations:
      idle: [5, 30]
      raising: [10, 60]
      holding: [60, 300]
      lowering: [10, 60]"""
    devices_yaml.write_text(f"""
devices:
  - id: device_001
    type: telescopic_mast_v1{sd_block}{six_sensors_block}
  - id: device_001
    type: telescopic_mast_v1{sd_block}{six_sensors_block}
""")
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    _original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: _original_sleep(0))

    with pytest.raises(ValueError, match="unique"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_rejects_missing_required_sensor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6 sensörün hepsi zorunlu — vibration eksikse ValueError."""
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text("""
devices:
  - id: device_001
    type: telescopic_mast_v1
    target_height_mm: 5000
    state_durations:
      idle: [5, 30]
      raising: [10, 60]
      holding: [60, 300]
      lowering: [10, 60]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
""")
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    _original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: _original_sleep(0))

    with pytest.raises(ValueError, match="eksik.*vibration"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_rejects_extra_unknown_sensor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Set tam olmalı — bilinmeyen sensör fazla → ValueError."""
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text("""
devices:
  - id: device_001
    type: telescopic_mast_v1
    target_height_mm: 5000
    state_durations:
      idle: [5, 30]
      raising: [10, 60]
      holding: [60, 300]
      lowering: [10, 60]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
      - {name: gyroscope,          unit: deg,     baseline: 0,    noise_std: 0.1}
""")
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    _original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: _original_sleep(0))

    with pytest.raises(ValueError, match="fazla.*gyroscope"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


async def test_run_device_respects_max_iterations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_device max_iterations'a ulaşınca temiz biter (shutdown.set path Task 4'te ayrı test)."""
    import asyncio as _asyncio
    import random as _random

    from simulator.config import DeviceState, SensorConfig, StateDurations
    from simulator.engine import run_device
    from simulator.runtime import DeviceRuntimeState
    from simulator.sensors import SENSOR_REGISTRY

    # Sensor config + device-equivalent fixture
    sensor_cfgs = [
        SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1),
        SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2),
        SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0),
        SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5),
        SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0),
        SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01),
    ]
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in sensor_cfgs]

    from simulator.config import DeviceConfig
    device = DeviceConfig(
        id="d1",
        type="telescopic_mast_v1",
        sensors=sensor_cfgs,
        state_durations=StateDurations(
            idle=(5.0, 5.0), raising=(10.0, 10.0),
            holding=(60.0, 60.0), lowering=(10.0, 10.0),
        ),
        target_height_mm=5000.0,
        seed=42,
    )

    clock = FakeClock(0.0)
    rng = _random.Random(42)
    runtime = DeviceRuntimeState(
        state=DeviceState.IDLE,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=rng.uniform(*device.state_durations.idle),
        position_mm=0.0,
        cycle_count=0,
        rng=rng,
        started_at_monotonic=0.0,
        clock=clock,
    )

    publisher = MagicMock()
    shutdown = _asyncio.Event()

    # asyncio.sleep no-op
    original_sleep = _asyncio.sleep
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
    import asyncio as _asyncio
    import random as _random

    from simulator.config import DeviceConfig, DeviceState, SensorConfig, StateDurations
    from simulator.engine import run_device
    from simulator.runtime import DeviceRuntimeState
    from simulator.sensors import SENSOR_REGISTRY

    sensor_cfgs = [
        SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1),
        SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2),
        SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0),
        SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5),
        SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0),
        SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01),
    ]
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in sensor_cfgs]
    device = DeviceConfig(
        id="d1", type="telescopic_mast_v1", sensors=sensor_cfgs,
        state_durations=StateDurations(
            idle=(5.0, 5.0), raising=(10.0, 10.0),
            holding=(60.0, 60.0), lowering=(10.0, 10.0),
        ),
        target_height_mm=5000.0, seed=42,
    )
    rng = _random.Random(42)
    runtime = DeviceRuntimeState(
        state=DeviceState.IDLE, state_entered_at_monotonic=0.0,
        current_state_duration_s=rng.uniform(*device.state_durations.idle),
        position_mm=0.0, cycle_count=0, rng=rng,
        started_at_monotonic=0.0, clock=FakeClock(0.0),
    )
    publisher = MagicMock()

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    shutdown = _asyncio.Event()

    async def runner() -> None:
        await run_device(
            device=device, runtime=runtime, sensors=sensors,
            publisher=publisher, tick_interval=1.0,
            shutdown_event=shutdown, max_iterations=None,  # sonsuz, sadece shutdown ile bitsin
        )

    task = _asyncio.create_task(runner())
    # Birkaç tick geçsin
    await _asyncio.sleep(0)
    await _asyncio.sleep(0)
    shutdown.set()
    await _asyncio.wait_for(task, timeout=1.0)

    assert publisher.publish_reading.call_count > 0


def test_run_spawns_all_devices_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """2 cihaz fixture'ı: her cihaz 2 tick × 6 sensör = 12 publish, toplam 24."""
    import asyncio as _asyncio

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=2,
        seed=None,  # YAML'deki per-device seed kullan
        clock=clock,
    )

    # 2 cihaz × 2 tick × 6 sensör = 24 publish
    assert mock_publisher.publish_reading.call_count == 24

    # Her iki cihaz da yayın yaptı (device_id alanı kontrolü)
    device_ids = {c.kwargs["device_id"] for c in mock_publisher.publish_reading.call_args_list}
    assert device_ids == {"device_001", "device_002"}

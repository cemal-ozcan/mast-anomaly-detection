"""Engine.run() top-level smoke + validation-via-run testleri (Iter 2b + Iter 3)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulator.config import DeviceState
from simulator.engine import run
from tests.unit.conftest import FIXTURES
from tests.unit.test_runtime import FakeClock

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

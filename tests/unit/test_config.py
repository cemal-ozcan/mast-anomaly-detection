from pathlib import Path

import pytest

from simulator.config import (
    DeviceConfig,
    EngineConfig,
    MQTTConfig,
    SensorConfig,
    load_devices,
    load_engine_config,
    load_mqtt_config,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_load_mqtt_config() -> None:
    cfg = load_mqtt_config(FIXTURES / "mqtt_minimal.yaml")
    assert isinstance(cfg, MQTTConfig)
    assert cfg.host == "localhost"
    assert cfg.port == 1883
    assert cfg.client_id_prefix == "mast-anomaly"
    assert cfg.keepalive == 60
    assert cfg.telemetry_prefix == "telemetry"
    assert cfg.qos == 1


def test_load_devices_returns_list_of_device_configs() -> None:
    devices = load_devices(FIXTURES / "devices_minimal.yaml")
    assert len(devices) == 1
    device = devices[0]
    assert isinstance(device, DeviceConfig)
    assert device.id == "device_001"
    assert device.type == "telescopic_mast_v1"
    assert len(device.sensors) == 6
    # Check first sensor (motor_current)
    sensor = device.sensors[0]
    assert isinstance(sensor, SensorConfig)
    assert sensor.name == "motor_current"
    assert sensor.unit == "A"
    assert sensor.baseline == 0.5
    assert sensor.noise_std == 0.1
    # Check all 6 required sensors are present
    sensor_names = {s.name for s in device.sensors}
    expected_names = {
        "motor_current",
        "motor_voltage",
        "hydraulic_pressure",
        "motor_temperature",
        "mast_position",
        "vibration",
    }
    assert sensor_names == expected_names


def test_load_engine_config() -> None:
    cfg = load_engine_config(FIXTURES / "simulator_minimal.yaml")
    assert isinstance(cfg, EngineConfig)
    assert cfg.tick_hz == 1.0
    assert cfg.log_level == "INFO"


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_mqtt_config(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises_value_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("broker:\n  host: localhost\n  port: not_a_number\n")
    with pytest.raises(ValueError):
        load_mqtt_config(bad)


def test_load_devices_parses_state_durations_as_tuples() -> None:
    devices = load_devices(FIXTURES / "devices_minimal.yaml")
    device = devices[0]
    assert device.state_durations.idle == (5.0, 30.0)
    assert device.state_durations.raising == (10.0, 60.0)
    assert device.state_durations.holding == (60.0, 300.0)
    assert device.state_durations.lowering == (10.0, 60.0)


def test_load_devices_includes_target_height_and_seed() -> None:
    devices = load_devices(FIXTURES / "devices_minimal.yaml")
    device = devices[0]
    assert device.target_height_mm == 5000.0
    assert device.seed == 42


def test_load_devices_rejects_missing_state_durations(tmp_path: Path) -> None:
    bad = tmp_path / "devices.yaml"
    bad.write_text(
        """
devices:
  - id: device_001
    type: telescopic_mast_v1
    target_height_mm: 5000
    sensors:
      - {name: motor_current, unit: A, baseline: 0.5, noise_std: 0.1}
"""
    )
    with pytest.raises(ValueError, match="state_durations"):
        load_devices(bad)


def test_device_state_is_str_enum() -> None:
    import json

    from simulator.config import DeviceState

    # StrEnum üyeleri string değeriyle tanımlı.
    assert DeviceState.IDLE.value == "idle"
    assert DeviceState.RAISING.value == "raising"
    assert DeviceState.HOLDING.value == "holding"
    assert DeviceState.LOWERING.value == "lowering"
    # StrEnum'un asıl faydası: JSON'a .value çağırmadan string olarak serialize olur.
    assert json.dumps({"s": DeviceState.IDLE}) == '{"s": "idle"}'


def test_load_devices_with_no_scenarios_field_returns_empty_list(tmp_path: Path) -> None:
    """scenarios alanı YAML'de yoksa DeviceConfig.scenarios == []."""
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text("""
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
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
""")
    devices = load_devices(devices_yaml)
    assert devices[0].scenarios == []


def test_load_devices_with_scenarios_block_parses_window(tmp_path: Path) -> None:
    """scenarios: bloğu ScenarioWindow listesine parse edilir."""
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text("""
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
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
    scenarios:
      - name: mechanical_wear
        start_after_s: 120
        duration_s: 600
        params:
          severity: 0.25
          ramp_up_s: 300
""")
    from simulator.config import ScenarioWindow

    devices = load_devices(devices_yaml)
    assert len(devices[0].scenarios) == 1
    window = devices[0].scenarios[0]
    assert isinstance(window, ScenarioWindow)
    assert window.name == "mechanical_wear"
    assert window.start_after_s == 120.0
    assert window.duration_s == 600.0
    assert window.params == {"severity": 0.25, "ramp_up_s": 300}


def test_scenario_window_is_frozen_dataclass() -> None:
    """ScenarioWindow frozen — params Mapping olarak saklanır, mutate edilemez."""
    from dataclasses import FrozenInstanceError

    from simulator.config import ScenarioWindow

    w = ScenarioWindow(
        name="mechanical_wear",
        start_after_s=0.0,
        duration_s=100.0,
        params={"severity": 0.2, "ramp_up_s": 300},
    )
    with pytest.raises(FrozenInstanceError):
        w.name = "other"  # type: ignore[misc]

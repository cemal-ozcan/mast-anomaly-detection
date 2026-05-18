from pathlib import Path

import pytest

from src.simulator.config import (
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
    assert len(device.sensors) == 1
    sensor = device.sensors[0]
    assert isinstance(sensor, SensorConfig)
    assert sensor.name == "motor_current"
    assert sensor.unit == "A"
    assert sensor.baseline == 0.5
    assert sensor.noise_std == 0.1


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

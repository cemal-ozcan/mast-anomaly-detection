from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulator.engine import run

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_run_publishes_configured_iteration_count(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_publisher = MagicMock()
    captured: dict[str, object] = {}

    def fake_publisher_factory(config: object) -> MagicMock:
        captured["config"] = config
        return mock_publisher

    monkeypatch.setattr("simulator.engine._make_publisher", fake_publisher_factory)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=42,
    )

    assert mock_publisher.connect.call_count == 1
    assert mock_publisher.publish_reading.call_count == 3
    assert mock_publisher.close.call_count == 1

    for call in mock_publisher.publish_reading.call_args_list:
        kwargs = call.kwargs
        assert kwargs["device_id"] == "device_001"
        assert kwargs["sensor"] == "motor_current"
        assert kwargs["unit"] == "A"
        assert isinstance(kwargs["value"], float)


def test_run_rejects_multiple_devices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text(
        """
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
      - {name: motor_current, unit: A, baseline: 0.5, noise_std: 0.1}
  - id: device_002
    type: telescopic_mast_v1
    target_height_mm: 5000
    state_durations:
      idle: [5, 30]
      raising: [10, 60]
      holding: [60, 300]
      lowering: [10, 60]
    sensors:
      - {name: motor_current, unit: A, baseline: 0.5, noise_std: 0.1}
"""
    )
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="exactly 1 device"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_rejects_unsupported_sensor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text(
        """
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
      - {name: hydraulic_pressure, unit: bar, baseline: 10, noise_std: 2}
"""
    )
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="motor_current"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )

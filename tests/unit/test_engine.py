"""Engine state machine entegrasyonu için unit testler."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulator.config import DeviceState
from simulator.engine import run
from tests.unit.test_runtime import FakeClock

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_run_publishes_with_state_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """publish_reading her tick'te runtime.state ile çağrılır (StrEnum → string)."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=42,
        clock=clock,
    )

    assert mock_publisher.publish_reading.call_count == 3
    for call in mock_publisher.publish_reading.call_args_list:
        kwargs = call.kwargs
        # state IDLE çünkü clock advance edilmedi, hala ilk state'te
        assert kwargs["state"] == DeviceState.IDLE


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
      - {name: unknown_sensor, unit: X, baseline: 10, noise_std: 2}
"""
    )
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(KeyError, match="unknown_sensor"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_publishes_noisy_value_around_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine gürültüyü ekler (spec § 8). IDLE'da değer config.baseline (0.5) civarı.

    clock advance edilmediği için state IDLE kalır; motor_current.compute() 0.5 döner,
    engine üzerine gauss(0, 0.1) ekler → değer 0.5 ± birkaç sigma.
    """
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=20,
        seed=42,
        clock=clock,
    )

    values = [c.kwargs["value"] for c in mock_publisher.publish_reading.call_args_list]
    # IDLE baseline 0.5, noise_std 0.1. 20 örnek → ortalama ~0.5 (3-sigma tolerans geniş).
    mean = sum(values) / len(values)
    assert 0.2 < mean < 0.8
    # Gürültü gerçekten ekleniyor: tüm değerler birebir aynı OLMAMALI.
    assert len(set(values)) > 1


def test_run_iterates_all_sensors_per_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine her tick'te tüm sensörler için publish_reading çağırır."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=2,
        seed=42,
        clock=clock,
    )

    # devices_minimal.yaml'da Iter 2a sonu 1 sensör (motor_current).
    # 2 tick × 1 sensör = 2 publish_reading çağrısı bekleniyor.
    assert mock_publisher.publish_reading.call_count == 2
    # Sensör adları config'deki sensör listesindeki sırada yayınlanır.
    sensor_names = [c.kwargs["sensor"] for c in mock_publisher.publish_reading.call_args_list]
    assert sensor_names == ["motor_current", "motor_current"]

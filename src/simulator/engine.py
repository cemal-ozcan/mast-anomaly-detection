"""Iterasyon 1 engine: tek cihaz, tek sensör, 1 Hz blocking loop."""
from __future__ import annotations

import random
import signal
import time
from pathlib import Path
from types import FrameType

from loguru import logger

from simulator.config import (
    DeviceConfig,
    DeviceState,
    MQTTConfig,
    load_devices,
    load_engine_config,
    load_mqtt_config,
)
from simulator.publisher import MQTTPublisher
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.motor_current import MotorCurrentSensor


def _make_publisher(config: MQTTConfig) -> MQTTPublisher:
    """Test edilebilirlik için factory; monkeypatch ile değiştirilebilir.

    Args:
        config: MQTT konfigürasyonu.

    Returns:
        MQTTPublisher örneği.
    """
    return MQTTPublisher(config)


def _validate_iteration1_constraints(devices: list[DeviceConfig]) -> DeviceConfig:
    """Iterasyon 1 kısıtlamalarını doğrula: tek cihaz, motor_current sensörü.

    Args:
        devices: Cihaz konfigürasyonları listesi.

    Returns:
        Tek cihaz (DeviceConfig).

    Raises:
        ValueError: Cihaz sayısı != 1 veya sensör != motor_current ise.
    """
    if len(devices) != 1:
        raise ValueError(
            f"Iterasyon 1 exactly 1 device destekliyor, alınan: {len(devices)}"
        )
    device = devices[0]
    if len(device.sensors) != 1 or device.sensors[0].name != "motor_current":
        raise ValueError(
            "Iterasyon 1: cihaz tam olarak bir 'motor_current' sensörü içermeli"
        )
    return device


def run(
    mqtt_config_path: Path = Path("config/mqtt.yaml"),
    devices_path: Path = Path("config/devices.yaml"),
    engine_config_path: Path = Path("config/simulator.yaml"),
    max_iterations: int | None = None,
    seed: int | None = None,
) -> None:
    """Engine'i başlatır. max_iterations=None → SIGINT/SIGTERM gelene dek sonsuz.

    max_iterations verilirse testler için sınırlı yinelemeler çalışır.
    seed verilirse RNG deterministik (test/regresyon için).

    Args:
        mqtt_config_path: MQTT konfigürasyonu dosya yolu.
        devices_path: Cihaz konfigürasyonu dosya yolu.
        engine_config_path: Engine konfigürasyonu dosya yolu.
        max_iterations: Sonsuz döngüyü sonlandırmak için maksimum yineleme sayısı.
                       None ise SIGINT/SIGTERM sinyali gelene kadar çalışır.
        seed: RNG için seed değeri. Test/regresyon için deterministiklik sağlar.

    Raises:
        ValueError: Iterasyon 1 kısıtlamalarına uymayan konfigürasyonlar.
    """
    mqtt_config = load_mqtt_config(mqtt_config_path)
    devices = load_devices(devices_path)
    engine_config = load_engine_config(engine_config_path)
    logger.level(engine_config.log_level)

    device = _validate_iteration1_constraints(devices)
    sensor_config = device.sensors[0]
    rng = random.Random(seed) if seed is not None else random.Random()
    sensor = MotorCurrentSensor(sensor_config)

    publisher = _make_publisher(mqtt_config)
    publisher.connect()

    stop = False

    def _shutdown(signum: int, _frame: FrameType | None) -> None:
        nonlocal stop
        logger.info("Shutdown sinyali alındı: {}", signum)
        stop = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    tick_interval = 1.0 / engine_config.tick_hz
    iterations = 0
    try:
        # Iterasyon 1: minimal state (IDLE sadece) + deterministik Gauss gürültü
        # Task 8'de state machine entegrasyonu ve engine refactor yapılacak.
        runtime = DeviceRuntimeState(
            state=DeviceState.IDLE,
            state_entered_at_monotonic=0.0,
            current_state_duration_s=0.0,
            position_mm=0.0,
            cycle_count=0,
            rng=rng,
            started_at_monotonic=time.monotonic(),
        )
        while not stop:
            # compute() saf sensor değeri (gürültü yok); gürültü engine'de (Task 8).
            base_value = sensor.compute(runtime, position_mm=0.0)
            # Iterasyon 1: Gauss gürültüsü burada ekleniyor (Task 8'de spec'e uygun hale getirilecek)
            value = base_value + rng.gauss(0.0, sensor_config.noise_std)
            publisher.publish_reading(
                device_id=device.id,
                sensor=sensor_config.name,
                value=value,
                unit=sensor_config.unit,
                state="idle",
            )
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            time.sleep(tick_interval)
    finally:
        publisher.close()

"""Iterasyon 2a engine: tek cihaz, state machine ile motor_current yayını."""
from __future__ import annotations

import random
import signal
import time
from collections.abc import Callable
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
from simulator.runtime import (
    DeviceRuntimeState,
    advance_state_machine,
    compute_position,
)
from simulator.sensors import SENSOR_REGISTRY
from simulator.sensors.base import BaseSensor


def _make_publisher(config: MQTTConfig) -> MQTTPublisher:
    """Test edilebilirlik için factory; monkeypatch ile değiştirilebilir."""
    return MQTTPublisher(config)


_REQUIRED_SENSORS = frozenset({
    "motor_current",
    "motor_voltage",
    "hydraulic_pressure",
    "motor_temperature",
    "mast_position",
    "vibration",
})


def _validate_iteration2b_constraints(devices: list[DeviceConfig]) -> DeviceConfig:
    """Iterasyon 2b kısıtlamaları: tam 1 cihaz + tam 6 sensör seti."""
    if len(devices) != 1:
        raise ValueError(
            f"Iterasyon 2b exactly 1 device destekliyor, alınan: {len(devices)}"
        )
    device = devices[0]
    names = {s.name for s in device.sensors}
    if names != _REQUIRED_SENSORS:
        parts: list[str] = []
        missing = _REQUIRED_SENSORS - names
        extra = names - _REQUIRED_SENSORS
        if missing:
            parts.append(f"eksik: {sorted(missing)}")
        if extra:
            parts.append(f"fazla: {sorted(extra)}")
        raise ValueError(
            f"Iterasyon 2b: cihaz tam olarak 6 sensör içermeli ({', '.join(parts)})"
        )
    return device


def run(
    mqtt_config_path: Path = Path("config/mqtt.yaml"),
    devices_path: Path = Path("config/devices.yaml"),
    engine_config_path: Path = Path("config/simulator.yaml"),
    max_iterations: int | None = None,
    seed: int | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Engine'i başlatır. State machine sürer, sensör compute() çağırır.

    Args:
        mqtt_config_path: MQTT YAML config.
        devices_path: Cihaz YAML config.
        engine_config_path: Engine YAML config.
        max_iterations: None → SIGINT/SIGTERM gelene dek sonsuz.
        seed: RNG seed; verilmezse YAML'deki device.seed kullanılır.
        clock: Saat kaynağı (DI). Test'lerde FakeClock inject edilebilir.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: Config geçersizse veya Iterasyon 2a kısıtlamaları ihlal edilmişse.
        KeyError: SENSOR_REGISTRY'de bilinmeyen sensör adı.
    """
    mqtt_config = load_mqtt_config(mqtt_config_path)
    devices = load_devices(devices_path)
    engine_config = load_engine_config(engine_config_path)
    logger.level(engine_config.log_level)

    device = _validate_iteration2b_constraints(devices)

    # Sensörleri config sırasıyla inşa et (Iter 2b: list-based, 1+ sensör).
    sensors: list[BaseSensor] = [
        SENSOR_REGISTRY[sc.name](sc) for sc in device.sensors
    ]

    rng = random.Random(seed if seed is not None else device.seed)
    now = clock()
    initial_duration = rng.uniform(*device.state_durations.idle)
    runtime = DeviceRuntimeState(
        state=DeviceState.IDLE,
        state_entered_at_monotonic=now,
        current_state_duration_s=initial_duration,
        position_mm=0.0,
        cycle_count=0,
        rng=rng,
        started_at_monotonic=now,
        clock=clock,
    )

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
        while not stop:
            advance_state_machine(runtime, device.state_durations)
            runtime.position_mm = compute_position(runtime, device.target_height_mm)

            for sensor in sensors:
                clean_value = sensor.compute(runtime, runtime.position_mm)
                noisy_value = clean_value + rng.gauss(0.0, sensor.config.noise_std)
                publisher.publish_reading(
                    device_id=device.id,
                    sensor=sensor.config.name,
                    value=noisy_value,
                    unit=sensor.config.unit,
                    state=runtime.state,  # StrEnum → JSON serializable
                )
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            time.sleep(tick_interval)
    finally:
        publisher.close()

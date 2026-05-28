"""Simulator engine: cihaz config'lerini validate eder, state machine + N sensör asyncio loop'unu sürer (Iter 3)."""
from __future__ import annotations

import asyncio
import random
import signal
import time
from collections.abc import Callable
from pathlib import Path

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


def _validate_devices(devices: list[DeviceConfig]) -> None:
    """Iter 3 validasyonu: N cihaz, her biri tam 6 sensör seti, unique ID'ler.

    Args:
        devices: YAML'den yüklenmiş cihaz config'leri.

    Raises:
        ValueError: Liste boşsa, herhangi bir cihazda 6 sensör setinden sapma varsa,
            veya device.id değerleri arasında duplikasyon varsa.

    Aynı `seed` birden fazla cihazda görülürse hata DEĞİL, WARN log basılır
    (spec § 3 Iter 3 bitti kriteri #2 — aynı seed regresyon testi meşru kullanım).
    """
    if len(devices) < 1:
        raise ValueError("Iterasyon 3: en az 1 cihaz tanımlı olmalı")

    # ID uniqueness
    ids = [d.id for d in devices]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(
            f"Iterasyon 3: device.id değerleri unique olmalı (duplikatlar: {dupes})"
        )

    # Her cihazda tam 6-sensör seti
    for device in devices:
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
                f"Iterasyon 3: cihaz '{device.id}' tam 6-sensör seti içermeli "
                f"({', '.join(parts)})"
            )

    # Same-seed → WARN (hata değil)
    seeds = [d.seed for d in devices if d.seed is not None]
    duplicated_seeds = sorted({s for s in seeds if seeds.count(s) > 1})
    if duplicated_seeds:
        logger.warning(
            "Birden fazla cihazda aynı seed kullanılıyor: {} — "
            "bu deterministik regresyon senaryosu için meşru, ama production'da "
            "cihazların aynı değer dizilerini üreteceğini unutmayın.",
            duplicated_seeds,
        )


async def run_device(
    device: DeviceConfig,
    runtime: DeviceRuntimeState,
    sensors: list[BaseSensor],
    publisher: MQTTPublisher,
    tick_interval: float,
    shutdown_event: asyncio.Event,
    max_iterations: int | None = None,
) -> None:
    """Tek cihazın asyncio tick döngüsü. Spec § 8 tick akışı asyncio versiyonu.

    Args:
        device: Cihaz config'i (id, sensors, state_durations, target_height_mm).
        runtime: Önceden başlatılmış `DeviceRuntimeState` (clock + started_at_monotonic
            engine'de set edilmiş). Tüm randomness `runtime.rng` üzerinden akar —
            engine-side noise dahil bu cihaza ait tek `random.Random(seed)` kaynağıdır
            (spec § 5 invaryantı).
        sensors: Önceden registry'den inşa edilmiş sensor instance listesi.
        publisher: Paylaşılan MQTTPublisher (N cihazlı engine'de aynı instance).
        tick_interval: Saniye cinsinden tick periyodu (engine_config.tick_hz'den).
        shutdown_event: Set edildiğinde döngü tick başında çıkar (SIGINT/SIGTERM
            veya test-side .set()).
        max_iterations: None → shutdown_event'e kadar sonsuz. 0 → hiç tick yapmaz
            (erken çıkış). N → tam N tick yayını yapar ve temiz çıkar.

    Note:
        Bu fonksiyon kendi engine'i başlatmaz, kendi publisher'ını connect etmez —
        bunları engine.run() / _amain orkestre eder. Burada sadece tick gövdesi var.
    """
    iterations = 0
    while not shutdown_event.is_set():
        if max_iterations is not None and iterations >= max_iterations:
            return
        advance_state_machine(runtime, device.state_durations)
        runtime.position_mm = compute_position(runtime, device.target_height_mm)

        for sensor in sensors:
            clean_value = sensor.compute(runtime, runtime.position_mm)
            noisy_value = clean_value + runtime.rng.gauss(0.0, sensor.config.noise_std)
            publisher.publish_reading(
                device_id=device.id,
                sensor=sensor.config.name,
                value=noisy_value,
                unit=sensor.config.unit,
                state=runtime.state,
            )
        iterations += 1
        await asyncio.sleep(tick_interval)


def run(
    mqtt_config_path: Path = Path("config/mqtt.yaml"),
    devices_path: Path = Path("config/devices.yaml"),
    engine_config_path: Path = Path("config/simulator.yaml"),
    max_iterations: int | None = None,
    seed: int | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Engine entry — asyncio.run(_amain) sarmalayıcısı.

    Args:
        mqtt_config_path: MQTT YAML config.
        devices_path: Cihaz YAML config.
        engine_config_path: Engine YAML config.
        max_iterations: None → SIGINT/SIGTERM (asyncio add_signal_handler ile
            shutdown Event set edilir) gelene dek sonsuz. Int verilirse o kadar
            tick sonra temiz çıkış.
        seed: RNG seed; verilmezse YAML'deki device.seed kullanılır. Multi-device
            durumunda bu parametre verilirse TÜM cihazlara aynı seed gider — same-seed
            WARN tetiklenir; deterministik regresyon senaryosu için per-device YAML
            seed kullanmak tercih edilir.
        clock: Saat kaynağı (DI). Test'lerde FakeClock inject edilebilir.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: Config geçersizse veya _validate_devices kısıtlamaları ihlal edilmişse
            (boş cihaz listesi, duplikat device.id, eksik/fazla sensör).
        KeyError: SENSOR_REGISTRY'de bilinmeyen sensör adı.

    Note (Iter 3):
        Tüm cihazlar paralel `asyncio.create_task(run_device(...))` ile spawn edilir
        ve `asyncio.gather(*tasks)` ile beklenir. Publisher ve `engine_boot_at`
        paylaşılır; her cihazın kendi `DeviceRuntimeState` + `random.Random(seed)`
        + sensor instance listesi vardır (cihazlar arası shared state YOK).
        Sinyal yönetimi: SIGINT/SIGTERM `loop.add_signal_handler` ile asyncio.Event
        set eder; `run_device` tick başında `is_set()` kontrolüyle temiz çıkar.
        Windows'ta `NotImplementedError` yakalanır (KeyboardInterrupt asyncio.run
        tarafından sarmalanır, `publisher.close()` finally bloğunda yine çalışır).
    """
    mqtt_config = load_mqtt_config(mqtt_config_path)
    devices = load_devices(devices_path)
    engine_config = load_engine_config(engine_config_path)
    logger.level(engine_config.log_level)

    _validate_devices(devices)

    engine_boot_at = clock()  # Tüm cihazlar için ortak referans (spec § 5)
    tick_interval = 1.0 / engine_config.tick_hz

    publisher = _make_publisher(mqtt_config)
    publisher.connect()

    # Her cihaz için: sensors + rng + runtime üret (cihazlar arasında shared state YOK).
    # rng `runtime.rng` üzerinden taşınır — run_device içinde noise da oradan akar.
    device_setups: list[tuple[DeviceConfig, DeviceRuntimeState, list[BaseSensor]]] = []
    for device in devices:
        device_sensors: list[BaseSensor] = [
            SENSOR_REGISTRY[sc.name](sc) for sc in device.sensors
        ]
        effective_seed = seed if seed is not None else device.seed
        device_rng = random.Random(effective_seed)
        initial_duration = device_rng.uniform(*device.state_durations.idle)
        device_runtime = DeviceRuntimeState(
            state=DeviceState.IDLE,
            state_entered_at_monotonic=engine_boot_at,
            current_state_duration_s=initial_duration,
            position_mm=0.0,
            cycle_count=0,
            rng=device_rng,
            started_at_monotonic=engine_boot_at,
            clock=clock,
        )
        device_setups.append((device, device_runtime, device_sensors))

    async def _amain() -> None:
        shutdown = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _set_shutdown(signum: int) -> None:
            logger.info("Shutdown sinyali alındı: {}", signum)
            shutdown.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _set_shutdown, sig)
            except NotImplementedError:
                # Windows asyncio signal handlers desteklemez; outer try/except
                # KeyboardInterrupt yakalayıp clean log basacak.
                logger.warning("add_signal_handler {} desteklenmiyor (Windows?)", sig)

        tasks = [
            asyncio.create_task(
                run_device(
                    device=d,
                    runtime=r,
                    sensors=s,
                    publisher=publisher,
                    tick_interval=tick_interval,
                    shutdown_event=shutdown,
                    max_iterations=max_iterations,
                ),
                name=f"run_device:{d.id}",
            )
            for (d, r, s) in device_setups
        ]

        try:
            await asyncio.gather(*tasks)
        finally:
            publisher.close()

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        # Windows fallback: add_signal_handler desteklenmiyor, KeyboardInterrupt
        # asyncio.run'dan propagate ediyor. POSIX'te bu blok hiç tetiklenmez
        # çünkü _amain'in signal handler'ı önce yakalıyor.
        logger.info("KeyboardInterrupt — engine kapanıyor (Windows fallback)")

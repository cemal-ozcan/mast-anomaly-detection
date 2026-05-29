"""Ingestion servisi entry: python -m ingestion (Iter 2.2: SQLite repository).

Faz 1 simulator MQTT yayınlarını subscribe eder, her mesajı parse edip
SQLite telemetry tablosuna tek-tek yazar (repository.insert). Migration
boot'ta apply edilir (idempotent). Bozuk JSON / eksik field → ERROR + skip;
SQLite IO hatası → CRITICAL + skip (tam retry resilience Iter 2.3'te).

SIGINT/SIGTERM ile graceful shutdown: subscriber loop_stop + disconnect + engine dispose.
"""
from __future__ import annotations

import json
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import FrameType

import paho.mqtt.client as mqtt
from loguru import logger
from sqlalchemy.exc import OperationalError

from ingestion.config import load_ingestion_config
from ingestion.message_parser import parse_message
from ingestion.subscriber import MQTTSubscriber
from simulator.config import load_mqtt_config
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository


def _make_message_handler(
    repository: TelemetryRepository,
) -> Callable[[mqtt.MQTTMessage], None]:
    """Paho mesaj callback'i: parse + repository.insert. Hataları yutar (servis çökmemeli)."""

    def handle(msg: mqtt.MQTTMessage) -> None:
        try:
            reading = parse_message(msg.payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error(
                "Bozuk mesaj atlandı: topic={} hata={} payload={!r}",
                msg.topic,
                e,
                msg.payload[:200],
            )
            return
        try:
            repository.insert(reading)
        except OperationalError as e:
            logger.critical(
                "SQLite insert başarısız (mesaj atlandı): device={} sensor={} hata={}",
                reading.device_id,
                reading.sensor,
                e,
            )
            return
        logger.debug(
            "Yazıldı: device={} sensor={} state={} value={}",
            reading.device_id,
            reading.sensor,
            reading.state,
            reading.value,
        )

    return handle


def run(
    mqtt_config_path: Path = Path("config/mqtt.yaml"),
    ingestion_config_path: Path = Path("config/ingestion.yaml"),
) -> None:
    """Ingestion servisini başlat. SIGINT/SIGTERM gelene kadar bloklar.

    Args:
        mqtt_config_path: MQTT broker YAML config (Faz 1 ile aynı dosya).
        ingestion_config_path: Ingestion-specific YAML config.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: Config geçersizse.
    """
    mqtt_config = load_mqtt_config(mqtt_config_path)
    ingestion_config = load_ingestion_config(ingestion_config_path)

    # Loguru sink-level: logger.level("INFO") sadece named level tanımını
    # okur/yaratır, sink filter'ı değiştirmez. Sink filter için default
    # stderr sink'ini kaldırıp config-driven level ile yeniden eklemek gerek.
    logger.remove()
    logger.add(sys.stderr, level=ingestion_config.log_level)

    engine = create_sqlite_engine(ingestion_config.db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repository = TelemetryRepository(engine)

        handler = _make_message_handler(repository)
        subscriber = MQTTSubscriber(
            config=mqtt_config,
            topic_pattern=ingestion_config.subscribe_topic_pattern,
            message_handler=handler,
        )

        shutdown = threading.Event()

        def _on_signal(signum: int, _frame: FrameType | None) -> None:
            logger.info("Shutdown sinyali alındı: {}", signum)
            shutdown.set()

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        subscriber.connect_and_start()
        try:
            # Background paho thread mesajları işler; ana thread shutdown bekler.
            shutdown.wait()
        finally:
            subscriber.stop()
    finally:
        engine.dispose()
        logger.info("Ingestion temiz kapandı")


if __name__ == "__main__":  # pragma: no cover
    run()

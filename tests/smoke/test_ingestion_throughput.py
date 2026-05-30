"""1000 msg/sec throughput smoke (spec § 13, kriter 1 + 4).

Yapay publisher (gerçek paho) broker'a hedef hızda yayın yapar; in-process ingestion
(subscriber + batch_writer) tmp SQLite'a yazar. Süre sonunda SQL satır sayısı yayınlanan
mesaj sayısına ±%1 yaklaşır (kayıpsız).

İzolasyon: `smoke/+/+` topic namespace kullanılır ki broker'daki başka publisher'lar
(ör. çalışan simulator'ın telemetry/+/+ yayını) sayımı şişirmesin.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

from ingestion.__main__ import _make_message_handler
from ingestion.batch_writer import BatchWriter
from ingestion.subscriber import MQTTSubscriber
from simulator.config import MQTTConfig
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository

pytestmark = pytest.mark.smoke

TARGET_RATE_HZ = 1000
TOPIC_PREFIX = "smoke"


def _publish_load(stop_event: threading.Event, published: list[int]) -> None:
    """Hedef hızda telemetri yayını yapar (smoke/ namespace); durana kadar. published[0]'a sayar."""
    client = mqtt.Client(client_id="smoke-publisher")
    client.connect("localhost", 1883, 60)
    client.loop_start()
    count = 0
    interval = 1.0 / TARGET_RATE_HZ
    next_at = time.monotonic()
    while not stop_event.is_set():
        device = f"device_{count % 60:03d}"
        payload = json.dumps({
            "device_id": device,
            "sensor": "motor_current",
            "timestamp": "2026-05-29T00:00:00.000Z",
            "state": "raising",
            "value": float(count % 100),
            "unit": "A",
        })
        client.publish(f"{TOPIC_PREFIX}/{device}/motor_current", payload, qos=1)
        count += 1
        next_at += interval
        sleep_for = next_at - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)
    client.loop_stop()
    client.disconnect()
    published[0] = count


def test_throughput_no_loss(tmp_path: Path, smoke_duration_s: float) -> None:
    """smoke_duration_s boyunca ~1000 msg/sec yük → SQL satır sayısı yayın sayısına ±%1."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    apply_migrations(engine, MIGRATIONS_DIR)
    repo = TelemetryRepository(engine)
    shutdown = threading.Event()
    writer = BatchWriter(repo, shutdown, max_size=100, flush_interval_s=1.0)
    writer.start()

    config = MQTTConfig(
        host="localhost", port=1883, client_id_prefix="smoke",
        keepalive=60, telemetry_prefix="smoke", qos=1,
    )
    subscriber = MQTTSubscriber(
        config=config,
        topic_pattern=f"{TOPIC_PREFIX}/+/+",
        message_handler=_make_message_handler(writer),
    )
    subscriber.connect_and_start()

    published: list[int] = [0]
    stop_pub = threading.Event()
    pub_thread = threading.Thread(
        target=_publish_load, args=(stop_pub, published), daemon=True
    )

    try:
        pub_thread.start()
        time.sleep(smoke_duration_s)
    finally:
        stop_pub.set()
        pub_thread.join(timeout=10)
        # 3s > flush_interval_s (1.0) + MQTT QoS1 transit payı: in-flight mesajlar drain olsun
        time.sleep(3.0)
        subscriber.stop()
        writer.stop()

    written = repo.count()
    engine.dispose()

    sent = published[0]
    assert sent > 0, "publisher hiç mesaj yayınlamadı"
    loss_ratio = (sent - written) / sent
    assert loss_ratio <= 0.01, f"kayıp %{loss_ratio*100:.2f} (>%1): sent={sent} written={written}"
    assert written <= sent, f"yazılan ({written}) yayınlanandan ({sent}) fazla — topic izolasyonu/çift sayım?"

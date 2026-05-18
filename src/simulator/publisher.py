"""MQTT yayıncı — spec § 7 topic + payload sözleşmesi."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
from loguru import logger

from src.simulator.config import MQTTConfig


def _now_iso() -> str:
    """UTC ISO 8601, milisaniye çözünürlüklü, Z suffix.

    Format: YYYY-MM-DDTHH:MM:SS.sssZ (spec § 7).

    Returns:
        UTC zaman damgası ISO 8601 formatında, Z soneksi ile.
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class MQTTPublisher:
    """paho-mqtt thin wrapper. Tek topic şeması: telemetry/{device_id}/{sensor}."""

    def __init__(self, config: MQTTConfig, client: Any | None = None) -> None:
        """MQTT yayıncısını başlat.

        Args:
            config: MQTT broker bağlantısı ve topic konfigürasyonu.
            client: paho-mqtt Client örneği (test için mock'lanabilir). None ise yeni client oluşturulur.
        """
        self.config = config
        self._client = client or mqtt.Client(client_id=f"{config.client_id_prefix}-publisher")
        self._connected = False

    def connect(self) -> None:
        """MQTT broker'a bağlan ve background loop başlat.

        Broker adresi ve portu config'den alınır. Loop başlatıldıktan sonra
        publish_reading() çağrıları non-blocking olarak çalışır.
        """
        logger.info("MQTT bağlanılıyor: {}:{}", self.config.host, self.config.port)
        self._client.connect(self.config.host, self.config.port, self.config.keepalive)
        self._client.loop_start()
        self._connected = True

    def publish_reading(
        self,
        device_id: str,
        sensor: str,
        value: float,
        unit: str,
        state: str = "idle",
    ) -> None:
        """Sensör okuması MQTT üzerinden yayınla.

        Topic şeması: telemetry/{device_id}/{sensor}
        Payload şeması (spec § 7): JSON ile device_id, timestamp, state, sensor, value, unit.

        Args:
            device_id: Cihaz kimliği (örn. "device_001").
            sensor: Sensör adı (örn. "motor_current").
            value: Ölçülen değer (float).
            unit: Birim (örn. "A", "V", "rpm").
            state: Cihaz durumu (varsayılan "idle").
        """
        payload = {
            "device_id": device_id,
            "timestamp": _now_iso(),
            "state": state,
            "sensor": sensor,
            "value": value,
            "unit": unit,
        }
        topic = f"{self.config.telemetry_prefix}/{device_id}/{sensor}"
        self._client.publish(topic, json.dumps(payload), qos=self.config.qos)

    def close(self) -> None:
        """MQTT bağlantısını kapat ve background loop'u durdur.

        Bağlantı açılmadıysa güvenli bir şekilde (hiçbir işlem yapmadan) döner.
        """
        if not self._connected:
            return
        logger.info("MQTT bağlantısı kapatılıyor")
        self._client.loop_stop()
        self._client.disconnect()
        self._connected = False

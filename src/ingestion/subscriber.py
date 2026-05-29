"""MQTT subscriber (paho-mqtt wrapper) — spec § 6 kontratı."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt
from loguru import logger

from simulator.config import MQTTConfig

MessageHandler = Callable[[mqtt.MQTTMessage], None]
"""Callback signature: paho mesajını parse + log/save yapan dışsal handler."""


class MQTTSubscriber:
    """paho-mqtt thin wrapper. Subscribe + background loop. Payload parsing'i bilmiyor —
    message_handler callable'a ham mesajı iletir (separation of concerns).

    Spec § 6: topic pattern `telemetry/+/+`, QoS 1, loop_start background thread.
    """

    def __init__(
        self,
        config: MQTTConfig,
        topic_pattern: str,
        message_handler: MessageHandler,
        client: Any | None = None,
    ) -> None:
        """MQTT subscriber'ı başlat (henüz bağlanmaz).

        Args:
            config: MQTT broker bağlantı bilgileri (Faz 1 simulator ile aynı config).
            topic_pattern: Subscribe edilecek topic pattern (`telemetry/+/+`).
            message_handler: Her gelen mesaj için çağrılacak callable.
            client: paho-mqtt Client instance'ı (test için mock'lanabilir). None ise yeni client.
        """
        self.config = config
        self.topic_pattern = topic_pattern
        self.message_handler = message_handler
        self._client = client or mqtt.Client(
            client_id=f"{config.client_id_prefix}-subscriber"
        )

    def connect_and_start(self) -> None:
        """Broker'a bağlan, topic'e subscribe ol, background loop'u başlat.

        on_message callback'i `message_handler`'a delege eder.
        """
        logger.info("MQTT subscriber bağlanılıyor: {}:{}", self.config.host, self.config.port)

        def _on_message(_client: Any, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
            self.message_handler(msg)

        self._client.on_message = _on_message
        self._client.connect(self.config.host, self.config.port, self.config.keepalive)
        self._client.subscribe(self.topic_pattern, qos=self.config.qos)
        self._client.loop_start()
        logger.info("Subscribed: {} (QoS={})", self.topic_pattern, self.config.qos)

    def stop(self) -> None:
        """Background loop'u durdur, broker'dan ayrıl."""
        logger.info("MQTT subscriber kapatılıyor")
        self._client.loop_stop()
        self._client.disconnect()

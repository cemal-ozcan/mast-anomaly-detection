"""MQTT yayıncı (publisher) için TDD testleri. Mock paho-mqtt ile."""
import json
import re
from unittest.mock import MagicMock

import pytest

from src.simulator.config import MQTTConfig
from src.simulator.publisher import MQTTPublisher, _now_iso


def _config(qos: int = 1) -> MQTTConfig:
    """Test için minimal MQTTConfig döndür."""
    return MQTTConfig(
        host="localhost",
        port=1883,
        client_id_prefix="test",
        keepalive=60,
        telemetry_prefix="telemetry",
        qos=qos,
    )


def test_now_iso_format() -> None:
    """_now_iso() çıkışı YYYY-MM-DDTHH:MM:SS.sssZ formatında olmalı."""
    ts = _now_iso()
    # 2026-05-18T15:30:00.123Z formatı
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts)


def test_connect_calls_paho_connect_and_loop_start() -> None:
    """connect() paho client'ını connect ve loop_start ile başlatmalı."""
    mock_client = MagicMock()
    pub = MQTTPublisher(_config(), client=mock_client)
    pub.connect()
    mock_client.connect.assert_called_once_with("localhost", 1883, 60)
    mock_client.loop_start.assert_called_once()


def test_publish_reading_emits_correct_topic_and_payload() -> None:
    """publish_reading() doğru topic ve JSON payload ile publish etmeli."""
    mock_client = MagicMock()
    pub = MQTTPublisher(_config(qos=1), client=mock_client)
    pub.publish_reading(
        device_id="device_001",
        sensor="motor_current",
        value=8.7,
        unit="A",
        state="idle",
    )
    mock_client.publish.assert_called_once()
    args, kwargs = mock_client.publish.call_args
    topic = args[0] if args else kwargs["topic"]
    payload_str = args[1] if len(args) > 1 else kwargs["payload"]
    qos = kwargs.get("qos") if "qos" in kwargs else (args[2] if len(args) > 2 else None)

    assert topic == "telemetry/device_001/motor_current"
    assert qos == 1
    payload = json.loads(payload_str)
    assert payload["device_id"] == "device_001"
    assert payload["sensor"] == "motor_current"
    assert payload["value"] == 8.7
    assert payload["unit"] == "A"
    assert payload["state"] == "idle"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", payload["timestamp"])


def test_close_stops_loop_and_disconnects() -> None:
    """close() paho client'ını loop_stop ve disconnect ile kapatmalı."""
    mock_client = MagicMock()
    pub = MQTTPublisher(_config(), client=mock_client)
    pub.connect()
    pub.close()
    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()


def test_close_is_safe_without_connect() -> None:
    """close() bağlanmamışken safe olmalı (hiçbir paho metodu çağrılmamalı)."""
    mock_client = MagicMock()
    pub = MQTTPublisher(_config(), client=mock_client)
    pub.close()  # Bağlanmamışken close() patlamamalı
    mock_client.loop_stop.assert_not_called()
    mock_client.disconnect.assert_not_called()

"""MQTTSubscriber paho wrapper testleri (Iter 2.1)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_subscriber_connects_and_subscribes(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect_and_start broker'a bağlanır + topic'e subscribe eder + loop_start çağırır."""
    from ingestion.subscriber import MQTTSubscriber
    from simulator.config import MQTTConfig

    mock_client = MagicMock()
    config = MQTTConfig(
        host="localhost",
        port=1883,
        client_id_prefix="test-ingestion",
        keepalive=60,
        telemetry_prefix="telemetry",
        qos=1,
    )
    handler = MagicMock()

    subscriber = MQTTSubscriber(
        config=config,
        topic_pattern="telemetry/+/+",
        message_handler=handler,
        client=mock_client,
    )
    subscriber.connect_and_start()

    mock_client.connect.assert_called_once_with("localhost", 1883, 60)
    mock_client.subscribe.assert_called_once_with("telemetry/+/+", qos=1)
    mock_client.loop_start.assert_called_once()


def test_subscriber_routes_message_to_handler() -> None:
    """paho on_message callback ayarlanmış message_handler'ı çağırır."""
    from ingestion.subscriber import MQTTSubscriber
    from simulator.config import MQTTConfig

    mock_client = MagicMock()
    config = MQTTConfig(
        host="localhost", port=1883, client_id_prefix="test",
        keepalive=60, telemetry_prefix="telemetry", qos=1,
    )
    handler = MagicMock()

    subscriber = MQTTSubscriber(
        config=config, topic_pattern="telemetry/+/+",
        message_handler=handler, client=mock_client,
    )
    subscriber.connect_and_start()

    # paho `on_message` mock_client.on_message setter ile atanmış olmalı
    assert mock_client.on_message is not None

    # Callback'i manuel tetikle
    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = b'{"device_id":"device_001","sensor":"motor_current","timestamp":"2026-05-29T00:00:00.000Z","state":"idle","value":0.5,"unit":"A"}'
    mock_client.on_message(mock_client, None, fake_msg)

    handler.assert_called_once_with(fake_msg)


def test_subscriber_stop_disconnects_and_loop_stop() -> None:
    """stop() loop_stop + disconnect çağırır."""
    from ingestion.subscriber import MQTTSubscriber
    from simulator.config import MQTTConfig

    mock_client = MagicMock()
    config = MQTTConfig(
        host="localhost", port=1883, client_id_prefix="test",
        keepalive=60, telemetry_prefix="telemetry", qos=1,
    )

    subscriber = MQTTSubscriber(
        config=config, topic_pattern="telemetry/+/+",
        message_handler=MagicMock(), client=mock_client,
    )
    subscriber.stop()

    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()


def test_connect_sets_reconnect_backoff() -> None:
    """connect_and_start paho reconnect_delay_set(1, 30) çağırır (kriter 2)."""
    from unittest.mock import MagicMock

    from ingestion.subscriber import MQTTSubscriber
    from simulator.config import MQTTConfig

    mock_client = MagicMock()
    config = MQTTConfig(
        host="localhost", port=1883, client_id_prefix="test",
        keepalive=60, telemetry_prefix="telemetry", qos=1,
    )
    sub = MQTTSubscriber(
        config=config,
        topic_pattern="telemetry/+/+",
        message_handler=lambda _msg: None,
        client=mock_client,
    )
    sub.connect_and_start()
    mock_client.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=30)

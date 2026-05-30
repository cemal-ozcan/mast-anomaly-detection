"""Ingestion __main__ handler testleri (Iter 2.3: batch_writer.enqueue)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock


def _payload() -> bytes:
    return json.dumps({
        "device_id": "device_001",
        "sensor": "motor_current",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")


def test_handle_message_enqueues_parsed_reading() -> None:
    """Geçerli mesaj → batch_writer.enqueue parse edilmiş IngestedReading ile çağrılır."""
    from ingestion.__main__ import _make_message_handler

    batch_writer = MagicMock()
    handler = _make_message_handler(batch_writer)

    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = _payload()

    handler(fake_msg)

    batch_writer.enqueue.assert_called_once()
    reading = batch_writer.enqueue.call_args.args[0]
    assert reading.device_id == "device_001"
    assert reading.value == 8.7


def test_handle_message_bad_json_does_not_enqueue() -> None:
    """Bozuk JSON → enqueue YOK, exception bastırılır (servis çökmez)."""
    from ingestion.__main__ import _make_message_handler

    batch_writer = MagicMock()
    handler = _make_message_handler(batch_writer)

    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = b"{not_valid_json"

    handler(fake_msg)  # raise etmemeli

    batch_writer.enqueue.assert_not_called()

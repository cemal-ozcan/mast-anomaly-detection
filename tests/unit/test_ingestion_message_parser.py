"""IngestedReading + parse_message testleri (Iter 2.1)."""
from __future__ import annotations

import json

import pytest


def test_ingested_reading_is_frozen_dataclass() -> None:
    """IngestedReading frozen — mutate edilemez."""
    from dataclasses import FrozenInstanceError

    from ingestion.message_parser import IngestedReading

    reading = IngestedReading(
        device_id="device_001",
        sensor="motor_current",
        timestamp="2026-05-29T15:30:00.123Z",
        state="raising",
        value=8.5,
        unit="A",
    )
    with pytest.raises(FrozenInstanceError):
        reading.value = 9.0  # type: ignore[misc]


def test_parse_message_valid_payload_returns_reading() -> None:
    """Geçerli Faz 1 publisher payload'ı → IngestedReading."""
    from ingestion.message_parser import IngestedReading, parse_message

    payload = json.dumps({
        "device_id": "device_001",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "sensor": "motor_current",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")

    reading = parse_message(payload)
    assert reading == IngestedReading(
        device_id="device_001",
        sensor="motor_current",
        timestamp="2026-05-29T15:30:00.123Z",
        state="raising",
        value=8.7,
        unit="A",
    )


def test_parse_message_invalid_json_raises_json_decode_error() -> None:
    """Bozuk JSON → json.JSONDecodeError (spesifik exception)."""
    from ingestion.message_parser import parse_message

    with pytest.raises(json.JSONDecodeError):
        parse_message(b"{not valid json")


def test_parse_message_missing_field_raises_key_error() -> None:
    """Eksik field → KeyError."""
    from ingestion.message_parser import parse_message

    payload = json.dumps({
        "device_id": "device_001",
        # "timestamp" eksik
        "state": "raising",
        "sensor": "motor_current",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")

    with pytest.raises(KeyError, match="timestamp"):
        parse_message(payload)


def test_parse_message_wrong_value_type_raises_value_error_or_type_error() -> None:
    """value alanı non-numeric → ValueError veya TypeError."""
    from ingestion.message_parser import parse_message

    payload = json.dumps({
        "device_id": "device_001",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "sensor": "motor_current",
        "value": "not_a_number",
        "unit": "A",
    }).encode("utf-8")

    with pytest.raises((ValueError, TypeError)):
        parse_message(payload)

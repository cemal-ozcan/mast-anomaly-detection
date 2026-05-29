"""Ingestion __main__ handler testleri (Iter 2.2: repository.insert)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from sqlalchemy import Engine


def _payload() -> bytes:
    return json.dumps({
        "device_id": "device_001",
        "sensor": "motor_current",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")


def test_handle_message_inserts_into_repository(migrated_engine: Engine) -> None:
    """Geçerli mesaj → repository.insert çağrılır, satır DB'ye yazılır."""
    from ingestion.__main__ import _make_message_handler
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    handler = _make_message_handler(repo)

    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = _payload()

    handler(fake_msg)

    assert repo.count() == 1
    rows = repo.fetch_recent("device_001", "motor_current", limit=1)
    assert rows[0].value == 8.7


def test_handle_message_bad_json_skips_without_insert(migrated_engine: Engine) -> None:
    """Bozuk JSON → insert YOK, exception bastırılır (servis çökmez)."""
    from ingestion.__main__ import _make_message_handler
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    handler = _make_message_handler(repo)

    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = b"{not_valid_json"

    handler(fake_msg)  # raise etmemeli

    assert repo.count() == 0

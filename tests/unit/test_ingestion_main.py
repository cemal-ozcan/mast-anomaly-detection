"""Ingestion __main__ entry testleri (Iter 2.1)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_handle_message_parses_and_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """handle_message geçerli mesajı parse edip loguru INFO basar."""
    import logging

    from loguru import logger

    from ingestion.__main__ import _make_message_handler

    handler = _make_message_handler()
    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = json.dumps({
        "device_id": "device_001",
        "sensor": "motor_current",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")

    handler_id = logger.add(caplog.handler, level="INFO", format="{message}")
    try:
        with caplog.at_level(logging.INFO):
            handler(fake_msg)
    finally:
        logger.remove(handler_id)

    assert any("device_001" in r.message and "motor_current" in r.message
               for r in caplog.records)


def test_handle_message_bad_json_logs_error_and_skips(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Bozuk JSON payload → ERROR log + servis çökmez (exception bastırılır)."""
    import logging

    from loguru import logger

    from ingestion.__main__ import _make_message_handler

    handler = _make_message_handler()
    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = b"{not_valid_json"

    handler_id = logger.add(caplog.handler, level="ERROR", format="{message}")
    try:
        with caplog.at_level(logging.ERROR):
            handler(fake_msg)  # raise etmemeli
    finally:
        logger.remove(handler_id)

    assert any("Bozuk mesaj" in r.message or "atlandı" in r.message
               for r in caplog.records)

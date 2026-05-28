"""2 cihaz paralel integration testi (Iter 3 — spec § 3 bitti kriteri #3).

paho-mqtt mock kullanır; gerçek Mosquitto'ya karşı testler tests/smoke/ (CI dışı).
Simüle 10 saniye: asyncio.sleep no-op + FakeClock manuel advance.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulator.engine import run
from tests.unit.test_runtime import FakeClock

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_two_devices_produce_messages_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """devices_multi.yaml ile 2 cihaz, simüle 10 tick, her ikisinden de mesaj akmalı."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=10,
        seed=None,
        clock=clock,
    )

    # 2 cihaz × 10 tick × 6 sensör = 120 publish
    assert mock_publisher.publish_reading.call_count == 120

    # Her cihazdan tam 60 mesaj (10 tick × 6 sensör)
    device_msg_counts: dict[str, int] = {"device_001": 0, "device_002": 0}
    for call in mock_publisher.publish_reading.call_args_list:
        device_msg_counts[call.kwargs["device_id"]] += 1
    assert device_msg_counts == {"device_001": 60, "device_002": 60}


def test_two_devices_interleave_within_each_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Her tick'te iki cihaz da ilerlemeli (biri diğerini tamamen bitirmesin).

    Sonraki 6 publish'in (1 cihazın 1 tick'i) hep aynı device_id'den geldiği bir
    durum varsa ve 6'nın katı pozisyonlarda hep aynı cihaz ardışık geliyorsa
    asyncio task'ları doğru interleave etmiyor. asyncio.gather'ın doğal davranışı
    her await'te diğer task'a yield etmektir, bu zaten doğru — test bu invariantı
    regresyon olarak korur.
    """
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=None,
        clock=clock,
    )

    device_id_sequence = [
        c.kwargs["device_id"] for c in mock_publisher.publish_reading.call_args_list
    ]
    # Her iki cihaz da yayın yaptı
    assert set(device_id_sequence) == {"device_001", "device_002"}
    # Bir cihaz, diğeri başlamadan tüm tick'lerini bitirmedi:
    # device_001'in son indeksi device_002'nin ilk indeksinden ÖNCE geliyorsa serileşmiş demektir.
    first_d2 = device_id_sequence.index("device_002")
    last_d1 = len(device_id_sequence) - 1 - list(reversed(device_id_sequence)).index("device_001")
    assert first_d2 < last_d1, (
        "Cihazlar serileşmiş çalıştı (biri tamamen bittikten sonra diğeri başladı); "
        "asyncio.gather paralelizmi düzgün çalışmıyor."
    )


def test_topic_disambiguation_uses_device_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Her cihazın mesajları kendi device_id'sini taşır (spec § 7 topic şeması)."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=1,
        seed=None,
        clock=clock,
    )

    # Her publish çağrısının device_id'si {device_001, device_002} kümesinde
    for call in mock_publisher.publish_reading.call_args_list:
        assert call.kwargs["device_id"] in {"device_001", "device_002"}

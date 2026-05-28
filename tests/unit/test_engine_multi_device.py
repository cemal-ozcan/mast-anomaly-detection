"""Çoklu cihaz spawn + per-device RNG determinizm testleri (Iter 3)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from simulator.engine import run
from tests.unit.conftest import FIXTURES
from tests.unit.test_runtime import FakeClock


def test_run_spawns_all_configured_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    """2 cihaz fixture'ı: her cihaz 2 tick × 6 sensör = 12 publish, toplam 24.

    "Her iki cihaz da yayın yaptı" garantisidir; interleaved scheduling
    (paralelizm) doğrulaması Task 7 integration testindedir.
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
        max_iterations=2,
        seed=None,  # YAML'deki per-device seed kullan
        clock=clock,
    )

    # 2 cihaz × 2 tick × 6 sensör = 24 publish
    assert mock_publisher.publish_reading.call_count == 24

    # Her iki cihaz da yayın yaptı (device_id alanı kontrolü)
    device_ids = {c.kwargs["device_id"] for c in mock_publisher.publish_reading.call_args_list}
    assert device_ids == {"device_001", "device_002"}


def test_same_seed_devices_produce_identical_value_sequences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec § 3 Iter 3 bitti kriteri #2: aynı seed → birebir aynı value dizisi.

    Per-device RNG izolasyonu + ortak engine_boot_at garantisinin testidir.
    Eğer cihazlar shared RNG kullansaydı veya started_at_monotonic'ler kaymış
    olsaydı bu test FAIL ederdi.
    """
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_same_seed.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=None,
        clock=clock,
    )

    # 2 cihaz × 3 tick × 6 sensör = 36 publish
    assert mock_publisher.publish_reading.call_count == 36

    # device_001 ve device_002'nin (sensor, tick_index) → value haritalarını çıkar
    by_device: dict[str, list[tuple[str, float]]] = {"device_001": [], "device_002": []}
    for call in mock_publisher.publish_reading.call_args_list:
        kw = call.kwargs
        by_device[kw["device_id"]].append((kw["sensor"], kw["value"]))

    # Aynı sensör sırası + aynı value'lar bekleniyor
    assert by_device["device_001"] == by_device["device_002"]


def test_different_seeds_produce_different_value_sequences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negatif kontrol: farklı seed → farklı value dizisi (devices_multi fixture)."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",  # seed 42 vs 7
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=None,
        clock=clock,
    )

    by_device: dict[str, list[tuple[str, float]]] = {"device_001": [], "device_002": []}
    for call in mock_publisher.publish_reading.call_args_list:
        kw = call.kwargs
        by_device[kw["device_id"]].append((kw["sensor"], kw["value"]))

    assert by_device["device_001"] != by_device["device_002"]

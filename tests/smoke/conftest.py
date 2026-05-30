"""Smoke test çift-kapı: RUN_SMOKE=1 env + broker erişilebilirlik (spec § 12, § 13).

Default `pytest tests/` run'ında smoke testleri SKIPPED'tir (env yok). Çalışması için:
    RUN_SMOKE=1 pytest tests/smoke/ -v
Süre: SMOKE_DURATION_S env (default 5s). Tam 60s kabul: SMOKE_DURATION_S=60 RUN_SMOKE=1 ...
"""
from __future__ import annotations

import os
import socket

import pytest

BROKER_HOST = "localhost"
BROKER_PORT = 1883


def _broker_reachable() -> bool:
    try:
        with socket.create_connection((BROKER_HOST, BROKER_PORT), timeout=1.0):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _smoke_gate() -> None:
    """Her smoke testinden önce çift kapı: env opt-in + broker erişilebilir."""
    if os.environ.get("RUN_SMOKE") != "1":
        pytest.skip("Smoke testleri opt-in: RUN_SMOKE=1 ile çalıştır")
    if not _broker_reachable():
        pytest.skip(f"Broker erişilemez: {BROKER_HOST}:{BROKER_PORT}")


@pytest.fixture
def smoke_duration_s() -> float:
    """Smoke yük süresi (saniye). SMOKE_DURATION_S env ile ayarlanır, default 5.0."""
    return float(os.environ.get("SMOKE_DURATION_S", "5.0"))

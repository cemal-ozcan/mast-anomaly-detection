"""Iter 3 altyapı testi: pytest-asyncio + asyncio.sleep no-op pattern çalışıyor mu?"""
from __future__ import annotations

import asyncio

import pytest


async def test_async_test_runner_works() -> None:
    """pytest-asyncio auto-mode ile async def test çalışmalı."""
    await asyncio.sleep(0)
    assert True


async def test_asyncio_sleep_can_be_monkeypatched_without_recursion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec § 12 pattern: orijinal sleep referansını sakla, lambda onu çağırsın.

    Bu test recursive-lambda hatasının regression koruyucusudur.
    """
    original_sleep = asyncio.sleep
    monkeypatch.setattr("asyncio.sleep", lambda _s: original_sleep(0))

    # 1.0 sn istesek bile gerçekte 0 sn bekler
    await asyncio.sleep(1.0)
    await asyncio.sleep(5.0)
    assert True  # Sonsuz döngü olsa buraya gelmezdik

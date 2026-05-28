"""MechanicalWear istatistiksel imza testi (spec § 12 bitti kriteri A).

60+ örnek RAISING'de motor_current ortalaması baseline'a göre %15..%30 yüksek
olmalı (scipy.stats.ttest_1samp p<0.05). Bu test "senaryo gerçekten gözle
görülür bir kayma üretiyor mu" sorusunu istatistiksel olarak doğrular —
hipotez kontrolü değil, regresyon değer kontrolü (deterministik seed altında
stabil p-value).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scipy.stats import ttest_1samp  # type: ignore[import-untyped]

from simulator.config import DeviceState
from simulator.engine import run

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_mechanical_wear_raising_current_mean_significantly_above_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAISING motor_current ortalama: t-test p<0.05 ve mean ∈ [baseline * 1.15, baseline * 1.30]."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep

    # FakeClock'u manuel advance edemiyoruz (engine içinde clock() çağrıları sıralı).
    # Çözüm: tick başına clock(0)→clock(1)→... ilerleyen counter.
    class CountingClock:
        def __init__(self) -> None:
            self._t = 0.0

        def __call__(self) -> float:
            return self._t

        def tick(self) -> None:
            self._t += 1.0

    clock = CountingClock()

    # asyncio.sleep yerine clock.tick + yield et
    async def _ticking_sleep(_s: float) -> None:
        clock.tick()
        await original_sleep(0)

    monkeypatch.setattr("simulator.engine.asyncio.sleep", _ticking_sleep)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_with_mechanical_wear.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=200,
        seed=None,
        clock=clock,
    )

    # RAISING durumundaki motor_current değerlerini topla
    raising_motor_currents = [
        c.kwargs["value"]
        for c in mock_publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "motor_current"
        and c.kwargs["state"] == DeviceState.RAISING
    ]

    assert len(raising_motor_currents) >= 60, (
        f"En az 60 RAISING motor_current örneği bekleniyor, alınan: {len(raising_motor_currents)}"
    )

    # Baseline RAISING kararlı motor_current = 8.0 (spec § 6).
    # MechanicalWear severity=0.25, ramp_up_s=5: ramp sonrası factor=0.25 → +%25.
    # Ramp süresince (ilk 5s) ortalama daha düşük; eğer örnekleme rampa öncesi
    # ve sonrası karışıksa ortalama [+15%, +30%] aralığında düşmelidir.
    baseline = 8.0
    mean_obs = sum(raising_motor_currents) / len(raising_motor_currents)

    # 1) Mean baseline'a göre [+15%, +30%] aralığında
    assert baseline * 1.15 <= mean_obs <= baseline * 1.30, (
        f"Ortalama {mean_obs:.2f} baseline {baseline} * [1.15, 1.30] dışında"
    )

    # 2) t-test: H0 = ortalama == baseline (no fault). H0 reddedilmeli (p<0.05).
    result = ttest_1samp(raising_motor_currents, popmean=baseline)
    assert result.pvalue < 0.05, (
        f"t-test p={result.pvalue:.4f} ≥ 0.05 — MechanicalWear sinyali baseline'dan ayırt edilmiyor"
    )

"""HydraulicLeak istatistiksel imza testi (spec § 12 bitti kriteri B).

HOLDING penceresinde 60+ örnek üzerinde hydraulic_pressure zaman serisine
scipy.stats.spearmanr → ρ<0 ve p<0.05 (negatif monoton trend).
"""
from __future__ import annotations

import pytest
from scipy.stats import spearmanr  # type: ignore[import-untyped]

from simulator.config import DeviceState
from simulator.engine import run
from tests.scenarios.conftest import FIXTURES, CountingClock


def test_hydraulic_leak_holding_pressure_decreases_monotonically(
    monkeypatch: pytest.MonkeyPatch,
    patched_engine_clock: CountingClock,
) -> None:
    """HOLDING'de hydraulic_pressure zaman serisi Spearman ρ<0, p<0.05."""
    from unittest.mock import MagicMock

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_with_hydraulic_leak.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=150,  # IDLE(1) + RAISING(1) + HOLDING(120) + LOWERING(1) = 123 — ilk cycle yeterli
        seed=None,
        clock=patched_engine_clock,
    )

    # HOLDING durumundaki hydraulic_pressure değerlerini sırayla topla
    holding_pressures = [
        c.kwargs["value"]
        for c in mock_publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "hydraulic_pressure"
        and c.kwargs["state"] == DeviceState.HOLDING
    ]

    assert len(holding_pressures) >= 60, (
        f"En az 60 HOLDING hydraulic_pressure örneği bekleniyor, alınan: {len(holding_pressures)}"
    )

    # tick_indices = [0, 1, 2, ...] (zaman sırasında)
    tick_indices = list(range(len(holding_pressures)))

    result = spearmanr(tick_indices, holding_pressures)
    # H0 = monoton ilişki yok. H1 = negatif monoton (basınç düşüşü).
    assert result.statistic < 0, (
        f"Spearman ρ={result.statistic:.3f} ≥ 0 — basınç düşmüyor"
    )
    assert result.pvalue < 0.05, (
        f"Spearman p={result.pvalue:.4f} ≥ 0.05 — kaçak sinyali istatistiksel olarak anlamsız"
    )

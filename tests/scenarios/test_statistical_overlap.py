"""Overlap analizi: kural ↔ istatistik aynı arızayı işaretler (Faz 5 Iter 5.2, spec § 10, kabul kriteri 3).

MechanicalWear (A): kısa pencere motor_current_high (kural) + uzun pencere three_sigma:motor_current
(istatistik) aynı motor_current arızasını yakalar. Servis (_detect_once) iki-pencere anomalilerini
tek turda fuse_anomalies ile birleştirir → fused(N) corroboration (spec § 8). Bu test o birleşmeyi
dedektör + fusion seviyesinde gösterir (servisin iki-pencere mimarisini yansıtır).
"""
from __future__ import annotations

import pytest

from detectors.fusion import fuse_anomalies
from detectors.rules.motor_current_high import MotorCurrentHigh
from detectors.statistical.three_sigma import ThreeSigma
from tests.scenarios.conftest import (
    FIXTURES,
    CountingClock,
    build_detector_window,
    build_statistical_window,
)


def test_mechanical_wear_rule_and_statistical_overlap_fused(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """A: motor_current_high (kural, kısa) + three_sigma:motor_current (istatistik, uzun) → fused(N)."""
    mech = FIXTURES / "devices_with_mechanical_wear.yaml"

    # İstatistik katmanı (uzun pencere: clean baseline + arıza tail)
    stat_window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(FIXTURES / "devices_clean_baseline.yaml", 364), (mech, 181)],
    )
    stat_anoms = ThreeSigma(
        current_window_s=181, sigma_k=3.0, min_baseline=30, min_current=5, sensors=["motor_current"]
    ).detect(stat_window)  # sensors daraltması: mast_position harness artefaktını dışla (B2 notu)

    # Kural katmanı (kısa pencere: yalnız arıza verisi, servisteki window_s gibi)
    rule_window = build_detector_window(monkeypatch, patched_engine_clock, mech, max_iterations=181)
    rule_anoms = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10).detect(rule_window)

    # Her iki katman da motor_current'ı bağımsız işaretledi (tutarlılık / overlap)
    assert any(a.sensor == "motor_current" for a in rule_anoms), "kural motor_current'ı yakalamadı"
    assert any(a.rule_name == "three_sigma:motor_current" for a in stat_anoms), \
        "istatistik motor_current'ı yakalamadı"

    # Servis bunları tek turda birleştirir → fused(N), her iki katman description'da
    fused = fuse_anomalies(rule_anoms + stat_anoms)
    assert fused is not None
    assert fused.rule_name.startswith("fused("), f"birleşmedi: {fused.rule_name}"
    assert "motor_current_high" in fused.description
    assert "three_sigma:motor_current" in fused.description

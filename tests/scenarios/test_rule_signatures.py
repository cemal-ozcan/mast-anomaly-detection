"""A/B/C + clean dedektör imza testleri (Faz 4 Iter 4.2, spec § 9, kabul kriteri 1 + 4).

Engine harness fixture senaryosunu koşturur → uzun-format pencere → dedektör çalıştırır:
- Arıza penceresinde ilgili kural TETİKLENİR.
- Clean (senaryosuz) pencerede HİÇBİR kural tetiklenmez (FP yok).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from detectors.config import build_detectors, load_detector_config
from detectors.rules.hydraulic_pressure_decline import HydraulicPressureDecline
from detectors.rules.motor_current_high import MotorCurrentHigh
from detectors.rules.motor_voltage_erratic import MotorVoltageErratic
from detectors.rules.vibration_elevated import VibrationElevated
from tests.scenarios.conftest import FIXTURES, CountingClock, build_detector_window


def test_mechanical_wear_triggers_motor_current_high(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """MechanicalWear penceresi motor_current_high'ı tetikler (RAISING ort. > 9.0A)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_mechanical_wear.yaml", max_iterations=200,
    )
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10)
    assert len(rule.detect(window)) == 1


def test_mechanical_wear_triggers_vibration_elevated(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """MechanicalWear penceresi vibration_elevated'ı tetikler (RAISING ort. > 0.37g)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_mechanical_wear.yaml", max_iterations=200,
    )
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10)
    assert len(rule.detect(window)) == 1


def test_hydraulic_leak_triggers_pressure_decline(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """HydraulicLeak penceresi hydraulic_pressure_decline'ı ÜRETİM parametreleriyle tetikler.

    max_iterations=120 → tek HOLDING epizodu (idle1 + raising1 + holding~118 ≥ min_samples 60),
    epizod-içi tek eğim. Üretim eşiği 3.0 bar/dk + min_samples 60 (FP-sağlam kalibrasyon);
    gerçek kaçak ~-5 bar/dk bunun çok altında → tetiklenir.
    """
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_hydraulic_leak.yaml", max_iterations=120,
    )
    rule = HydraulicPressureDecline(
        state="holding", slope_threshold_bar_per_min=3.0, min_samples=60
    )
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    assert anomalies[0].value < -3.0  # slope bar/dk


def test_electrical_fault_triggers_voltage_erratic(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """ElectricalFault penceresi motor_voltage_erratic'i tetikler (std > 1.0V)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_electrical_fault.yaml", max_iterations=200,
    )
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert len(rule.detect(window)) == 1


def test_clean_baseline_triggers_no_rules(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """Senaryosuz clean pencere: TÜM kalibre kural seti HİÇBİR anomali üretmez (FP yok).

    max_iterations=181 → idle1 + raising60 + holding120 (tek epizod), her kuralın
    değerlendirme koşulu sağlanır (≥10 RAISING + ≥10 HOLDING örnek) ama tetiklenmez.
    """
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_clean_baseline.yaml", max_iterations=181,
    )
    detectors = build_detectors(load_detector_config(Path("config/detectors.yaml.example")))
    triggered = [a.rule_name for d in detectors for a in d.detect(window)]
    assert triggered == [], f"Clean veride beklenmeyen tetik: {triggered}"

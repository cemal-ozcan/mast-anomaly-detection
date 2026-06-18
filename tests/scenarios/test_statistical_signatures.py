"""A/B/C + clean istatistiksel imza testleri (Faz 5 Iter 5.2, spec § 10, kabul kriteri 2/4).

build_statistical_window: clean baseline segment(leri) + arıza tail segmenti → uzun pencere.
Statistical dedektör içeride split_recent ile böler; current_window_s = son (arıza) segmentin
iterasyon sayısı → arıza tail "current" olur.
"""
from __future__ import annotations

import pytest

from detectors.rules.motor_voltage_erratic import MotorVoltageErratic
from detectors.statistical.iqr import IQR
from detectors.statistical.three_sigma import ThreeSigma
from tests.scenarios.conftest import (
    FIXTURES,
    CountingClock,
    build_detector_window,
    build_statistical_window,
)


def test_harness_builds_two_segment_window(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """build_statistical_window iki segmenti birleştirir; baseline+current ayrılabilir boyutta."""
    window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(FIXTURES / "devices_clean_baseline.yaml", 182),
         (FIXTURES / "devices_with_mechanical_wear.yaml", 181)],
    )
    assert not window.empty
    assert set(window.columns) == {"device_id", "timestamp", "sensor", "state", "value"}
    # motor_current hem baseline hem current segmentten satır içermeli (split anlamlı olsun)
    mc = window[window["sensor"] == "motor_current"]
    assert len(mc) > 300  # ~363 satır (182 + 181)
    # split_recent ile current = son 181s, baseline > 0 satır olmalı (sensors=motor_current ile daralt)
    ts = ThreeSigma(current_window_s=181, sigma_k=3.0, min_baseline=30, min_current=5, sensors=["motor_current"])
    iqr = IQR(current_window_s=181, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=["motor_current"])
    # mechanical_wear motor_current güçlü sinyal → en az bir dedektör yakalamalı
    rules = {a.rule_name for a in ts.detect(window)} | {a.rule_name for a in iqr.detect(window)}
    assert "three_sigma:motor_current" in rules or "iqr:motor_current" in rules


# Clean baseline: idle1+raising60+holding120+lowering1 = 182 iter/epizod.
# mechanical_wear: idle1+raising60+holding60+lowering60 = 181 iter/epizod.
# developed leak: idle1+raising1+holding600+lowering1 = 603 iter/epizod.
# electrical_fault: idle60+raising60+holding60+lowering60 = 240 iter/epizod.
# sensors=[...] daraltması: durağan-değil mast_position/motor_temperature harness artefaktını dışlar
# (modül başı not; spec § 5 sensors filtresi). Hepsi ölçümle doğrulandı.
_CLEAN = FIXTURES / "devices_clean_baseline.yaml"
_STATIONARY = ["motor_current", "motor_voltage", "hydraulic_pressure", "vibration"]


def test_mechanical_wear_triggers_three_sigma_and_iqr(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """A: MechanicalWear motor_current (z≈19) + vibration (z≈15) hem 3σ hem IQR ile tetiklenir."""
    window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(_CLEAN, 364), (FIXTURES / "devices_with_mechanical_wear.yaml", 181)],
    )
    watched = ["motor_current", "vibration"]
    ts_rules = {a.rule_name for a in ThreeSigma(
        current_window_s=181, sigma_k=3.0, min_baseline=30, min_current=5, sensors=watched).detect(window)}
    iqr_rules = {a.rule_name for a in IQR(
        current_window_s=181, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=watched).detect(window)}
    assert ts_rules == {"three_sigma:motor_current", "three_sigma:vibration"}, f"3σ: {ts_rules}"
    assert iqr_rules == {"iqr:motor_current", "iqr:vibration"}, f"IQR: {iqr_rules}"


def test_developed_hydraulic_leak_triggers_three_sigma_and_iqr(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """B: gelişmiş kaçak hydraulic_pressure'ı (HOLDING, ölçülen z≈12) hem 3σ hem IQR ile tetikler."""
    window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(_CLEAN, 364), (FIXTURES / "devices_with_hydraulic_leak_developed.yaml", 603)],
    )
    watched = ["hydraulic_pressure"]
    ts_rules = {a.rule_name for a in ThreeSigma(
        current_window_s=603, sigma_k=3.0, min_baseline=30, min_current=5, sensors=watched).detect(window)}
    iqr_rules = {a.rule_name for a in IQR(
        current_window_s=603, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=watched).detect(window)}
    assert ts_rules == {"three_sigma:hydraulic_pressure"}, f"3σ: {ts_rules}"
    assert iqr_rules == {"iqr:hydraulic_pressure"}, f"IQR: {iqr_rules}"


def test_electrical_fault_statistical_silent_rule_catches(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """C (varyans arızası): merkezi-eğilim statistical SESSIZ; kural katmanı (std) yakalar — tamamlayıcı.

    ElectricalFault mean/median'ı kaydırmaz (spike'lar simetrik, ölçülen z<1.4) → 3σ/IQR motor_voltage'da
    tetiklenMEZ. Aynı arıza penceresinde motor_voltage_erratic (std) tetiklenir (komplementerlik, spec § 9 C).
    """
    stat_window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(_CLEAN, 364), (FIXTURES / "devices_with_electrical_fault.yaml", 240)],
    )
    watched = ["motor_voltage"]
    ts_anoms = ThreeSigma(
        current_window_s=240, sigma_k=3.0, min_baseline=30, min_current=5, sensors=watched).detect(stat_window)
    iqr_anoms = IQR(
        current_window_s=240, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=watched).detect(stat_window)
    assert ts_anoms == [], f"3σ beklenmedik tetik (varyans arızası kör olmalı): {[a.rule_name for a in ts_anoms]}"
    assert iqr_anoms == [], f"IQR beklenmedik tetik (varyans arızası kör olmalı): {[a.rule_name for a in iqr_anoms]}"

    # Tamamlayıcı kural katmanı: aynı arızayı kısa pencerede motor_voltage_erratic yakalar.
    rule_window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_electrical_fault.yaml", max_iterations=200,
    )
    erratic = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10, trip_std_v=5.0)
    assert len(erratic.detect(rule_window)) == 1


def test_clean_baseline_no_statistical_trigger(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """Clean baseline + clean tail → durağan sensörlerde statistical HİÇBİR anomali üretmez (FP yok, kriter 4)."""
    window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(_CLEAN, 364), (_CLEAN, 182)],
    )
    ts = ThreeSigma(current_window_s=182, sigma_k=3.0, min_baseline=30, min_current=5, sensors=_STATIONARY)
    iqr = IQR(current_window_s=182, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=_STATIONARY)
    assert ts.detect(window) == [], f"clean'de 3σ FP: {[a.rule_name for a in ts.detect(window)]}"
    assert iqr.detect(window) == [], f"clean'de IQR FP: {[a.rule_name for a in iqr.detect(window)]}"

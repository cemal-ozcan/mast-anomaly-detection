"""A/B/C + clean istatistiksel imza testleri (Faz 5 Iter 5.2, spec § 10, kabul kriteri 2/4).

build_statistical_window: clean baseline segment(leri) + arıza tail segmenti → uzun pencere.
Statistical dedektör içeride split_recent ile böler; current_window_s = son (arıza) segmentin
iterasyon sayısı → arıza tail "current" olur.
"""
from __future__ import annotations

import pytest

from detectors.statistical.iqr import IQR
from detectors.statistical.three_sigma import ThreeSigma
from tests.scenarios.conftest import FIXTURES, CountingClock, build_statistical_window


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

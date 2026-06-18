"""detectors.scoring.band_position_score birim testleri (Faz 8 Iter 8.4, spec § 3)."""
from __future__ import annotations

import pytest

from detectors.scoring import band_position_score, severity_from_band


def test_at_warn_is_zero() -> None:
    assert band_position_score(95.0, warn=95.0, trip=130.0) == 0.0


def test_at_trip_is_one() -> None:
    assert band_position_score(130.0, warn=95.0, trip=130.0) == 1.0


def test_midpoint_is_half() -> None:
    assert band_position_score(112.5, warn=95.0, trip=130.0) == pytest.approx(0.5)


def test_below_warn_clamps_to_zero() -> None:
    assert band_position_score(90.0, warn=95.0, trip=130.0) == 0.0


def test_above_trip_clamps_to_one() -> None:
    assert band_position_score(200.0, warn=95.0, trip=130.0) == 1.0


def test_trip_not_greater_than_warn_raises() -> None:
    with pytest.raises(ValueError, match="trip"):
        band_position_score(5.0, warn=10.0, trip=10.0)


def test_severity_below_high_cutoff_is_warning() -> None:
    assert severity_from_band(0.0, high_cutoff=0.40, critical_cutoff=0.75) == "warning"
    assert severity_from_band(0.39, high_cutoff=0.40, critical_cutoff=0.75) == "warning"


def test_severity_at_high_cutoff_is_high() -> None:
    assert severity_from_band(0.40, high_cutoff=0.40, critical_cutoff=0.75) == "high"
    assert severity_from_band(0.74, high_cutoff=0.40, critical_cutoff=0.75) == "high"


def test_severity_at_critical_cutoff_is_critical() -> None:
    assert severity_from_band(0.75, high_cutoff=0.40, critical_cutoff=0.75) == "critical"
    assert severity_from_band(1.0, high_cutoff=0.40, critical_cutoff=0.75) == "critical"


def test_severity_invalid_cutoffs_raises() -> None:
    with pytest.raises(ValueError, match="cutoff"):
        severity_from_band(0.5, high_cutoff=0.75, critical_cutoff=0.40)  # high >= critical
    with pytest.raises(ValueError, match="cutoff"):
        severity_from_band(0.5, high_cutoff=0.0, critical_cutoff=0.75)   # 0 < high gerekir

"""detectors.scoring.band_position_score birim testleri (Faz 8 Iter 8.4, spec § 3)."""
from __future__ import annotations

import pytest

from detectors.scoring import band_position_score


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

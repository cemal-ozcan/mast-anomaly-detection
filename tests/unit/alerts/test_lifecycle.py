"""alerts.lifecycle saf durum-geçiş kuralları (Faz 7 Iter 7.1, spec § 6)."""
from __future__ import annotations

import pytest

from alerts.lifecycle import (
    ACKNOWLEDGED,
    ACTIVE,
    RESOLVED,
    can_transition,
)


@pytest.mark.parametrize(
    ("current", "target", "expected"),
    [
        (ACTIVE, ACKNOWLEDGED, True),
        (ACTIVE, RESOLVED, True),
        (ACKNOWLEDGED, RESOLVED, True),
        (ACKNOWLEDGED, ACTIVE, False),
        (RESOLVED, ACTIVE, False),
        (RESOLVED, ACKNOWLEDGED, False),
        (ACTIVE, ACTIVE, False),
        (ACKNOWLEDGED, ACKNOWLEDGED, False),
    ],
)
def test_can_transition(current: str, target: str, expected: bool) -> None:
    assert can_transition(current, target) is expected


def test_can_transition_unknown_status_false() -> None:
    """Bilinmeyen mevcut durum → hiçbir geçiş geçerli değil."""
    assert can_transition("bogus", RESOLVED) is False

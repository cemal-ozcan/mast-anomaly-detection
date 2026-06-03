"""Uyarı durum makinesi: geçerli geçişler (Faz 7 Iter 7.1, spec § 6).

SAF — dış bağımlılık yok. Repository geçişleri SQL WHERE ile atomik zorlar; dashboard
hangi butonu göstereceğine bununla karar verir. Geçiş matrisi tek kaynak burada.
"""
from __future__ import annotations

ACTIVE = "active"
ACKNOWLEDGED = "acknowledged"
RESOLVED = "resolved"

# Geçerli geçişler: active→{ack,resolved}, acknowledged→{resolved}, resolved→{} (terminal).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ACTIVE: frozenset({ACKNOWLEDGED, RESOLVED}),
    ACKNOWLEDGED: frozenset({RESOLVED}),
    RESOLVED: frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    """current durumundan target durumuna geçiş geçerli mi?

    Args:
        current: Mevcut durum (active/acknowledged/resolved).
        target: Hedef durum.

    Returns:
        Geçiş ALLOWED_TRANSITIONS'ta tanımlıysa True; bilinmeyen current → False.
    """
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())

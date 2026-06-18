"""Band-pozisyon skoru: dedektörler arası ortak, karşılaştırılabilir [0,1] şiddet (Faz 8 Iter 8.4).

Anlam her dedektörde aynı: 0 = alarm (warn) sınırını yeni geçti, 1 = kritik (trip) seviyesi.
ISO 20816 zone mantığı (alarm=B/C, trip=C/D). Saf leaf — yalnız stdlib.
"""
from __future__ import annotations


def band_position_score(q: float, warn: float, trip: float) -> float:
    """`q`'nun `warn`→`trip` bandındaki konumu, `[0, 1]`'e clamp.

    Args:
        q: Ölçülen büyüklük (sensör değeri, sapma veya mesafe — non-negatif uzayda).
        warn: Alarm (tetik) sınırı → skor 0.
        trip: Kritik referans → skor 1.

    Returns:
        `(q - warn) / (trip - warn)`, `[0, 1]`'e clamp.

    Raises:
        ValueError: `trip <= warn` ise (band tanımsız).
    """
    if trip <= warn:
        raise ValueError(f"band_position_score: trip ({trip}) > warn ({warn}) olmalı")
    return max(0.0, min(1.0, (q - warn) / (trip - warn)))

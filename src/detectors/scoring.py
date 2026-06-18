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


def severity_from_band(score: float, high_cutoff: float, critical_cutoff: float) -> str:
    """Band-pozisyon skorunu (`0..1`) severity etiketine eşler (Faz 8 Iter 8.6, spec § 6).

    `0` = alarm bölgesine yeni girdi (en az "warning"), `1` = kritik (trip). Eşikler ISO 20816
    zone mantığı + sim kalibrasyonu (config-driven, hand-picked sabit yok). Band-türetilmiş
    severity tabanı "warning"dir → "info" asla dönmez ("info" yalnız validity-rule'ların config
    severity'sinde teorik olarak mümkün).

    Args:
        score: Band-pozisyon skoru `[0, 1]`.
        high_cutoff: `>= high_cutoff` → en az "high".
        critical_cutoff: `>= critical_cutoff` → "critical".

    Returns:
        `"warning" | "high" | "critical"`.

    Raises:
        ValueError: `0 < high_cutoff < critical_cutoff < 1` değilse.
    """
    if not (0.0 < high_cutoff < critical_cutoff < 1.0):
        raise ValueError(
            f"severity_from_band: 0 < high_cutoff ({high_cutoff}) < "
            f"critical_cutoff ({critical_cutoff}) < 1 olmalı"
        )
    if score >= critical_cutoff:
        return "critical"
    if score >= high_cutoff:
        return "high"
    return "warning"

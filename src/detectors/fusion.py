"""Anomali füzyonu: aynı cihaz+pencerede çoklu kuralı tek temsilci Anomaly'e birleştirir.

Spec § 5/§ 7 (minimal fusion, write-side). Detector poll turunda bir cihazın tüm
anomalilerini toplar ve `fuse_anomalies` ile tek satıra indirir (gürültü azaltma).
Gelişmiş (ağırlıklı/çok-katmanlı) fusion Faz 6.
"""
from __future__ import annotations

from detectors.base import Anomaly

# Severity sıralaması (yüksekten düşüğe karşılaştırma için).
_SEVERITY_RANK: dict[str, int] = {"critical": 3, "high": 2, "warning": 1, "info": 0}


def _rank(anomaly: Anomaly) -> tuple[int, float]:
    """Önem anahtarı: önce severity, sonra score (max ile 'top' seçimi için)."""
    return (_SEVERITY_RANK.get(anomaly.severity, 0), anomaly.score)


def fuse_anomalies(anomalies: list[Anomaly]) -> Anomaly | None:
    """Tek cihazın bir poll turundaki anomalilerini tek temsilci Anomaly'e birleştirir.

    Args:
        anomalies: Aynı cihaza ait, bir poll turunda tetiklenen anomaliler.

    Returns:
        Boş liste → None. Tek anomali → kendisi (değişmez). Çoklu → "fused(N)" temsilci:
        en yüksek (severity, score) anomali baz alınır (device_id, sensor, value, severity
        ondan); score = max; window_start = min, window_end = max; description katkıda
        bulunan kuralları (önemden düşüğe) listeler.
    """
    if not anomalies:
        return None
    top = max(anomalies, key=_rank)
    if len(anomalies) == 1:
        return top
    contributors = sorted(anomalies, key=_rank, reverse=True)
    description = " + ".join(f"{a.rule_name}({a.value:.2f})" for a in contributors)
    return Anomaly(
        device_id=top.device_id,
        rule_name=f"fused({len(anomalies)})",
        sensor=top.sensor,
        severity=top.severity,
        score=max(a.score for a in anomalies),
        window_start=min(a.window_start for a in anomalies),
        window_end=max(a.window_end for a in anomalies),
        value=top.value,
        description=description,
    )

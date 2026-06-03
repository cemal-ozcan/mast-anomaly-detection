"""Alert okuma/yönetim modeli (Faz 7 Iter 7.1, spec § 5).

Anomaly (detector yazma kontratı) DEĞİŞMEZ; Alert ayrı bir okuma görünümüdür — kimlik (id),
durum ve yaşam döngüsü zaman damgalarını içerir. Düz (flat) dataclass: DataFrame transform
ve dashboard tüketimi için sade.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Alert:
    """anomalies tablosundan okunan, yaşam döngüsü durumu olan bir uyarı."""

    id: int
    device_id: str
    rule_name: str
    sensor: str
    severity: str
    score: float
    window_start: str
    window_end: str
    value: float
    description: str
    created_at: str
    status: str
    acknowledged_at: str | None
    resolved_at: str | None

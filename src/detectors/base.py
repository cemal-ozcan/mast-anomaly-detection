"""Anomaly veri kontratı + Detector ABC (Faz 4 Iter 4.1, spec § 5).

Bu modül SAF kontrattır: yalnız pandas + dataclasses + abc import eder; storage,
ingestion veya servis katmanına bağımlı DEĞİLDİR (repository bunu import eder —
ters yönde döngü olmasın diye).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

# Sensör-sağlığı (veri-kalitesi) kuralları: skoru ikili validity bayrağı (1.0), band konumu DEĞİL
# (severity banttan türetilmez — Iter 8.4/8.6). Tek-kaynak burada (detector + dashboard paylaşır, Iter 8.8).
VALIDITY_RULES: frozenset[str] = frozenset({"sensor_out_of_range", "sensor_frozen"})


@dataclass(frozen=True)
class Anomaly:
    """Bir kuralın tetiklediği tek anomali (spec § 5).

    Attributes:
        device_id: Anomalinin ait olduğu cihaz.
        rule_name: Tetikleyen kuralın adı (örn. "motor_temperature_high").
        sensor: İlgili sensör adı.
        severity: "info" / "warning" / "critical" (kural/config-driven).
        score: 0-1 normalize şiddet skoru (fusion için, Iter 4.3).
        window_start: Pencere başı ISO 8601 ms (YYYY-MM-DDTHH:MM:SS.sssZ).
        window_end: Pencere sonu / tespit anı ISO 8601 ms.
        value: Tetikleyen değer (örn. tepe sıcaklık).
        description: İnsan-okur açıklama.
    """

    device_id: str
    rule_name: str
    sensor: str
    severity: str
    score: float
    window_start: str
    window_end: str
    value: float
    description: str


class Detector(ABC):
    """Anomali dedektörü kontratı (ARCHITECTURE.md § 4).

    Her dedektör tek-cihaz penceresini alır ve sıfır veya daha çok Anomaly döndürür.
    Pencere uzun-formattır; kolonlar: [device_id, timestamp, sensor, state, value].
    Kural ilgili sensör(ler)i `sensor` kolonundan filtreler.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Kuralın benzersiz adı (registry anahtarı + Anomaly.rule_name)."""

    @abstractmethod
    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        """Pencerede anomali ara.

        Args:
            window: Tek cihazın son N saniyelik okumaları; uzun-format
                [device_id, timestamp, sensor, state, value] kolonları.

        Returns:
            Tetiklenen Anomaly listesi (tetikleme yoksa boş liste).
        """

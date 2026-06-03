"""Dashboard saf transform helper'ları (Faz 3 spec § 5). Streamlit/DB import etmez."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from alerts.models import Alert
from ingestion.message_parser import IngestedReading

WINDOW_OPTIONS: dict[str, timedelta | None] = {
    "Son 5 dakika": timedelta(minutes=5),
    "Son 15 dakika": timedelta(minutes=15),
    "Son 1 saat": timedelta(hours=1),
    "Tümü": None,
}


def window_to_since(now: datetime, window: str) -> str | None:
    """Seçili pencere etiketinden ISO 8601 ms cutoff string üretir (publisher formatı).

    Cutoff `YYYY-MM-DDTHH:MM:SS.sssZ` (ms, `+00:00`→`Z`) — telemetri timestamp'leriyle
    aynı format, lexicographic `timestamp >= since` karşılaştırması doğru çalışsın.

    Args:
        now: Şimdiki UTC-aware datetime (test için enjekte edilir). Naive datetime
            kabul edilmez; tz-naive ise ValueError fırlatılır.
        window: WINDOW_OPTIONS anahtarlarından biri.

    Returns:
        ISO ms cutoff string; "Tümü" veya bilinmeyen pencere → None.

    Raises:
        ValueError: now tz-naive ise.
    """
    if now.tzinfo is None:
        raise ValueError("now UTC-aware datetime olmalı (naive datetime kabul edilmez)")
    # "Tümü" → None (filtresiz); bilinmeyen anahtar da None döner — çağıranlar
    # her zaman WINDOW_OPTIONS.keys() ile sınırlı olduğundan güvenli.
    delta = WINDOW_OPTIONS.get(window)
    if delta is None:
        return None
    cutoff = now - delta
    return cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def readings_to_frame(readings: list[IngestedReading]) -> pd.DataFrame:
    """IngestedReading listesini st.line_chart için DataFrame'e çevirir.

    Args:
        readings: timestamp ASC sıralı okumalar (boş olabilir).

    Returns:
        timestamp (datetime index) + value kolonlu DataFrame. Boş girdi → 0 satırlı
        ama doğru-şemalı DataFrame.
    """
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [r.timestamp for r in readings], format="ISO8601", utc=True
            ),
            "value": [r.value for r in readings],
        }
    )
    return frame.set_index("timestamp")


_ALERT_COLUMNS = ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"]


def alerts_to_frame(alerts: list[Alert]) -> pd.DataFrame:
    """Alert listesini "Uyarılar" tablosu için DataFrame'e çevirir (spec § 8).

    Args:
        alerts: fetch_alerts çıktısı (created_at DESC sıralı; boş olabilir).

    Returns:
        [zaman, cihaz, severity, sensör, kural, skor, durum, açıklama] kolonlu DataFrame;
        girdi sırasını korur. `zaman` = window_end, `skor` 2 ondalığa yuvarlanır, `durum` =
        yaşam döngüsü durumu. Boş girdi → 0 satırlı ama doğru-şemalı DataFrame.
    """
    return pd.DataFrame(
        {
            "zaman": [a.window_end for a in alerts],
            "cihaz": [a.device_id for a in alerts],
            "severity": [a.severity for a in alerts],
            "sensör": [a.sensor for a in alerts],
            "kural": [a.rule_name for a in alerts],
            "skor": [round(a.score, 2) for a in alerts],
            "durum": [a.status for a in alerts],
            "açıklama": [a.description for a in alerts],
        },
        columns=_ALERT_COLUMNS,
    )

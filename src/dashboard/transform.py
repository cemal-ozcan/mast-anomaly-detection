"""Dashboard saf transform helper'ları (Faz 3 spec § 5). Streamlit/DB import etmez."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

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
        now: Şimdiki UTC-aware datetime (test için enjekte edilir).
        window: WINDOW_OPTIONS anahtarlarından biri.

    Returns:
        ISO ms cutoff string; "Tümü" veya bilinmeyen pencere → None.
    """
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

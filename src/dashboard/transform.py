"""Dashboard saf transform helper'ları (Faz 3 spec § 5). Streamlit/DB import etmez."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from alerts.lifecycle import ACKNOWLEDGED, ACTIVE
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


def relative_time(now: datetime, ts: str) -> str:
    """ISO 8601 timestamp'i insan-okur göreli zamana çevirir ("12 sn önce").

    Args:
        now: Şimdiki UTC-aware datetime (test için enjekte edilir). tz-naive → ValueError.
        ts: Publisher/DB formatında ISO 8601 string (`...Z` veya `+00:00`).

    Returns:
        "X sn önce" / "X dk önce" / "X sa önce" / "X gün önce". Gelecek ts → "0 sn önce".

    Raises:
        ValueError: now tz-naive ise.
    """
    if now.tzinfo is None:
        raise ValueError("now UTC-aware datetime olmalı (naive datetime kabul edilmez)")
    moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    seconds = max(0, int((now - moment).total_seconds()))
    if seconds < 60:
        return f"{seconds} sn önce"
    if seconds < 3600:
        return f"{seconds // 60} dk önce"
    if seconds < 86400:
        return f"{seconds // 3600} sa önce"
    return f"{seconds // 86400} gün önce"


def readings_to_chart_frame(readings: list[IngestedReading]) -> pd.DataFrame:
    """IngestedReading listesini Altair chart frame'ine çevirir (spec § 5 tooltip: state dahil).

    timestamp INDEX değil KOLON (altair kolon encode eder) ve tooltip için state
    kolonu taşır. (Eski index'li readings_to_frame, st.line_chart ile birlikte kaldırıldı.)

    Args:
        readings: timestamp ASC sıralı okumalar (boş olabilir).

    Returns:
        [timestamp (datetime), value, state] kolonlu DataFrame.
    """
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [r.timestamp for r in readings], format="ISO8601", utc=True
            ),
            "value": [r.value for r in readings],
            "state": [r.state for r in readings],
        }
    )


def downsample_frame(frame: pd.DataFrame, max_points: int = 1000) -> pd.DataFrame:
    """Frame'i eşit aralıklı seyrelterek en çok max_points satıra indirir (spec § 5).

    Altair'in max_rows=5000 sınırı uzun pencerelerde MaxRowsError fırlatır; her grafik
    öncesi bu guard uygulanır. Küçük frame DEĞİŞMEDEN (aynı obje) döner.

    Args:
        frame: Satır sırası anlamlı (timestamp ASC) DataFrame.
        max_points: Üst sınır (>0).

    Returns:
        En çok max_points satırlı, sıra + ilk/son satır korunmuş DataFrame.
    """
    if len(frame) <= max_points:
        return frame
    indices = np.unique(np.linspace(0, len(frame) - 1, num=max_points, dtype=int))
    return frame.iloc[indices]


OPEN_STATUSES: tuple[str, ...] = (ACTIVE, ACKNOWLEDGED)


def latest_alert_per_device(alerts: list[Alert]) -> list[Alert]:
    """Cihaz başına en son AÇIK uyarıyı döndürür — "Cihaz özeti" görünümü (spec § 2 flicker).

    Args:
        alerts: created_at DESC sıralı uyarılar (fetch_alerts çıktısı; tüm durumlar olabilir).

    Returns:
        Cihaz başına ilk görülen açık (active|acknowledged) uyarı; girdi sırası korunur.
        Açık uyarısı olmayan cihaz listede YOK (kartlar zaten OK gösterir).
    """
    seen: set[str] = set()
    result: list[Alert] = []
    for alert in alerts:
        if alert.status not in OPEN_STATUSES or alert.device_id in seen:
            continue
        seen.add(alert.device_id)
        result.append(alert)
    return result


_ALERT_COLUMNS = ["zaman", "ne zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"]

_SEVERITY_EMOJI: dict[str, str] = {"critical": "🔴", "high": "🟠", "warning": "🟡"}

# Tema B severity paleti (spec § 4) — satır zemin + metin rengi
_SEVERITY_ROW_CSS: dict[str, str] = {
    "critical": "background-color: #fef2f2; color: #b91c1c",
    "high": "background-color: #fff7ed; color: #c2410c",
    "warning": "background-color: #fefce8; color: #a16207",
}


def alerts_to_frame(alerts: list[Alert], now: datetime) -> pd.DataFrame:
    """Alert listesini severity-emoji'li + göreli zamanlı "Uyarılar" tablosuna çevirir (spec § 3).

    Args:
        alerts: fetch_alerts çıktısı (created_at DESC sıralı; boş olabilir).
        now: Göreli zaman hesabı için şimdiki UTC-aware datetime (enjekte edilir).

    Returns:
        [zaman, ne zaman, cihaz, severity, sensör, kural, skor, durum, açıklama] kolonlu
        DataFrame; girdi sırasını korur. `zaman` = window_end, `ne zaman` = created_at'ten
        göreli, `severity` emoji önekli. Boş girdi → 0 satırlı doğru-şemalı DataFrame.
    """
    return pd.DataFrame(
        {
            "zaman": [a.window_end for a in alerts],
            "ne zaman": [relative_time(now, a.created_at) for a in alerts],
            "cihaz": [a.device_id for a in alerts],
            "severity": [f"{_SEVERITY_EMOJI.get(a.severity, '⚪')} {a.severity}" for a in alerts],
            "sensör": [a.sensor for a in alerts],
            "kural": [a.rule_name for a in alerts],
            "skor": [round(a.score, 2) for a in alerts],
            "durum": [a.status for a in alerts],
            "açıklama": [a.description for a in alerts],
        },
        columns=_ALERT_COLUMNS,
    )


def severity_row_style(row: pd.Series[Any]) -> list[str]:
    """pandas Styler.apply(axis=1) için satır-bazlı severity CSS'i üretir (spec § 3/§ 4).

    Args:
        row: alerts_to_frame çıktısının bir satırı ("severity" kolonu emoji önekli).

    Returns:
        Satırdaki her hücre için aynı CSS string'i; eşleşme yoksa boş string'ler.
    """
    severity = str(row.get("severity", ""))
    for key, css in _SEVERITY_ROW_CSS.items():
        if key in severity:
            return [css] * len(row)
    return [""] * len(row)

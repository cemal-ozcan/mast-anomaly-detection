"""Dashboard saf transform helper'ları (Faz 3 spec § 5). Streamlit/DB import etmez."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from alerts.lifecycle import ACKNOWLEDGED, ACTIVE
from alerts.models import Alert
from detectors.base import VALIDITY_RULES
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


def is_data_quality_alert(alert: Alert) -> bool:
    """Uyarı veri-kalitesi ekseninde mi (yalnız validity kurallarından mı oluşuyor)? (Iter 8.8).

    rule_set'teki TÜM kurallar VALIDITY_RULES'taysa True (sensör bütünlüğü); en az bir kestirimci
    kural varsa False (arıza ekseni). rule_set boş/None → False (kestirimci varsay).

    Args:
        alert: Sınıflandırılacak uyarı (rule_set fingerprint'i taşımalı).

    Returns:
        Veri-kalitesi (sensör-sağlığı) ekseninde mi.
    """
    if not alert.rule_set:
        return False
    rules = {r for r in alert.rule_set.split(",") if r}
    return bool(rules) and rules <= VALIDITY_RULES


def split_alerts_by_axis(alerts: list[Alert]) -> tuple[list[Alert], list[Alert]]:
    """Uyarıları (kestirimci_arızalar, veri_kalitesi) olarak ikiye böler; sıra korunur (Iter 8.8).

    Args:
        alerts: Bölünecek uyarılar.

    Returns:
        (faults, data_quality) — sırasıyla kestirimci arıza ve sensör-sağlığı uyarıları.
    """
    faults = [a for a in alerts if not is_data_quality_alert(a)]
    data_quality = [a for a in alerts if is_data_quality_alert(a)]
    return faults, data_quality

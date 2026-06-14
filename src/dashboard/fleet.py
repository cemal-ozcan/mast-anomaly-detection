"""Filo sağlık + KPI türetimi (Faz 8 Iter 8.2 spec § 7). Saf — streamlit/DB import etmez."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alerts.models import Alert
from dashboard.transform import OPEN_STATUSES, relative_time
from ingestion.message_parser import IngestedReading

BADGE_OK = "ok"
BADGE_WARNING = "warning"
BADGE_CRITICAL = "critical"

_SEVERITY_RANK = {"warning": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class SensorSnapshot:
    """Bir sensörün karttaki son değeri."""

    sensor: str
    value: float
    unit: str
    highlighted: bool  # açık uyarıyla ilişkili sensör (spec § 3)


@dataclass(frozen=True)
class DeviceHealth:
    """Bir cihazın filo kartı verisi (spec § 3/§ 7)."""

    device_id: str
    badge: str  # BADGE_OK | BADGE_WARNING | BADGE_CRITICAL
    state: str
    snapshots: tuple[SensorSnapshot, ...]
    open_alert_count: int
    top_rule: str | None  # en yüksek severity'li (eşitlikte en güncel) açık uyarının kuralı


@dataclass(frozen=True)
class FleetKpis:
    """KPI satırı verisi (spec § 3/§ 7)."""

    device_count: int
    open_alert_count: int
    critical_alert_count: int
    last_detection: str  # göreli zaman veya "—"


def derive_device_health(
    device_id: str, latest_readings: list[IngestedReading], alerts: list[Alert]
) -> DeviceHealth:
    """Bir cihazın kart verisini son okumalar + uyarılardan türetir (spec § 7).

    Args:
        device_id: Cihaz kimliği.
        latest_readings: fetch_latest_readings çıktısı (TÜM cihazlar; içeride filtrelenir).
        alerts: fetch_alerts çıktısı (TÜM durumlar; açıklar içeride filtrelenir).

    Returns:
        DeviceHealth — rozet (critical > warning > ok), en güncel okumanın state'i,
        sensör snapshot'ları (uyarılı sensör vurgulu), açık uyarı sayısı, en kritik kural.
    """
    open_alerts = [
        a for a in alerts if a.device_id == device_id and a.status in OPEN_STATUSES
    ]
    readings = [r for r in latest_readings if r.device_id == device_id]
    flagged_sensors = {a.sensor for a in open_alerts}
    snapshots = tuple(
        SensorSnapshot(r.sensor, r.value, r.unit, r.sensor in flagged_sensors)
        for r in readings
    )
    state = max(readings, key=lambda r: r.timestamp).state if readings else "?"
    if any(a.severity == "critical" for a in open_alerts):
        badge = BADGE_CRITICAL
    elif open_alerts:
        badge = BADGE_WARNING
    else:
        badge = BADGE_OK
    top_rule: str | None = None
    if open_alerts:
        top = max(open_alerts, key=lambda a: (_SEVERITY_RANK.get(a.severity, 0), a.created_at))
        top_rule = top.rule_name
    return DeviceHealth(device_id, badge, state, snapshots, len(open_alerts), top_rule)


def derive_fleet(
    devices: list[str], latest_readings: list[IngestedReading], alerts: list[Alert]
) -> list[DeviceHealth]:
    """Tüm filo kartlarını türetir (cihaz sırası korunur)."""
    return [derive_device_health(d, latest_readings, alerts) for d in devices]


def compute_kpis(devices: list[str], alerts: list[Alert], now: datetime) -> FleetKpis:
    """KPI satırını tek fetch_alerts sonucundan client-side türetir (spec § 6/§ 7).

    Args:
        devices: Cihaz listesi.
        alerts: fetch_alerts(None, ...) çıktısı (tüm durumlar).
        now: Göreli zaman için UTC-aware datetime.

    Returns:
        FleetKpis — açık = status ∈ OPEN_STATUSES; kritik = açık ∧ severity=critical;
        son tespit = en güncel created_at göreli (uyarı yoksa "—").
    """
    open_alerts = [a for a in alerts if a.status in OPEN_STATUSES]
    critical_count = sum(1 for a in open_alerts if a.severity == "critical")
    last_detection = "—"
    if alerts:
        latest = max(alerts, key=lambda a: a.created_at)
        last_detection = relative_time(now, latest.created_at)
    return FleetKpis(len(devices), len(open_alerts), critical_count, last_detection)

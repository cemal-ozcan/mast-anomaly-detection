"""dashboard.fleet türetim birim testleri (Faz 8 Iter 8.2 spec § 7)."""
from __future__ import annotations

from datetime import UTC, datetime

from alerts.models import Alert
from ingestion.message_parser import IngestedReading


def _alert(id_: int, device: str, status: str = "active", severity: str = "warning",
           sensor: str = "motor_current", rule: str = "motor_current_high",
           created_at: str = "2026-06-03T12:00:00.000Z") -> Alert:
    return Alert(id=id_, device_id=device, rule_name=rule, sensor=sensor, severity=severity,
                 score=0.5, window_start="s", window_end="e", value=1.0, description="d",
                 created_at=created_at, status=status, acknowledged_at=None, resolved_at=None)


def _reading(device: str, sensor: str, value: float = 1.0, unit: str = "A",
             state: str = "idle", ts: str = "2026-06-03T12:00:00.000Z") -> IngestedReading:
    return IngestedReading(device_id=device, sensor=sensor, timestamp=ts,
                           state=state, value=value, unit=unit)


def test_badge_critical_beats_warning() -> None:
    """Açık critical varsa rozet critical; yalnız warning → warning; açık yoksa ok."""
    from dashboard.fleet import BADGE_CRITICAL, BADGE_OK, BADGE_WARNING, derive_device_health

    readings = [_reading("dev", "motor_current")]
    crit = derive_device_health("dev", readings, [
        _alert(1, "dev", severity="warning"), _alert(2, "dev", severity="critical")])
    warn = derive_device_health("dev", readings, [_alert(1, "dev", severity="warning")])
    ok = derive_device_health("dev", readings, [_alert(1, "dev", status="resolved")])
    assert crit.badge == BADGE_CRITICAL
    assert warn.badge == BADGE_WARNING
    assert ok.badge == BADGE_OK


def test_device_health_snapshots_highlight_and_state() -> None:
    """Uyarıyla ilişkili sensör vurgulu; state en güncel okumadan; unit passthrough."""
    from dashboard.fleet import derive_device_health

    readings = [
        _reading("dev", "motor_current", value=11.2, unit="A", state="raising",
                 ts="2026-06-03T12:00:01.000Z"),
        _reading("dev", "vibration", value=0.05, unit="g", state="idle",
                 ts="2026-06-03T12:00:00.000Z"),
        _reading("other", "motor_current", value=0.5),  # başka cihaz — dahil edilmez
    ]
    health = derive_device_health("dev", readings, [_alert(1, "dev", sensor="motor_current")])
    assert health.state == "raising"  # en güncel okuma 12:00:01
    by_sensor = {s.sensor: s for s in health.snapshots}
    assert set(by_sensor) == {"motor_current", "vibration"}
    assert by_sensor["motor_current"].highlighted is True
    assert by_sensor["motor_current"].unit == "A"
    assert by_sensor["vibration"].highlighted is False
    assert health.open_alert_count == 1


def test_top_rule_highest_severity_then_recency() -> None:
    """En yüksek severity'li, eşitlikte en güncel açık uyarının kuralı seçilir."""
    from dashboard.fleet import derive_device_health

    alerts = [
        _alert(1, "dev", severity="warning", rule="old_warning", created_at="2026-06-03T11:00:00.000Z"),
        _alert(2, "dev", severity="critical", rule="the_critical", created_at="2026-06-03T10:00:00.000Z"),
        _alert(3, "dev", severity="warning", rule="new_warning", created_at="2026-06-03T12:00:00.000Z"),
    ]
    health = derive_device_health("dev", [_reading("dev", "motor_current")], alerts)
    assert health.top_rule == "the_critical"


def test_compute_kpis_counts_and_last_detection() -> None:
    """KPI: açık = active+acknowledged; kritik = açık ∧ critical; son tespit göreli."""
    from dashboard.fleet import compute_kpis

    alerts = [
        _alert(1, "a", status="active", severity="critical", created_at="2026-06-03T12:00:00.000Z"),
        _alert(2, "b", status="acknowledged", severity="warning", created_at="2026-06-03T11:59:00.000Z"),
        _alert(3, "c", status="resolved", severity="critical", created_at="2026-06-03T11:00:00.000Z"),
    ]
    now = datetime(2026, 6, 3, 12, 0, 30, tzinfo=UTC)
    kpis = compute_kpis(["a", "b", "c"], alerts, now)
    assert kpis.device_count == 3
    assert kpis.open_alert_count == 2
    assert kpis.critical_alert_count == 1
    assert kpis.last_detection == "30 sn önce"


def test_compute_kpis_no_alerts_dash() -> None:
    """Hiç uyarı yoksa son tespit '—'."""
    from dashboard.fleet import compute_kpis

    kpis = compute_kpis(["a"], [], datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC))
    assert kpis.last_detection == "—"
    assert kpis.open_alert_count == 0


def test_top_rule_equal_severity_recency_wins() -> None:
    """Eşit severity'de en güncel created_at'li açık uyarının kuralı seçilir (tie-break)."""
    from dashboard.fleet import derive_device_health

    alerts = [
        _alert(1, "dev", severity="warning", rule="old", created_at="2026-06-03T11:00:00.000Z"),
        _alert(2, "dev", severity="warning", rule="new", created_at="2026-06-03T12:00:00.000Z"),
    ]
    health = derive_device_health("dev", [_reading("dev", "motor_current")], alerts)
    assert health.top_rule == "new"

"""dashboard.transform.alerts_to_frame birim testi (Faz 7 Iter 7.1 + Faz 8 Iter 8.2)."""
from __future__ import annotations


def test_alerts_to_frame_columns_and_status() -> None:
    """alerts_to_frame durum + göreli zaman kolonu içerir; severity emoji'li; skor yuvarlanır."""
    from datetime import UTC, datetime

    from alerts.models import Alert
    from dashboard.transform import alerts_to_frame

    alerts = [
        Alert(id=1, device_id="device_001", rule_name="motor_current_high", sensor="motor_current",
              severity="critical", score=0.912, window_start="s", window_end="2026-06-03T10:00:00.000Z",
              value=10.0, description="d", created_at="2026-06-03T10:00:05.000Z", status="active",
              acknowledged_at=None, resolved_at=None),
    ]
    now = datetime(2026, 6, 3, 10, 0, 17, tzinfo=UTC)
    frame = alerts_to_frame(alerts, now)
    assert list(frame.columns) == [
        "zaman", "ne zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"
    ]
    assert frame.iloc[0]["durum"] == "active"
    assert frame.iloc[0]["skor"] == 0.91
    assert frame.iloc[0]["zaman"] == "2026-06-03T10:00:00.000Z"
    assert frame.iloc[0]["ne zaman"] == "12 sn önce"
    assert frame.iloc[0]["severity"] == "🔴 critical"


def test_alerts_to_frame_empty_correct_schema() -> None:
    """Boş girdi → 0 satırlı, doğru kolonlu DataFrame."""
    from datetime import UTC, datetime

    from dashboard.transform import alerts_to_frame

    frame = alerts_to_frame([], datetime(2026, 6, 3, 10, 0, 0, tzinfo=UTC))
    assert list(frame.columns) == [
        "zaman", "ne zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"
    ]
    assert len(frame) == 0


def _alert(id_: int, device: str, status: str, created_at: str, severity: str = "warning") -> object:
    """Test Alert fabrikası (yalnız bu dosyada)."""
    from alerts.models import Alert

    return Alert(id=id_, device_id=device, rule_name=f"rule_{id_}", sensor="motor_current",
                 severity=severity, score=0.5, window_start="s", window_end="e",
                 value=1.0, description="d", created_at=created_at, status=status,
                 acknowledged_at=None, resolved_at=None)


def test_latest_alert_per_device_keeps_first_open_per_device() -> None:
    """created_at DESC girdide cihaz başına İLK açık uyarı kalır; resolved atlanır."""
    from dashboard.transform import latest_alert_per_device

    alerts = [
        _alert(5, "device_002", "active", "2026-06-03T12:05:00.000Z"),
        _alert(4, "device_002", "resolved", "2026-06-03T12:04:00.000Z"),
        _alert(3, "device_001", "acknowledged", "2026-06-03T12:03:00.000Z"),
        _alert(2, "device_002", "active", "2026-06-03T12:02:00.000Z"),
        _alert(1, "device_001", "active", "2026-06-03T12:01:00.000Z"),
    ]
    result = latest_alert_per_device(alerts)  # type: ignore[arg-type]
    assert [(a.id, a.device_id) for a in result] == [(5, "device_002"), (3, "device_001")]


def test_latest_alert_per_device_all_resolved_empty() -> None:
    """Yalnız resolved uyarılar → boş liste (açık uyarı yok)."""
    from dashboard.transform import latest_alert_per_device

    alerts = [_alert(1, "device_001", "resolved", "2026-06-03T12:00:00.000Z")]
    assert latest_alert_per_device(alerts) == []  # type: ignore[arg-type]


def test_severity_emoji_fallback() -> None:
    """Bilinmeyen severity ⚪ ile işaretlenir (çökmez)."""
    from datetime import UTC, datetime

    from dashboard.transform import alerts_to_frame

    a = _alert(1, "device_001", "active", "2026-06-03T10:00:00.000Z", severity="exotic")
    frame = alerts_to_frame([a], datetime(2026, 6, 3, 10, 0, 5, tzinfo=UTC))  # type: ignore[list-item]
    assert frame.iloc[0]["severity"] == "⚪ exotic"


def test_severity_row_style_colors_by_severity() -> None:
    """critical/warning satırları CSS alır; OK/bilinmeyen boş string listesi."""
    from datetime import UTC, datetime

    from dashboard.transform import alerts_to_frame, severity_row_style

    crit = _alert(1, "device_001", "active", "2026-06-03T10:00:00.000Z", severity="critical")
    warn = _alert(2, "device_002", "active", "2026-06-03T10:00:00.000Z", severity="warning")
    frame = alerts_to_frame([crit, warn], datetime(2026, 6, 3, 10, 0, 5, tzinfo=UTC))  # type: ignore[list-item]
    crit_styles = severity_row_style(frame.iloc[0])
    warn_styles = severity_row_style(frame.iloc[1])
    assert len(crit_styles) == len(frame.columns)
    assert all("#fef2f2" in s for s in crit_styles)
    assert all("#fefce8" in s for s in warn_styles)

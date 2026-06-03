"""dashboard.transform.alerts_to_frame birim testi (Faz 7 Iter 7.1)."""
from __future__ import annotations


def test_alerts_to_frame_columns_and_status() -> None:
    """alerts_to_frame durum kolonu içerir; girdi sırasını korur; skor yuvarlanır."""
    from alerts.models import Alert
    from dashboard.transform import alerts_to_frame

    alerts = [
        Alert(id=1, device_id="device_001", rule_name="motor_current_high", sensor="motor_current",
              severity="high", score=0.912, window_start="s", window_end="2026-06-03T10:00:00.000Z",
              value=10.0, description="d", created_at="c", status="active",
              acknowledged_at=None, resolved_at=None),
    ]
    frame = alerts_to_frame(alerts)
    assert list(frame.columns) == ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"]
    assert frame.iloc[0]["durum"] == "active"
    assert frame.iloc[0]["skor"] == 0.91
    assert frame.iloc[0]["zaman"] == "2026-06-03T10:00:00.000Z"


def test_alerts_to_frame_empty_correct_schema() -> None:
    """Boş girdi → 0 satırlı, doğru kolonlu DataFrame."""
    from dashboard.transform import alerts_to_frame

    frame = alerts_to_frame([])
    assert list(frame.columns) == ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"]
    assert len(frame) == 0

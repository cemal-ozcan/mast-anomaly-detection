"""dashboard.transform uyarı helper'ları: latest_alert_per_device + eksen sınıflandırma testleri."""
from __future__ import annotations

from alerts.models import Alert
from dashboard.transform import (
    is_data_quality_alert,
    latest_alert_per_device,
    split_alerts_by_axis,
)


def _alert(id_: int, device: str, status: str, created_at: str, severity: str = "warning") -> Alert:
    """Test Alert fabrikası (yalnız bu dosyada)."""
    return Alert(id=id_, device_id=device, rule_name=f"rule_{id_}", sensor="motor_current",
                 severity=severity, score=0.5, window_start="s", window_end="e",
                 value=1.0, description="d", created_at=created_at, status=status,
                 acknowledged_at=None, resolved_at=None)


def test_latest_alert_per_device_keeps_first_open_per_device() -> None:
    """created_at DESC girdide cihaz başına İLK açık uyarı kalır; resolved atlanır."""
    alerts = [
        _alert(5, "device_002", "active", "2026-06-03T12:05:00.000Z"),
        _alert(4, "device_002", "resolved", "2026-06-03T12:04:00.000Z"),
        _alert(3, "device_001", "acknowledged", "2026-06-03T12:03:00.000Z"),
        _alert(2, "device_002", "active", "2026-06-03T12:02:00.000Z"),
        _alert(1, "device_001", "active", "2026-06-03T12:01:00.000Z"),
    ]
    result = latest_alert_per_device(alerts)
    assert [(a.id, a.device_id) for a in result] == [(5, "device_002"), (3, "device_001")]


def test_latest_alert_per_device_all_resolved_empty() -> None:
    """Yalnız resolved uyarılar → boş liste (açık uyarı yok)."""
    alerts = [_alert(1, "device_001", "resolved", "2026-06-03T12:00:00.000Z")]
    assert latest_alert_per_device(alerts) == []


def _alert_rs(rule_set: str | None, device: str = "d1") -> Alert:
    return Alert(id=1, device_id=device, rule_name="r", sensor="s", severity="high", score=1.0,
                 window_start="a", window_end="b", value=1.0, description="d", created_at="c",
                 status="active", acknowledged_at=None, resolved_at=None, rule_set=rule_set)


def test_is_data_quality_single_validity_rule() -> None:
    assert is_data_quality_alert(_alert_rs("sensor_out_of_range")) is True
    assert is_data_quality_alert(_alert_rs("sensor_frozen")) is True


def test_is_data_quality_predictive_rule() -> None:
    assert is_data_quality_alert(_alert_rs("motor_current_high")) is False


def test_is_data_quality_mixed_fused_is_fault() -> None:
    assert is_data_quality_alert(_alert_rs("motor_current_high,sensor_out_of_range")) is False


def test_is_data_quality_multi_validity_is_dq() -> None:
    assert is_data_quality_alert(_alert_rs("sensor_frozen,sensor_out_of_range")) is True


def test_is_data_quality_empty_rule_set_is_fault() -> None:
    assert is_data_quality_alert(_alert_rs(None)) is False
    assert is_data_quality_alert(_alert_rs("")) is False


def test_split_alerts_by_axis_partitions_preserving_order() -> None:
    alerts = [_alert_rs("motor_current_high", "d1"), _alert_rs("sensor_out_of_range", "d2"),
              _alert_rs("vibration_elevated", "d3")]
    faults, dq = split_alerts_by_axis(alerts)
    assert [a.device_id for a in faults] == ["d1", "d3"]
    assert [a.device_id for a in dq] == ["d2"]

"""service saf yardımcıları: apply_band_severity + _reconcile_status (Faz 8 Iter 8.6, spec § 6/§ 7)."""
from __future__ import annotations

from alerts.models import Alert
from detectors.base import Anomaly
from detectors.config import SeverityBands
from detectors.service import _should_reactivate, apply_band_severity

_BANDS = SeverityBands(high_cutoff=0.40, critical_cutoff=0.75)


def _anom(rule: str, score: float, severity: str = "warning") -> Anomaly:
    return Anomaly(device_id="d", rule_name=rule, sensor="s", severity=severity, score=score,
                   window_start="a", window_end="b", value=1.0, description="x")


def _alert(status: str, severity: str, ack: str | None) -> Alert:
    return Alert(id=1, device_id="d", rule_name="r", sensor="s", severity=severity, score=0.5,
                 window_start="a", window_end="b", value=1.0, description="x",
                 created_at="c", status=status, acknowledged_at=ack, resolved_at=None)


def test_apply_band_severity_derives_for_band_rule() -> None:
    assert apply_band_severity(_anom("motor_current_high", 0.10), _BANDS).severity == "warning"
    assert apply_band_severity(_anom("motor_current_high", 0.50), _BANDS).severity == "high"
    assert apply_band_severity(_anom("motor_current_high", 0.90), _BANDS).severity == "critical"


def test_apply_band_severity_exempts_validity_rules() -> None:
    a = _anom("sensor_out_of_range", 1.0, severity="high")
    assert apply_band_severity(a, _BANDS) is a  # değişmeden döner (config severity korunur)
    f = _anom("sensor_frozen", 1.0, severity="warning")
    assert apply_band_severity(f, _BANDS).severity == "warning"


def test_should_reactivate_true_for_acknowledged_band_up() -> None:
    assert _should_reactivate(_alert("acknowledged", "high", "t"), "critical") is True


def test_should_reactivate_false_within_band() -> None:
    assert _should_reactivate(_alert("acknowledged", "high", "t"), "high") is False
    assert _should_reactivate(_alert("acknowledged", "critical", "t"), "high") is False


def test_should_reactivate_false_for_active() -> None:
    # active uyarı (zaten dikkat çekiyor) band-up olsa da re-activate gerektirmez.
    assert _should_reactivate(_alert("active", "warning", None), "critical") is False

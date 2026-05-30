"""detectors.fusion: çoklu anomaliyi tek temsilci Anomaly'e birleştirme (Faz 4 Iter 4.3, spec § 5/§ 7)."""
from __future__ import annotations

from detectors.base import Anomaly
from detectors.fusion import fuse_anomalies


def _anom(
    *,
    rule_name: str,
    severity: str = "warning",
    score: float = 0.5,
    sensor: str = "motor_current",
    value: float = 1.0,
    window_start: str = "2026-05-30T00:00:00.000Z",
    window_end: str = "2026-05-30T00:01:00.000Z",
    device_id: str = "device_001",
) -> Anomaly:
    return Anomaly(
        device_id=device_id,
        rule_name=rule_name,
        sensor=sensor,
        severity=severity,
        score=score,
        window_start=window_start,
        window_end=window_end,
        value=value,
        description=f"{rule_name} desc",
    )


def test_empty_returns_none() -> None:
    assert fuse_anomalies([]) is None


def test_single_returns_same_anomaly_unchanged() -> None:
    """Tek anomali füzyona girmez — kendi rule_name'iyle aynen döner."""
    a = _anom(rule_name="motor_current_high", severity="high", score=0.4)
    fused = fuse_anomalies([a])
    assert fused is a


def test_multiple_fuses_into_representative() -> None:
    """Çoklu → 'fused(N)'; en yüksek severity baz; skor=max; pencere min/max; açıklama katkılar."""
    a1 = _anom(
        rule_name="motor_current_high", severity="high", score=0.4,
        sensor="motor_current", value=10.0,
        window_start="2026-05-30T00:00:05.000Z", window_end="2026-05-30T00:00:50.000Z",
    )
    a2 = _anom(
        rule_name="vibration_elevated", severity="warning", score=0.9,
        sensor="vibration", value=0.45,
        window_start="2026-05-30T00:00:00.000Z", window_end="2026-05-30T00:01:00.000Z",
    )
    fused = fuse_anomalies([a1, a2])
    assert fused is not None
    assert fused.rule_name == "fused(2)"
    assert fused.device_id == "device_001"
    assert fused.severity == "high"          # en yüksek severity (a1)
    assert fused.sensor == "motor_current"   # top katkının sensörü (a1, severity yüksek)
    assert fused.value == 10.0               # top katkının değeri
    assert fused.score == 0.9                # max skor (a2)
    assert fused.window_start == "2026-05-30T00:00:00.000Z"  # min
    assert fused.window_end == "2026-05-30T00:01:00.000Z"    # max
    assert "motor_current_high" in fused.description
    assert "vibration_elevated" in fused.description


def test_top_chosen_by_severity_then_score() -> None:
    """severity eşitse skor belirler; severity farklıysa severity baskın (skor düşük olsa da)."""
    crit_low = _anom(rule_name="motor_temperature_high", severity="critical", score=0.1, sensor="motor_temperature", value=95.0)
    warn_high = _anom(rule_name="motor_voltage_erratic", severity="warning", score=1.0, sensor="motor_voltage", value=18.0)
    fused = fuse_anomalies([warn_high, crit_low])
    assert fused is not None
    assert fused.severity == "critical"          # severity baskın
    assert fused.sensor == "motor_temperature"   # critical olan top
    assert fused.value == 95.0
    assert fused.score == 1.0                     # ama skor yine max (warn_high)

"""dashboard.transform.anomalies_to_frame birim testi (Faz 4 Iter 4.3)."""
from __future__ import annotations

from dashboard.transform import anomalies_to_frame
from detectors.base import Anomaly


def _anom(rule_name: str = "motor_current_high", device: str = "device_001") -> Anomaly:
    return Anomaly(
        device_id=device,
        rule_name=rule_name,
        sensor="motor_current",
        severity="high",
        score=0.87,
        window_start="2026-05-30T00:00:00.000Z",
        window_end="2026-05-30T00:01:00.000Z",
        value=10.5,
        description=f"{rule_name} açıklaması",
    )


def test_empty_returns_correct_schema() -> None:
    """Boş liste → 0 satırlı ama doğru kolonlu DataFrame."""
    frame = anomalies_to_frame([])
    assert list(frame.columns) == ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "açıklama"]
    assert len(frame) == 0


def test_maps_fields_to_columns() -> None:
    """Her Anomaly alanı doğru kolona eşlenir; skor 2 ondalığa yuvarlanır."""
    frame = anomalies_to_frame([_anom()])
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["zaman"] == "2026-05-30T00:01:00.000Z"  # window_end
    assert row["cihaz"] == "device_001"
    assert row["severity"] == "high"
    assert row["sensör"] == "motor_current"
    assert row["kural"] == "motor_current_high"
    assert row["skor"] == 0.87
    assert row["açıklama"] == "motor_current_high açıklaması"


def test_preserves_order() -> None:
    """Girdi sırası (repository created_at DESC) korunur."""
    frame = anomalies_to_frame([_anom(rule_name="a"), _anom(rule_name="b")])
    assert list(frame["kural"]) == ["a", "b"]

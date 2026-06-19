"""dashboard.charts Altair builder birim testleri (Faz 8 Iter 8.2 spec § 5)."""
from __future__ import annotations

from alerts.models import Alert
from dashboard.transform import readings_to_chart_frame
from ingestion.message_parser import IngestedReading


def _readings(n: int = 5) -> list[IngestedReading]:
    return [
        IngestedReading(device_id="dev", sensor="motor_current",
                        timestamp=f"2026-06-03T12:00:0{i}.000Z", state="raising",
                        value=float(i), unit="A")
        for i in range(n)
    ]


def _alert(sensor: str = "motor_current") -> Alert:
    return Alert(id=1, device_id="dev", rule_name="motor_current_high", sensor=sensor,
                 severity="critical", score=0.86,
                 window_start="2026-06-03T12:00:01.000Z", window_end="2026-06-03T12:00:03.000Z",
                 value=3.0, description="d", created_at="2026-06-03T12:00:03.000Z",
                 status="active", acknowledged_at=None, resolved_at=None)


def test_chart_without_alerts_single_line_layer() -> None:
    """Uyarı yoksa katmansız tek çizgi chart döner (spec § 5 boş overlay)."""
    from dashboard.charts import build_sensor_chart

    chart = build_sensor_chart(readings_to_chart_frame(_readings()), [], "motor_current", "A")
    spec = chart.to_dict()
    assert "layer" not in spec
    assert spec["mark"]["type"] == "line"
    assert spec["encoding"]["y"]["title"] == "motor_current (A)"


def test_chart_with_alert_has_four_layers() -> None:
    """Uyarılı chart 4 katman: bant(rect) + çizgi(rule) + etiket(text) + telemetri(line)."""
    from dashboard.charts import build_sensor_chart

    chart = build_sensor_chart(
        readings_to_chart_frame(_readings()), [_alert()], "motor_current", "A")
    spec = chart.to_dict()
    marks = [layer["mark"]["type"] for layer in spec["layer"]]
    assert marks == ["rect", "rule", "text", "line"]


def test_chart_ignores_other_sensor_alerts() -> None:
    """Başka sensörün uyarısı bu grafiğe bant ÇİZMEZ (fused temsilci-sensör kuralı)."""
    from dashboard.charts import build_sensor_chart

    chart = build_sensor_chart(
        readings_to_chart_frame(_readings()), [_alert(sensor="vibration")], "motor_current", "A")
    assert "layer" not in chart.to_dict()


def test_overlay_frame_label_format() -> None:
    """Etiket '⚠ {rule} ({score:.2f})' formatında."""
    from dashboard.charts import alerts_to_overlay_frame

    frame = alerts_to_overlay_frame([_alert()])
    assert frame.iloc[0]["label"] == "⚠ motor_current_high (0.86)"
    assert list(frame.columns) == ["window_start", "window_end", "severity", "label"]


def test_build_sensor_chart_has_fixed_height() -> None:
    """build_sensor_chart okunabilirlik için sabit yükseklik taşır (2×3 ızgara eşit hizalama)."""
    import pandas as pd

    from dashboard.charts import build_sensor_chart

    frame = pd.DataFrame({"timestamp": pd.to_datetime(["2026-06-19T12:00:00Z"], utc=True),
                          "value": [1.0], "state": ["holding"]})
    d = build_sensor_chart(frame, [], "motor_current", "A").to_dict()
    assert d.get("height") == 200 or d.get("spec", {}).get("height") == 200

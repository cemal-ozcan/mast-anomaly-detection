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
    """Uyarı/band yoksa katmansız tek çizgi chart döner; y-başlığı YOK (ham kod adı kalktı)."""
    from dashboard.charts import build_sensor_chart

    chart = build_sensor_chart(readings_to_chart_frame(_readings()), [], "motor_current", "A")
    spec = chart.to_dict()
    assert "layer" not in spec
    assert spec["mark"]["type"] == "line"
    assert spec["encoding"]["y"].get("title") in (None, "")  # ham kod adı yok


def test_chart_with_alert_has_overlay_layers_no_text() -> None:
    """Uyarılı (band'sız) chart: bant(rect) + telemetri(line) + başlangıç(rule); etiket(text) YOK."""
    from dashboard.charts import build_sensor_chart

    chart = build_sensor_chart(
        readings_to_chart_frame(_readings()), [_alert()], "motor_current", "A")
    spec = chart.to_dict()
    marks = [layer["mark"]["type"] for layer in spec["layer"]]
    assert "text" not in marks  # üst üste binen ham etiket kaldırıldı
    assert marks == ["rect", "line", "rule"]  # bant → çizgi → başlangıç


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


def test_chart_band_adds_zone_and_threshold_layers() -> None:
    """band verilince: bölge rect (y2'li, tam-genişlik x'li) + eşik çizgileri (y'li rule) + genişlemiş y-domain."""
    from dashboard.charts import build_sensor_chart
    from dashboard.thresholds import LevelBand

    frame = readings_to_chart_frame(_readings())  # value 0..4
    band = LevelBand(warn=9.0, trip=11.0)
    spec = build_sensor_chart(frame, [], "motor_current", "A", band=band).to_dict()
    assert "layer" in spec
    # bölge: y2'li mark_rect; tam-genişlik için x+x2 de taşır (render-doğru)
    zones = [ly for ly in spec["layer"]
             if ly["mark"]["type"] == "rect" and "y2" in ly.get("encoding", {})]
    assert zones
    assert "x" in zones[0]["encoding"] and "x2" in zones[0]["encoding"]  # tam-genişlik
    # eşik çizgileri: y encoding'li, clip'li mark_rule (anomali rule x encoding kullanır)
    thresh = [ly for ly in spec["layer"]
              if ly["mark"]["type"] == "rule" and "y" in ly.get("encoding", {})]
    assert thresh
    # Hibrit: y-domain VERİ-temelli (trip'i zorla kapsamaz); sonlu bir aralık taşır.
    line = [ly for ly in spec["layer"] if ly["mark"]["type"] == "line"][0]
    domain = line["encoding"]["y"]["scale"]["domain"]
    assert len(domain) == 2 and domain[0] < domain[1]


def test_chart_band_with_alert_keeps_overlay() -> None:
    """band + uyarı birlikte: bölge rect (y2'li) VE anomali overlay rect (x2'li, y2'siz) ayrı bulunur."""
    from dashboard.charts import build_sensor_chart
    from dashboard.thresholds import LevelBand

    frame = readings_to_chart_frame(_readings())
    spec = build_sensor_chart(frame, [_alert()], "motor_current", "A",
                              band=LevelBand(9.0, 11.0)).to_dict()
    rect_marks = [ly for ly in spec["layer"] if ly["mark"]["type"] == "rect"]
    has_zone = any("y2" in ly.get("encoding", {}) for ly in rect_marks)
    # anomali overlay: x2 var ama y2 yok (bölge rect'inden ayırt et)
    has_overlay = any("x2" in ly.get("encoding", {}) and "y2" not in ly.get("encoding", {})
                      for ly in rect_marks)
    assert has_zone and has_overlay

"""Altair chart builder'ları (Faz 8 Iter 8.2 spec § 5). Saf — streamlit/DB import etmez."""
from __future__ import annotations

import altair as alt
import pandas as pd

from alerts.models import Alert

LINE_COLOR = "#1d4ed8"  # tema B lacivert (spec § 4)
CHART_HEIGHT = 200  # 2×3 ızgarada eşit-yükseklik okunabilirlik (Clean Corporate yeniden tasarım)
_GRID_COLOR = "#eef2f7"

# Severity → bant/çizgi/etiket rengi (tema B paleti, spec § 4)
SEVERITY_COLORS = {"critical": "#b91c1c", "high": "#ea580c", "warning": "#a16207"}

BAND_OPACITY = 0.15


def alerts_to_overlay_frame(alerts: list[Alert]) -> pd.DataFrame:
    """Alert listesini overlay katmanlarının veri frame'ine çevirir (spec § 5).

    Args:
        alerts: Grafiğin sensörüne ait uyarılar (boş olabilir).

    Returns:
        [window_start (datetime), window_end (datetime), severity, label] kolonlu DataFrame;
        label = "⚠ {rule_name} ({score:.2f})".
    """
    return pd.DataFrame(
        {
            "window_start": pd.to_datetime(
                [a.window_start for a in alerts], format="ISO8601", utc=True
            ),
            "window_end": pd.to_datetime(
                [a.window_end for a in alerts], format="ISO8601", utc=True
            ),
            "severity": [a.severity for a in alerts],
            "label": [f"⚠ {a.rule_name} ({a.score:.2f})" for a in alerts],
        }
    )


def _severity_color() -> alt.Color:
    """Overlay katmanları için paylaşılan severity renk encoding'i (legend kapalı)."""
    return alt.Color(
        "severity:N",
        scale=alt.Scale(domain=list(SEVERITY_COLORS), range=list(SEVERITY_COLORS.values())),
        legend=None,
    )


def build_sensor_chart(
    frame: pd.DataFrame, alerts: list[Alert], sensor: str, unit: str
) -> alt.LayerChart | alt.Chart:
    """Bir sensörün telemetri çizgisi + anomali overlay'li Altair chart'ını kurar (spec § 5).

    Katmanlar (alttan üste): severity bandı (mark_rect) → başlangıç çizgisi (mark_rule,
    kesikli) → kural etiketi (mark_text) → telemetri çizgisi (mark_line, tooltip'li).
    Bu sensöre ait uyarı yoksa (veya frame boşsa) yalnız çizgi döner.

    Args:
        frame: readings_to_chart_frame çıktısı (timestamp/value/state; downsample edilmiş).
        alerts: Seçili cihazın uyarıları (TÜM sensörler; içeride sensor'e filtrelenir —
            fused(N) bandı yalnız temsilci Alert.sensor grafiğine çizilir, spec § 7).
        sensor: Sensör adı (y-ekseni başlığı).
        unit: Birim etiketi (DB'den; boşsa başlık yalnız sensör adı).

    Returns:
        İnteraktif (zoom/pan) Altair chart'ı.
    """
    y_title = f"{sensor} ({unit})" if unit else sensor
    line: alt.Chart = (
        alt.Chart(frame)
        .mark_line(color=LINE_COLOR, strokeWidth=1.5)
        .encode(
            x=alt.X("timestamp:T", title=None, axis=alt.Axis(labelFontSize=10)),
            y=alt.Y(
                "value:Q",
                title=y_title,
                scale=alt.Scale(zero=False),
                axis=alt.Axis(
                    grid=True, gridColor=_GRID_COLOR, labelFontSize=11, titleFontSize=11
                ),
            ),
            tooltip=[
                alt.Tooltip("timestamp:T", format="%H:%M:%S", title="zaman"),
                alt.Tooltip("value:Q", title="değer", format=".3f"),
                alt.Tooltip("state:N", title="state"),
            ],
        )
    )
    relevant = [a for a in alerts if a.sensor == sensor]
    if frame.empty or not relevant:
        return line.interactive().properties(height=CHART_HEIGHT)

    # x-domain telemetri verisinden sabitlenir — bant domain'i esnetmesin (spec § 5).
    domain = [frame["timestamp"].min(), frame["timestamp"].max()]
    line = line.encode(
        x=alt.X(
            "timestamp:T",
            title=None,
            scale=alt.Scale(domain=domain),
            axis=alt.Axis(labelFontSize=10),
        )
    )
    overlay = alerts_to_overlay_frame(relevant)
    band = (
        alt.Chart(overlay)
        .mark_rect(opacity=BAND_OPACITY, clip=True)
        .encode(x="window_start:T", x2="window_end:T", color=_severity_color())
    )
    rule = (
        alt.Chart(overlay)
        .mark_rule(strokeDash=[4, 2], clip=True)
        .encode(x="window_start:T", color=_severity_color())
    )
    text = (
        alt.Chart(overlay)
        .mark_text(align="left", baseline="top", dx=4, clip=True)
        .encode(x="window_start:T", y=alt.value(8), text="label:N", color=_severity_color())
    )
    return alt.layer(band, rule, text, line).interactive().properties(height=CHART_HEIGHT)

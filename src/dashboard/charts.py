"""Altair chart builder'ları (Faz 8 Iter 8.2 spec § 5). Saf — streamlit/DB import etmez."""
from __future__ import annotations

from typing import Any, cast

import altair as alt
import pandas as pd

from alerts.models import Alert
from dashboard.thresholds import LevelBand

LINE_COLOR = "#171b21"  # grafit telemetri çizgisi (AI-mavisi kaldırıldı, frontend-design)
CHART_HEIGHT = 200  # 2×3 ızgarada eşit-yükseklik okunabilirlik
_GRID_COLOR = "#e7eaee"
_CHART_BG = "#ffffff"  # beyaz zemin (siyah/neon değil — sayfayla tutarlı)
_AXIS_LABEL_COLOR = "#697078"
_FONT_SANS = "IBM Plex Sans"
_FONT_MONO = "IBM Plex Mono"

# Severity → bant/çizgi/etiket rengi (tema B paleti, spec § 4)
SEVERITY_COLORS = {"critical": "#b91c1c", "high": "#ea580c", "warning": "#a16207"}

BAND_OPACITY = 0.15

# Radar bölge renkleri (açık zemin; düşük opaklık ki çizgi/overlay üstte okunsun)
ZONE_OK = "#16a34a"
ZONE_WARN = "#d97706"
ZONE_CRIT = "#dc2626"
ZONE_OPACITY = 0.10


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


def _band_layers(
    lo: float, hi: float, band: LevelBand, y_scale: alt.Scale, x_domain: list[Any]
) -> list[alt.Chart]:
    """Seviye-bandı için bölge rect'leri + uyarı/kritik kesikli eşik çizgileri (paylaşılan y_scale).

    BÖLGE rect'i tam-genişlik için açık x-span taşır (x_domain = [tmin, tmax]); yalnız y/y2
    veren bir rect Vega-Lite'ta tam genişliğe yayılmaz. Eşik çizgileri (mark_rule, yalnız y)
    doğal olarak tam-genişlik yatay çizgidir.
    """
    x0, x1 = x_domain[0], x_domain[1]
    zones = pd.DataFrame(
        {"x0": [x0, x0, x0], "x1": [x1, x1, x1],
         "y0": [lo, band.warn, band.trip], "y1": [band.warn, band.trip, hi],
         "zone": ["ok", "warn", "crit"]}
    )
    zone_color = alt.Color(
        "zone:N",
        scale=alt.Scale(domain=["ok", "warn", "crit"], range=[ZONE_OK, ZONE_WARN, ZONE_CRIT]),
        legend=None,
    )
    zone_layer = (
        alt.Chart(zones)
        .mark_rect(opacity=ZONE_OPACITY)
        .encode(
            x=alt.X("x0:T", title=None, axis=alt.Axis(labelFontSize=10)),
            x2="x1:T",
            y=alt.Y("y0:Q", scale=y_scale, title=None),
            y2="y1:Q",
            color=zone_color,
        )
    )
    lines = pd.DataFrame({"y": [band.warn, band.trip], "kind": ["Uyarı", "Kritik"]})
    line_color = alt.Color(
        "kind:N",
        scale=alt.Scale(domain=["Uyarı", "Kritik"], range=[ZONE_WARN, ZONE_CRIT]),
        legend=None,
    )
    thresh_layer = (
        alt.Chart(lines)
        .mark_rule(strokeDash=[6, 3], strokeWidth=1.5)
        .encode(y=alt.Y("y:Q", scale=y_scale), color=line_color)
    )
    return [zone_layer, thresh_layer]


def _finalize(chart: alt.LayerChart | alt.Chart) -> alt.LayerChart | alt.Chart:
    """Ortak bitiş: interaktif + sabit yükseklik + beyaz zemin + IBM Plex eksen (enstrüman-sınıfı)."""
    finished = (
        chart.interactive()
        .properties(height=CHART_HEIGHT)
        .configure_view(stroke=None)
        .configure(background=_CHART_BG, font=_FONT_SANS)
        .configure_axis(
            labelFont=_FONT_MONO,
            titleFont=_FONT_SANS,
            labelColor=_AXIS_LABEL_COLOR,
            titleColor=_AXIS_LABEL_COLOR,
            gridColor=_GRID_COLOR,
            domainColor=_GRID_COLOR,
            tickColor=_GRID_COLOR,
        )
    )
    return cast("alt.LayerChart | alt.Chart", finished)


def build_sensor_chart(
    frame: pd.DataFrame,
    alerts: list[Alert],
    sensor: str,
    unit: str,
    band: LevelBand | None = None,
) -> alt.LayerChart | alt.Chart:
    """Bir sensörün telemetri çizgisi + opsiyonel radar bölgeleri + anomali overlay'i (spec § 3/§ 5).

    Args:
        frame: readings_to_chart_frame çıktısı (timestamp/value/state; downsample edilmiş).
        alerts: Seçili cihazın uyarıları (içeride sensor'e filtrelenir — fused(N) bandı yalnız
            temsilci Alert.sensor grafiğine çizilir, spec § 7).
        sensor: Sensör adı (y-ekseni başlığı).
        unit: Birim etiketi (DB'den; boşsa başlık yalnız sensör adı).
        band: Seviye-bandı (warn/trip) verilirse yeşil/sarı/kırmızı bölge + eşik çizgileri eklenir
            ve y-ekseni eşikleri kapsayacak şekilde genişler; None → klasik davranış.

    Returns:
        İnteraktif Altair chart'ı (band/uyarı yoksa tek çizgi; varsa katmanlı).
    """
    y_title = f"{sensor} ({unit})" if unit else sensor
    frame_empty = bool(frame.empty)
    x_domain: list[Any] | None = (
        None if frame_empty else [frame["timestamp"].min(), frame["timestamp"].max()]
    )

    # y-ölçeği: band varsa eşikleri kapsa (çizginin sınıra uzaklığı görünür). Boş frame'de band yok.
    y_scale = alt.Scale(zero=False)
    band_bounds: tuple[float, float] | None = None
    if band is not None and not frame_empty:
        dmin = float(frame["value"].min())
        dmax = float(frame["value"].max())
        lo = min(dmin, band.warn)
        hi = max(dmax, band.trip)
        pad = (hi - lo) * 0.05 or 1.0
        lo, hi = lo - pad, hi + pad
        y_scale = alt.Scale(domain=[lo, hi], zero=False)
        band_bounds = (lo, hi)

    # Katman eklenecekse (band/overlay) x-domain'i sabitle ki bölge + çizgi + overlay hizalansın.
    relevant = [a for a in alerts if a.sensor == sensor]
    fix_x = x_domain is not None and (band_bounds is not None or bool(relevant))
    if fix_x and x_domain is not None:
        x_enc = alt.X("timestamp:T", title=None, scale=alt.Scale(domain=x_domain),
                      axis=alt.Axis(labelFontSize=10))
    else:
        x_enc = alt.X("timestamp:T", title=None, axis=alt.Axis(labelFontSize=10))
    line: alt.Chart = (
        alt.Chart(frame)
        .mark_line(color=LINE_COLOR, strokeWidth=1.5)
        .encode(
            x=x_enc,
            y=alt.Y(
                "value:Q",
                title=y_title,
                scale=y_scale,
                axis=alt.Axis(grid=True, gridColor=_GRID_COLOR, labelFontSize=11, titleFontSize=11),
            ),
            tooltip=[
                alt.Tooltip("timestamp:T", format="%H:%M:%S", title="zaman"),
                alt.Tooltip("value:Q", title="değer", format=".3f"),
                alt.Tooltip("state:N", title="state"),
            ],
        )
    )

    layers: list[alt.Chart] = []
    if band is not None and band_bounds is not None and x_domain is not None:
        layers.extend(_band_layers(band_bounds[0], band_bounds[1], band, y_scale, x_domain))

    if relevant and not frame_empty:
        overlay = alerts_to_overlay_frame(relevant)
        layers.append(
            alt.Chart(overlay).mark_rect(opacity=BAND_OPACITY, clip=True)
            .encode(x="window_start:T", x2="window_end:T", color=_severity_color())
        )
        layers.append(
            alt.Chart(overlay).mark_rule(strokeDash=[4, 2], clip=True)
            .encode(x="window_start:T", color=_severity_color())
        )
        layers.append(
            alt.Chart(overlay).mark_text(align="left", baseline="top", dx=4, clip=True)
            .encode(x="window_start:T", y=alt.value(8), text="label:N", color=_severity_color())
        )

    if not layers:
        return _finalize(line)
    layers.append(line)
    return _finalize(alt.layer(*layers))

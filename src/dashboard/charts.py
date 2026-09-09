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
ZONE_OPACITY = 0.16  # beyaz zeminde belirginlik (kullanıcı isteği: renk katmanları net görünsün)


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
            # tz KALDIRILIR (telemetri çizgisiyle AYNI eksende hizalanmalı; readings_to_chart_frame
            # naive UTC kullanıyor → overlay de naive UTC olmalı, yoksa 3 saat kayar).
            "window_start": pd.to_datetime(
                [a.window_start for a in alerts], format="ISO8601", utc=True
            ).tz_localize(None),
            "window_end": pd.to_datetime(
                [a.window_end for a in alerts], format="ISO8601", utc=True
            ).tz_localize(None),
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


def _hybrid_y_bounds(dmin: float, dmax: float, band: LevelBand) -> tuple[float, float]:
    """Hibrit y-aralığı: sinyalin gerçek hareketine ölçekle ama gürültüyü şişirme (taban).

    Görünür aralık ≥ %10·kritik (sakin sinyal yumuşak doku gösterir, dipte düz kalmaz);
    sinyal eşiğe tırmanınca aralık yükselir → uyarı/kritik bölgesi doğal olarak girer.
    Negatif olmayan veride alt sınır 0'a kırpılır.
    """
    min_span = 0.10 * band.trip
    span = max(dmax - dmin, min_span)
    center = (dmin + dmax) / 2
    half = span / 2 * 1.25
    ylo, yhi = center - half, center + half
    if dmin >= 0:
        ylo = max(ylo, 0.0)
    return ylo, yhi


def _band_layers(
    ylo: float, yhi: float, band: LevelBand, y_scale: alt.Scale, x_domain: list[Any]
) -> list[alt.Chart]:
    """Seviye-bandı arka plan bölgeleri + uyarı/kritik eşik çizgileri (görünür aralığa KIRPILI).

    Bölgeler mutlak eşik sınırlarında çizilir (yeşil: uyarı altı, sarı: uyarı–kritik, kırmızı:
    kritik üstü) ve y-ölçeği veri-temelli olduğundan `clip=True` ile görünür pencereye kırpılır:
    sinyal sakinken tüm arka plan yeşil; eşiğe tırmanınca sarı/kırmızı girer. Eşik çizgileri de
    yalnız görünür aralıktaysa görünür.
    """
    x0, x1 = x_domain[0], x_domain[1]
    big = (yhi - ylo) + abs(band.trip) + 1.0  # bölgeleri pencere dışına taşır → kırpma temiz
    zones = pd.DataFrame(
        {"x0": [x0, x0, x0], "x1": [x1, x1, x1],
         "y0": [ylo - big, band.warn, band.trip], "y1": [band.warn, band.trip, yhi + big],
         "zone": ["ok", "warn", "crit"]}
    )
    zone_color = alt.Color(
        "zone:N",
        scale=alt.Scale(domain=["ok", "warn", "crit"], range=[ZONE_OK, ZONE_WARN, ZONE_CRIT]),
        legend=None,
    )
    zone_layer = (
        alt.Chart(zones)
        .mark_rect(opacity=ZONE_OPACITY, clip=True)
        .encode(
            x=alt.X("x0:T", title=None, axis=alt.Axis(labelFontSize=10)),
            x2="x1:T",
            y=alt.Y("y0:Q", scale=y_scale, title=None, axis=None),
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
        .mark_rule(strokeDash=[6, 3], strokeWidth=1.5, clip=True)
        .encode(y=alt.Y("y:Q", scale=y_scale), color=line_color)
    )
    return [zone_layer, thresh_layer]


def _finalize(chart: alt.LayerChart | alt.Chart) -> alt.LayerChart | alt.Chart:
    """Ortak bitiş: sabit yükseklik + beyaz zemin + IBM Plex eksen (enstrüman-sınıfı).

    NOT: `.interactive()` (zoom/pan) KASITLI yok — katmanlı grafik + 2s fragment yenilemesinde
    Vega 'Unrecognized data set' hatası veriyor (Streamlit+Altair bilinen sorunu); canlı izlemede
    zoom zaten gereksiz (veri sürekli tazeleniyor).
    """
    finished = (
        chart
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
        Altair chart'ı (band/uyarı yoksa tek çizgi; varsa katmanlı). `.interactive()` YOK —
        app.py bunu sunucuda PNG'ye render eder (canlı izlemede zoom gereksiz).
    """
    frame_empty = bool(frame.empty)
    x_domain: list[Any] | None = (
        None if frame_empty else [frame["timestamp"].min(), frame["timestamp"].max()]
    )

    # Hibrit y-ölçeği: sinyalin gerçek hareketine ölçekle (taban'lı); bölge/eşik clip ile girer.
    y_scale = alt.Scale(zero=False)
    band_bounds: tuple[float, float] | None = None
    if band is not None and not frame_empty:
        ylo, yhi = _hybrid_y_bounds(
            float(frame["value"].min()), float(frame["value"].max()), band
        )
        y_scale = alt.Scale(domain=[ylo, yhi], zero=False)
        band_bounds = (ylo, yhi)

    # x'e AÇIK scale-domain verme: paylaşılan otomatik x-domain (veri min/max) bölge + çizgi +
    # overlay'i zaten hizalar (bölgeler x0/x1'i VERİ değeri olarak alır). Açık tz'li ISO domain
    # gereksiz ve kimi vega sürümlerinde kırılgandır.
    relevant = [a for a in alerts if a.sensor == sensor]
    x_enc = alt.X("timestamp:T", title=None, axis=alt.Axis(labelFontSize=10))
    # y-başlığı YOK (ham kod adı yerine panel başlığı sensörü adlandırır); yalnız değer eksenleri.
    line: alt.Chart = (
        alt.Chart(frame)
        .mark_line(color=LINE_COLOR, strokeWidth=1.5)
        .encode(
            x=x_enc,
            y=alt.Y(
                "value:Q",
                title=None,
                scale=y_scale,
                axis=alt.Axis(grid=True, gridColor=_GRID_COLOR, labelFontSize=11),
            ),
            tooltip=[
                alt.Tooltip("timestamp:T", format="%H:%M:%S", title="zaman"),
                alt.Tooltip("value:Q", title="değer", format=".3f"),
                alt.Tooltip("state:N", title="state"),
            ],
        )
    )

    zone_layers: list[alt.Chart] = []
    if band is not None and band_bounds is not None and x_domain is not None:
        zone_layers = _band_layers(band_bounds[0], band_bounds[1], band, y_scale, x_domain)

    overlay_layers: list[alt.Chart] = []
    if relevant and not frame_empty:
        overlay = alerts_to_overlay_frame(relevant)
        overlay_layers.append(
            alt.Chart(overlay).mark_rect(opacity=BAND_OPACITY, clip=True)
            .encode(x="window_start:T", x2="window_end:T", color=_severity_color())
        )
        overlay_layers.append(
            alt.Chart(overlay).mark_rule(strokeDash=[4, 2], clip=True)
            .encode(x="window_start:T", color=_severity_color())
        )

    if not zone_layers and not overlay_layers:
        return _finalize(line)
    # Katman sırası (alttan üste): bölge arka plan → uyarı penceresi → telemetri çizgisi → başlangıç.
    band_overlay = overlay_layers[:1]
    start_overlay = overlay_layers[1:]
    return _finalize(alt.layer(*zone_layers, *band_overlay, line, *start_overlay))

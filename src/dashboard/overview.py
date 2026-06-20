"""Açılış 'Operasyon Merkezi' saf HTML/SVG builder'ları (streamlit/DB import etmez).

SAF leaf: alerts.models.Alert + dashboard.fleet/labels/transform + stdlib. app.py string'leri
st.markdown(unsafe_allow_html=True) ile basar. Serbest metin html.escape; renkler styles paletiyle
elle senkron (saf leaf, styles'a bağımlı olmamak için yerel sabit).
"""
from __future__ import annotations

import html as _html
from dataclasses import dataclass
from datetime import datetime, timedelta

from alerts.models import Alert
from dashboard.fleet import DeviceHealth
from dashboard.labels import badge_label, device_label, rule_label
from dashboard.transform import relative_time

_OK = "#2f8f5b"
_WARN = "#c07d12"
_CRIT = "#bd3a2c"
_RING_BG = "#e9ecef"
_INK = "#171b21"
_MUTED = "#697078"
_TONE_COLOR = {"ok": _OK, "warning": _WARN, "critical": _CRIT, "muted": "#9aa1a9"}


@dataclass(frozen=True)
class FleetSummary:
    """Filo sağlık özeti (hero + halka)."""

    total: int
    ok: int
    warning: int
    critical: int
    worst: str  # ok | warning | critical


def summarize_fleet(fleet: list[DeviceHealth]) -> FleetSummary:
    """DeviceHealth listesini sağlık sayımlarına indirger (worst: critical>warning>ok)."""
    ok = sum(1 for h in fleet if h.badge == "ok")
    warning = sum(1 for h in fleet if h.badge == "warning")
    critical = sum(1 for h in fleet if h.badge == "critical")
    worst = "critical" if critical else ("warning" if warning else "ok")
    return FleetSummary(len(fleet), ok, warning, critical, worst)


def info_badge_html(tip: str) -> str:
    """Köşe 'i' bilgi rozeti — imleç gelince data-tip CSS tooltip'i (html.escape)."""
    return f'<span class="mg-info" data-tip="{_html.escape(tip)}">i</span>'


def health_ring_svg(summary: FleetSummary) -> str:
    """Sağlık halkası (donut): yeşil yay = ok/total; merkez 'N/M' + 'SAĞLIKLI'."""
    pct = (summary.ok / summary.total * 100) if summary.total else 0.0
    return (
        '<svg class="mg-ring" viewBox="0 0 36 36">'
        f'<circle cx="18" cy="18" r="15.9" fill="none" stroke="{_RING_BG}" stroke-width="3.4"/>'
        f'<circle cx="18" cy="18" r="15.9" fill="none" stroke="{_OK}" stroke-width="3.4" '
        f'stroke-dasharray="{pct:.0f} 100" stroke-linecap="round" transform="rotate(-90 18 18)"/>'
        f'<text x="18" y="17.6" text-anchor="middle" font-size="8.5" font-weight="700" '
        f'font-family="IBM Plex Mono" fill="{_INK}">{summary.ok}/{summary.total}</text>'
        f'<text x="18" y="23.4" text-anchor="middle" font-size="3.1" '
        f'font-family="IBM Plex Mono" fill="{_MUTED}">SAĞLIKLI</text>'
        "</svg>"
    )


def hero_html(
    summary: FleetSummary, device_count: int, sensor_count: int,
    freshness_str: str, span_str: str,
) -> str:
    """Sağlık hero'su: halka + büyük durum + kapsam/tazelik subline + izleme süresi."""
    if summary.worst == "ok":
        status = f'<span style="color:{_OK}">TÜM FİLO SAĞLIKLI</span>'
    else:
        parts = []
        if summary.critical:
            parts.append(f'<span style="color:{_CRIT}">{summary.critical} kritik</span>')
        if summary.warning:
            parts.append(f'<span style="color:{_WARN}">{summary.warning} dikkat</span>')
        parts.append(f"{summary.ok} sağlıklı")
        status = " · ".join(parts)
    return (
        f'<div class="mg-hero mg-hero--{summary.worst}">'
        f"{health_ring_svg(summary)}"
        '<div class="mg-hero-mid">'
        '<div class="mg-hero-ey">Filo Durumu</div>'
        f'<div class="mg-hero-big">{status}</div>'
        f'<div class="mg-hero-sub"><b>{device_count}</b> mast · <b>{sensor_count}</b> sensör '
        f"kesintisiz izleniyor · son veri <b>{_html.escape(freshness_str)}</b></div>"
        "</div>"
        f'<div class="mg-hero-right"><div class="mg-hero-u">{_html.escape(span_str)}</div>'
        '<div class="mg-hero-ul">izleme süresi</div></div>'
        "</div>"
    )


@dataclass(frozen=True)
class CoverageStat:
    """Kapsam/ölçek şeridi tek istatistiği (info tooltip'li)."""

    value: str
    label: str
    tip: str


def coverage_stats(
    device_count: int, sensor_count: int, rate_per_s: int,
    freshness_str: str, detections_24h: int,
) -> list[CoverageStat]:
    """5 kapsam istatistiği (her biri açıklayıcı info tooltip ile)."""
    return [
        CoverageStat(str(device_count), "İzlenen Mast",
                     "Sisteme bağlı, sürekli izlenen mast sayısı."),
        CoverageStat(str(sensor_count), "Aktif Sensör",
                     "Her mastta 6 sensör — toplam izlenen kanal."),
        CoverageStat(f"~{rate_per_s}/sn", "Ölçüm Hızı",
                     "Saniyede işlenen telemetri ölçümü (~mast × 6)."),
        CoverageStat(freshness_str, "Veri Tazeliği",
                     "En son telemetrinin üstünden geçen süre."),
        CoverageStat(str(detections_24h), "Son 24s Tespit",
                     "Son 24 saatte üretilen anomali uyarısı sayısı."),
    ]


def coverage_html(stats: list[CoverageStat]) -> str:
    """Kapsam şeridi HTML'i (hairline ızgara + her stat'ta info tooltip)."""
    cells = "".join(
        f'<div class="mg-stat"><div class="mg-stat-v">{_html.escape(s.value)}'
        f"{info_badge_html(s.tip)}</div>"
        f'<div class="mg-stat-l">{_html.escape(s.label)}</div></div>'
        for s in stats
    )
    return f'<div class="mg-stats">{cells}</div>'


@dataclass(frozen=True)
class TimelineEvent:
    """Son-24s olay akışı satırı."""

    when: str
    tone: str  # critical | warning | ok | ack
    text: str


def timeline_events(alerts: list[Alert], now: datetime, limit: int = 8) -> list[TimelineEvent]:
    """Son 24 saatteki olayları (en yeni üstte) TimelineEvent'lere çevirir.

    resolved → 'çözüldü' (ok); acknowledged → 'teknisyen onayı' (ack); aktif → 'sürüyor'
    (severity tonunda). 24s filtre created_at üzerinden (lexicographic ISO).
    """
    cutoff = (now - timedelta(hours=24)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    recent = sorted(
        (a for a in alerts if a.created_at >= cutoff), key=lambda a: a.created_at, reverse=True
    )
    events: list[TimelineEvent] = []
    for a in recent[:limit]:
        if a.status == "resolved":
            tone, suffix = "ok", "çözüldü"
        elif a.status == "acknowledged":
            tone, suffix = "ack", "teknisyen onayı"
        else:
            tone = a.severity if a.severity in ("critical", "warning") else "warning"
            suffix = "sürüyor"
        text = f"{device_label(a.device_id)} · {rule_label(a.rule_name)} {suffix}"
        events.append(TimelineEvent(relative_time(now, a.created_at), tone, text))
    return events


def timeline_html(events: list[TimelineEvent]) -> str:
    """Olay akışı HTML'i (boşsa dostça 'olay yok' mesajı)."""
    if not events:
        return ('<div class="mg-tl"><div class="mg-empty">'
                "Son 24 saatte olay yok — izleme sürüyor.</div></div>")
    rows = "".join(
        f'<div class="mg-ev"><span class="mg-ev-t">{_html.escape(e.when)}</span>'
        f'<span class="mg-ev-d mg-ev-d--{e.tone}"></span>'
        f'<span class="mg-ev-x">{_html.escape(e.text)}</span></div>'
        for e in events
    )
    return f'<div class="mg-tl">{rows}</div>'


def sparkline_svg(values: list[float], tone: str = "muted", width: int = 140, height: int = 30) -> str:
    """Değer listesini minik inline-SVG polyline sparkline'a çevirir (boş/tek → '')."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(values)
    pts = " ".join(
        f"{i / (n - 1) * width:.1f},{height - (v - lo) / span * (height - 4) - 2:.1f}"
        for i, v in enumerate(values)
    )
    color = _TONE_COLOR.get(tone, _TONE_COLOR["muted"])
    return (
        f'<svg class="mg-spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>'
    )


def fleet_card_html(health: DeviceHealth, spark_values: list[float], value_str: str) -> str:
    """Tıklanır (drill-down) filo kartı: ad + durum rozeti + sorun/incele + sparkline + değer.

    `<a href="?dev=...">` ile tıklanınca o cihaz sayfası açılır (app.py query-param). Ham metin escape.
    """
    badge = health.badge if health.badge in ("ok", "warning", "critical") else "ok"
    tone = badge if badge != "ok" else "muted"
    if health.open_alert_count and health.top_rule:
        prob = f'<div class="mg-cprob bad">{_html.escape(rule_label(health.top_rule))}</div>'
        right = f'<span class="mg-cval">{_html.escape(value_str)}</span>' if value_str else ""
    else:
        prob = '<div class="mg-cprob">Sorun yok</div>'
        right = '<span class="mg-go">incele →</span>'
    return (
        f'<a href="?dev={_html.escape(health.device_id)}" target="_self" '
        f'class="mg-card mg-card--{badge}"><div class="mg-strip"></div><div class="mg-body">'
        f'<div class="mg-cardhead">'
        f'<span class="mg-dev">{_html.escape(device_label(health.device_id))}</span>'
        f'<span class="mg-badge mg-badge--{badge}">{_html.escape(badge_label(badge))}</span></div>'
        f"{prob}"
        f'<div class="mg-cfoot">{sparkline_svg(spark_values, tone)}{right}</div>'
        "</div></a>"
    )


def fleet_grid_html(cards: list[str]) -> str:
    """Filo kartlarını ızgara sarmalayıcısına koyar."""
    return f'<div class="mg-fleet">{"".join(cards)}</div>'

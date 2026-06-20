"""Clean Corporate kurumsal görünüm: CSS + saf HTML-builder'lar (yeniden tasarım 2026-06-19).

SAF — streamlit/DB import ETMEZ (dashboard.fleet/dashboard.transform/alerts.models saf leaf +
stdlib html). app.py bu string'leri st.markdown(unsafe_allow_html=True) ile basar. unsafe_allow_html
ile basılan serbest-metin html.escape ile kaçışlanır (yalnız iç/sentetik veri ama disiplin).
CSS Streamlit 1.36.0 DOM'una göre yazıldı (requirements pinli); canlı smoke ile doğrulanır.
"""
from __future__ import annotations

import html as _html
from datetime import datetime

from alerts.models import Alert
from dashboard.fleet import DeviceHealth, FleetKpis
from dashboard.labels import badge_label, device_label, rule_label, state_label
from dashboard.transform import relative_time

_SEVERITY_RANK_DISPLAY = {"critical": 3, "high": 2, "warning": 1, "info": 0}

# Enstrüman-sınıfı palet (frontend-design: tek-accent, renk=anlam, AI-mavisi/Inter yok).
_BG = "#eef0f2"        # cool paper (krem değil)
_SURFACE = "#ffffff"
_GRAPHITE = "#1b2027"  # kontrol-odası grafit (başlık şeridi + yapısal vurgu)
_PRIMARY = _GRAPHITE   # marka aksanı = grafit (AI-mavisi #1d4ed8 kaldırıldı)
_TEXT = "#171b21"
_MUTED = "#697078"
_BORDER = "#dadee3"    # hairline
_OK = "#2f8f5b"
_WARN = "#c07d12"
_CRIT = "#bd3a2c"
_OKBG = "#e8f3ec"
_WARNBG = "#f7efe0"
_CRITBG = "#f7e6e3"
_ICE = "#eaf2fb"        # buz mavisi — yalnız hover/etkileşim geri bildirimi (marka değil)
_ICE_BORDER = "#bcd4ef"
_FONT = '"IBM Plex Sans", system-ui, -apple-system, sans-serif'
_MONO = '"IBM Plex Mono", ui-monospace, "SF Mono", monospace'

APP_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

/* Streamlit chrome gizle (temiz demo yüzeyi) */
#MainMenu {{visibility: hidden;}}
header[data-testid="stHeader"] {{display: none;}}
div[data-testid="stToolbar"] {{display: none;}}
footer {{visibility: hidden;}}
/* Enstrüman-sınıfı açık zemin (tarayıcı tema-seçici ezmesine karşı) */
.stApp {{background: {_BG} !important;}}
.block-container {{padding-top: 1.1rem; max-width: 1340px;}}
/* Sidebar — daraltılmış (küçük yer kaplasın), açık tema */
section[data-testid="stSidebar"] {{background:{_SURFACE} !important;
  border-right:1px solid {_BORDER}; width:240px !important; min-width:240px !important;}}
section[data-testid="stSidebar"] > div {{width:240px !important; min-width:240px !important;}}
/* Sidebar gezinme kutusunu ana içerikteki siyah header ile aynı hizaya getir (block-container 1.1rem) */
section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
section[data-testid="stSidebar"] .block-container {{padding-top:1.1rem !important;}}
html, body, .stApp, [class*="css"] {{color: {_TEXT}; font-family: {_FONT};}}
.mono, .mg-kpi-val, .mg-pval, .mg-when, .mg-summary b, .mg-pill {{
  font-family: {_MONO}; font-variant-numeric: tabular-nums;}}

/* Light selectbox kapalı kontrol (Streamlit BaseWeb karanlık varsayılanını ez) */
[data-baseweb="select"] > div {{background:{_SURFACE} !important; border-color:{_BORDER} !important;
  color:{_TEXT} !important; border-radius:5px !important;}}
[data-baseweb="select"] span, [data-baseweb="select"] svg {{color:{_TEXT} !important; fill:{_TEXT} !important;}}
/* Açılan menü (popover) — beyaz zemin, siyah yazı, buz-mavisi hover */
[data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"], ul[role="listbox"] {{
  background:{_SURFACE} !important; border:1px solid {_BORDER} !important;}}
[data-baseweb="popover"] li, [role="option"] {{background:{_SURFACE} !important;
  color:{_TEXT} !important; font-family:{_FONT} !important;}}
[data-baseweb="popover"] li:hover, [role="option"]:hover,
[role="option"][aria-selected="true"] {{background:{_ICE} !important; color:{_TEXT} !important;}}
.stButton > button {{background:{_SURFACE}; color:{_TEXT}; border:1px solid {_BORDER};
  border-radius:5px; font-weight:600; font-family:{_FONT};}}
.stButton > button:hover {{border-color:{_GRAPHITE}; color:{_GRAPHITE};}}
.stButton > button:active {{transform: translateY(1px);}}

/* Başlık şeridi — kontrol-odası grafit */
.mg-header {{display:flex; align-items:center; justify-content:space-between;
  padding:13px 22px; background:{_GRAPHITE}; border-radius:6px; margin-bottom:16px;}}
.mg-header .mg-brand {{font-family:{_MONO}; font-size:16px; font-weight:600; color:#eef0f2;
  letter-spacing:.16em; text-transform:uppercase;}}
.mg-header .mg-brand small {{font-family:{_FONT}; color:#8b929b; font-weight:400; font-size:11px;
  letter-spacing:.10em; text-transform:uppercase; margin-left:12px;}}
.mg-header .mg-live {{font-family:{_MONO}; color:#aeb4bc; font-weight:500; font-size:12px;
  letter-spacing:.06em; display:flex; align-items:center; gap:8px;}}
.mg-header .mg-livedot {{width:7px; height:7px; border-radius:50%; background:{_OK};
  box-shadow:0 0 0 3px rgba(47,143,91,.20);}}

/* KPI — hairline enstrüman okumaları (yuvarlak/AI-mavisi kart yok) */
.mg-kpis {{display:grid; grid-template-columns:repeat(4,1fr); background:{_SURFACE};
  border:1px solid {_BORDER}; border-radius:6px; margin-bottom:18px; overflow:hidden;}}
.mg-kpi {{padding:15px 18px; border-left:1px solid {_BORDER};}}
.mg-kpi:first-child {{border-left:0;}}
.mg-kpi .mg-kpi-val {{font-size:30px; font-weight:600; line-height:1; color:{_TEXT};}}
.mg-kpi--critical .mg-kpi-val {{color:{_CRIT};}}
.mg-kpi--warning .mg-kpi-val {{color:{_WARN};}}
.mg-kpi .mg-kpi-lbl {{font-size:11px; color:{_MUTED}; text-transform:uppercase;
  letter-spacing:.12em; margin-top:7px;}}

/* Bir-bakışta filo özeti */
.mg-summary {{display:flex; align-items:center; gap:10px; background:{_SURFACE};
  border:1px solid {_BORDER}; border-left:4px solid {_OK}; border-radius:6px;
  padding:12px 18px; margin-bottom:16px; font-size:16px; color:{_TEXT};}}
.mg-summary--warning {{border-left-color:{_WARN};}}
.mg-summary--critical {{border-left-color:{_CRIT};}}
.mg-summary .mg-summary-dot {{width:11px; height:11px; border-radius:3px; background:{_OK};}}
.mg-summary--warning .mg-summary-dot {{background:{_WARN};}}
.mg-summary--critical .mg-summary-dot {{background:{_CRIT};}}

/* Filo kartları — hairline + ince durum şeridi (düşük radius, gölge yok) */
.mg-fleet {{display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:20px;}}
.mg-card {{background:{_SURFACE}; border:1px solid {_BORDER}; border-radius:6px; overflow:hidden;
  transition:background .12s, border-color .12s;}}
.mg-card:hover {{background:{_ICE}; border-color:{_ICE_BORDER};}}
.mg-card .mg-strip {{height:3px; background:{_OK};}}
.mg-card--warning .mg-strip {{background:{_WARN};}}
.mg-card--critical .mg-strip {{background:{_CRIT};}}
.mg-card .mg-body {{padding:15px 17px;}}
.mg-cardhead {{display:flex; align-items:center; justify-content:space-between;}}
.mg-card .mg-dev {{font-weight:600; font-size:18px; color:{_TEXT};}}
.mg-card .mg-badge {{font-family:{_MONO}; font-size:11px; font-weight:600; padding:3px 10px;
  border-radius:3px; letter-spacing:.07em;}}
.mg-badge--ok {{background:{_OKBG}; color:{_OK};}}
.mg-badge--warning {{background:{_WARNBG}; color:{_WARN};}}
.mg-badge--critical {{background:{_CRITBG}; color:{_CRIT};}}
.mg-card .mg-state {{font-size:13px; color:{_MUTED}; margin:5px 0 11px;}}
.mg-card .mg-problem {{font-size:15px; font-weight:600; color:{_CRIT};}}
.mg-card--warning .mg-problem {{color:{_WARN};}}
.mg-card .mg-okline {{font-size:14px; color:{_MUTED}; font-weight:500;}}

/* Uyarı satır-kartları (düz Türkçe başlık + soluk teknik detay) */
.mg-alert {{display:flex; align-items:center; gap:12px; background:{_SURFACE};
  border:1px solid {_BORDER}; border-left:3px solid {_MUTED}; border-radius:5px;
  padding:11px 14px; margin-bottom:7px; font-size:15px; color:{_TEXT};
  transition:background .12s;}}
.mg-alert:hover {{background:{_ICE};}}
.mg-alert--critical {{border-left-color:{_CRIT};}}
.mg-alert--high {{border-left-color:{_WARN};}}
.mg-alert--warning {{border-left-color:{_WARN};}}
.mg-pill {{font-size:11px; font-weight:600; padding:3px 9px; border-radius:3px; white-space:nowrap;
  letter-spacing:.06em;}}
.mg-pill--critical {{background:{_CRITBG}; color:{_CRIT};}}
.mg-pill--high {{background:{_WARNBG}; color:{_WARN};}}
.mg-pill--warning {{background:{_WARNBG}; color:{_WARN};}}
.mg-alert .mg-when {{color:{_MUTED}; min-width:76px; font-size:12px;}}
.mg-alert .mg-desc {{color:{_TEXT}; flex:1;}}
.mg-alert .mg-detail {{display:block; color:{_MUTED}; font-size:12px; margin-top:2px; font-family:{_MONO};}}
.mg-empty {{color:{_MUTED}; font-size:14px; padding:8px 2px;}}

/* Grafik başlığı (arızalı sensör vurgusu) */
.mg-chart-title {{font-weight:600; font-size:15px; color:{_TEXT}; margin:6px 0 2px;}}
.mg-chart-title--alert {{color:{_CRIT};}}

/* Cihaz Detayı sensör paneli */
.mg-panel {{display:flex; align-items:flex-start; justify-content:space-between; gap:8px;
  margin:4px 0 2px;}}
.mg-panel .mg-pname {{font-weight:600; font-size:14.5px; color:{_TEXT}; display:flex;
  align-items:center; gap:8px;}}
.mg-panel .mg-pval {{font-size:13px; color:{_MUTED};}}
.mg-panel .mg-pval b {{color:{_TEXT}; font-weight:600;}}
.mg-lamp {{width:10px; height:10px; border-radius:3px; background:{_OK}; flex:0 0 auto;}}
.mg-lamp--warning {{background:{_WARN};}}
.mg-lamp--critical {{background:{_CRIT};}}
.mg-pmeta {{display:block; font-size:11.5px; color:{_MUTED}; margin-top:1px; font-family:{_MONO};}}

/* Operasyon Merkezi — hero */
.mg-hero {{display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:24px;
  background:{_SURFACE}; border:1px solid {_BORDER}; border-left:4px solid {_OK};
  border-radius:8px; padding:18px 24px; margin:6px 0 14px;}}
.mg-hero--warning {{border-left-color:{_WARN};}}
.mg-hero--critical {{border-left-color:{_CRIT};}}
.mg-ring {{width:92px; height:92px; flex:0 0 auto;}}
.mg-hero-ey {{font-family:{_MONO}; font-size:11px; letter-spacing:.14em; text-transform:uppercase;
  color:{_MUTED}; margin-bottom:4px;}}
.mg-hero-big {{font-size:27px; font-weight:700; color:{_TEXT}; letter-spacing:-.01em;}}
.mg-hero-sub {{color:{_MUTED}; font-size:14px; margin-top:8px;}}
.mg-hero-sub b {{color:{_TEXT}; font-family:{_MONO};}}
.mg-hero-right {{text-align:right;}}
.mg-hero-u {{font-family:{_MONO}; font-size:21px; font-weight:600; color:{_TEXT};}}
.mg-hero-ul {{font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:{_MUTED}; margin-top:3px;}}

/* Kapsam şeridi + info tooltip */
.mg-stats {{display:grid; grid-template-columns:repeat(5,1fr); background:{_SURFACE};
  border:1px solid {_BORDER}; border-radius:6px; margin-bottom:6px;}}
.mg-stat {{padding:13px 18px; border-left:1px solid {_BORDER};}}
.mg-stat:first-child {{border-left:0;}}
.mg-stat-v {{font-family:{_MONO}; font-size:21px; font-weight:600; display:flex;
  align-items:center; gap:6px;}}
.mg-stat-l {{font-size:10.5px; letter-spacing:.1em; text-transform:uppercase; color:{_MUTED};
  margin-top:5px;}}
.mg-info {{display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px;
  border:1px solid {_BORDER}; border-radius:50%; font-family:{_MONO}; font-size:10px; font-weight:400;
  color:{_MUTED}; cursor:help; position:relative; vertical-align:middle; text-transform:none;}}
.mg-info::after {{content:attr(data-tip); position:absolute; bottom:160%; left:50%;
  transform:translateX(-50%); background:{_SURFACE}; color:{_TEXT}; border:1px solid {_BORDER};
  font-family:{_FONT}; font-size:12px; line-height:1.4; font-weight:400;
  letter-spacing:0; text-transform:none; padding:8px 11px; border-radius:6px; width:max-content;
  max-width:230px; white-space:normal; opacity:0; pointer-events:none; transition:opacity .12s;
  z-index:1000; box-shadow:0 8px 22px rgba(15,23,42,.16);}}
.mg-info:hover::after {{opacity:1;}}

/* Filo kartı — tıklanır link + sparkline ayağı */
a.mg-card {{text-decoration:none; color:inherit; display:block;}}
.mg-card .mg-cprob {{font-size:13px; color:{_MUTED}; margin:7px 0 0;}}
.mg-card .mg-cprob.bad {{color:{_TEXT}; font-weight:500;}}
.mg-card .mg-cfoot {{display:flex; align-items:flex-end; justify-content:space-between; gap:10px;
  margin-top:9px;}}
.mg-card .mg-spark {{flex:1; min-width:0; height:30px;}}
.mg-card .mg-go {{font-family:{_MONO}; font-size:11px; color:{_MUTED};}}
.mg-card .mg-cval {{font-family:{_MONO}; font-size:13px; color:{_MUTED};}}
.mg-card .mg-cval b {{color:{_TEXT};}}

/* Son-24s olay akışı (timeline) */
.mg-tl {{background:{_SURFACE}; border:1px solid {_BORDER}; border-radius:6px; padding:4px 18px;
  margin-bottom:6px;}}
.mg-ev {{display:grid; grid-template-columns:78px 12px 1fr; align-items:center; gap:12px;
  padding:11px 0; border-top:1px solid {_BORDER};}}
.mg-ev:first-child {{border-top:0;}}
.mg-ev-t {{font-family:{_MONO}; font-size:12px; color:{_MUTED};}}
.mg-ev-d {{width:9px; height:9px; border-radius:50%; background:{_OK};}}
.mg-ev-d--warning {{background:{_WARN};}}
.mg-ev-d--critical {{background:{_CRIT};}}
.mg-ev-d--ack {{background:{_MUTED};}}
.mg-ev-x {{font-size:14px; color:{_TEXT};}}

/* Cihaz Detayı — sensör satırı (bordürlü container: durum + geniş grafik) */
[data-testid="stVerticalBlockBorderWrapper"] {{background:{_SURFACE};
  border:1px solid {_BORDER} !important; border-radius:6px; margin-bottom:10px;}}

/* Cihaz Detayı — katman chip'leri + kritiğe-uzaklık gauge */
.mg-layers {{display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin:8px 0 2px;}}
.mg-layers .mg-lbl {{font-family:{_MONO}; font-size:10px; letter-spacing:.07em;
  text-transform:uppercase; color:{_MUTED}; margin-right:2px;}}
.mg-chip {{font-size:11px; font-weight:500; padding:2px 8px; border:1px solid {_BORDER};
  border-radius:999px; color:{_MUTED};}}
.mg-chip--on {{background:{_CRITBG}; border-color:{_CRITBG}; color:{_CRIT}; font-weight:600;}}
.mg-chip-score {{font-family:{_MONO}; font-size:12px; font-weight:600; color:{_CRIT};
  margin-left:auto;}}
.mg-gauge-row {{display:flex; align-items:center; gap:9px; margin:7px 0 2px;}}
.mg-glbl {{font-family:{_MONO}; font-size:10px; letter-spacing:.06em; text-transform:uppercase;
  color:{_MUTED}; min-width:108px;}}
.mg-gauge {{flex:1; height:7px; background:{_BORDER}; border-radius:4px; overflow:hidden;}}
.mg-gfill {{display:block; height:100%; background:{_OK};}}
.mg-gfill--warning {{background:{_WARN};}}
.mg-gfill--critical {{background:{_CRIT};}}
.mg-gfill--ok {{background:{_OK};}}
.mg-gpct {{font-family:{_MONO}; font-size:12px; font-weight:600; min-width:54px; text-align:right;
  color:{_MUTED};}}
.mg-gpct--warning {{color:{_WARN};}}
.mg-gpct--critical {{color:{_CRIT};}}

/* Bölüm başlığı — eyebrow (mono, letterspaced, sessiz) */
.mg-section {{font-family:{_MONO}; font-weight:500; font-size:12px; color:{_MUTED};
  letter-spacing:.14em; text-transform:uppercase; margin:22px 0 9px;}}
</style>
"""


def kpi_card_html(label: str, value: str, tone: str) -> str:
    """Tek KPI kartı (tone: neutral|warning|critical → üst-çizgi + değer rengi).

    Args:
        label: KPI etiketi (örn. "Kritik").
        value: Gösterilecek değer (string).
        tone: "neutral" | "warning" | "critical".

    Returns:
        `.mg-kpi` kartı HTML'i (değer/etiket html.escape'li).
    """
    cls = "mg-kpi" if tone == "neutral" else f"mg-kpi mg-kpi--{tone}"
    return (
        f'<div class="{cls}"><div class="mg-kpi-val">{_html.escape(value)}</div>'
        f'<div class="mg-kpi-lbl">{_html.escape(label)}</div></div>'
    )


def kpis_html(kpis: FleetKpis) -> str:
    """4 KPI kartı ızgarası; tone sayımlardan türetilir (Kritik>0→critical, Açık>0→warning).

    Args:
        kpis: FleetKpis (device/open/critical sayıları + son tespit).

    Returns:
        `.mg-kpis` ızgara HTML'i. Boş "—" son-tespit → "Henüz yok".
    """
    crit_tone = "critical" if kpis.critical_alert_count > 0 else "neutral"
    open_tone = "warning" if kpis.open_alert_count > 0 else "neutral"
    last = (
        kpis.last_detection
        if kpis.last_detection and kpis.last_detection != "—"
        else "Henüz yok"
    )
    cards = (
        kpi_card_html("Cihaz", str(kpis.device_count), "neutral")
        + kpi_card_html("Açık Uyarı", str(kpis.open_alert_count), open_tone)
        + kpi_card_html("Kritik", str(kpis.critical_alert_count), crit_tone)
        + kpi_card_html("Son Tespit", last, "neutral")
    )
    return f'<div class="mg-kpis">{cards}</div>'


def device_card_html(health: DeviceHealth) -> str:
    """Sade filo kartı: cihaz adı + durum rozeti + state + (sorun varsa) düz-Türkçe arıza ifadesi.

    Yönetici-dostu: ham sensör sayıları KART'ta yok (alttaki grafiklerde) — bir bakışta "ne durumda,
    sorun ne" anlaşılır. Ham kod adları labels.py ile Türkçeye çevrilir.

    Args:
        health: DeviceHealth (badge ∈ {ok,warning,critical}; state; open_alert_count; top_rule).

    Returns:
        `.mg-card` HTML'i (tüm metin html.escape'li).
    """
    badge = health.badge if health.badge in ("ok", "warning", "critical") else "ok"
    problem = ""
    if health.open_alert_count and health.top_rule:
        problem = f'<div class="mg-problem">⚠ {_html.escape(rule_label(health.top_rule))}</div>'
    else:
        problem = '<div class="mg-okline">✓ Sorun yok</div>'
    return (
        f'<div class="mg-card mg-card--{badge}"><div class="mg-strip"></div><div class="mg-body">'
        f'<div class="mg-cardhead">'
        f'<span class="mg-dev">{_html.escape(device_label(health.device_id))}</span>'
        f'<span class="mg-badge mg-badge--{badge}">{_html.escape(badge_label(badge))}</span>'
        "</div>"
        f'<div class="mg-state">{_html.escape(state_label(health.state))}</div>'
        f"{problem}"
        "</div></div>"
    )


def fleet_html(fleet: list[DeviceHealth]) -> str:
    """Filo kartları ızgarası (`.mg-fleet`)."""
    return f'<div class="mg-fleet">{"".join(device_card_html(h) for h in fleet)}</div>'


def fleet_summary_html(fleet: list[DeviceHealth]) -> str:
    """Bir-bakışta filo özeti cümlesi: "N masttan X'i sağlıklı, Y'si dikkat, Z'si kritik".

    Tonu en kötü duruma göre (kritik>dikkat>sağlıklı); bilmeyen biri için anında anlaşılır.
    """
    total = len(fleet)
    ok = sum(1 for h in fleet if h.badge == "ok")
    warn = sum(1 for h in fleet if h.badge == "warning")
    crit = sum(1 for h in fleet if h.badge == "critical")
    tone = "critical" if crit else ("warning" if warn else "ok")
    parts = [f"{ok}'i sağlıklı"]
    if warn:
        parts.append(f"{warn}'i dikkat gerektiriyor")
    if crit:
        parts.append(f"{crit}'i KRİTİK")
    detail = ", ".join(parts)  # tamamen iç-üretim (sayı + sabit metin) → escape gereksiz
    return (
        f'<div class="mg-summary mg-summary--{tone}">'
        f'<span class="mg-summary-dot"></span>'
        f"<span><b>{total} masttan</b> {detail}</span>"
        "</div>"
    )


def alert_card_html(alert: Alert, now: datetime) -> str:
    """Tek uyarı satır-kartı: severity pill + göreli zaman + cihaz + sensör·kural + açıklama (escape).

    Args:
        alert: Gösterilecek uyarı.
        now: Göreli zaman ("1 dk önce") referansı.

    Returns:
        `.mg-alert` satır-kartı HTML'i (serbest-metin html.escape'li).
    """
    sev = alert.severity if alert.severity in ("critical", "high", "warning") else "warning"
    when = relative_time(now, alert.created_at)
    # Başlık düz Türkçe (kim · ne); ham teknik açıklama soluk ikincil satır (IT lead için).
    return (
        f'<div class="mg-alert mg-alert--{sev}">'
        f'<span class="mg-pill mg-pill--{sev}">{_html.escape(badge_label(sev))}</span>'
        f'<span class="mg-when">{_html.escape(when)}</span>'
        '<span class="mg-desc">'
        f'<b>{_html.escape(device_label(alert.device_id))}</b> · '
        f"{_html.escape(rule_label(alert.rule_name))}"
        f'<span class="mg-detail">{_html.escape(alert.description)}</span>'
        "</span>"
        "</div>"
    )


def alerts_section_html(title: str, alerts: list[Alert], now: datetime, empty_msg: str) -> str:
    """Bir uyarı ekseni: başlık + satır-kartları (kritik üstte) veya boş-durum mesajı.

    Args:
        title: Bölüm başlığı (örn. "Arıza Uyarıları").
        alerts: Bu eksenin uyarıları.
        now: Göreli zaman referansı.
        empty_msg: Liste boşsa gösterilecek mesaj.

    Returns:
        Başlık + satır-kartları (veya boş-durum) HTML'i.
    """
    head = f'<div class="mg-section">{_html.escape(title)}</div>'
    if not alerts:
        return head + f'<div class="mg-empty">{_html.escape(empty_msg)}</div>'
    ordered = sorted(
        alerts, key=lambda a: _SEVERITY_RANK_DISPLAY.get(a.severity, 0), reverse=True
    )
    return head + "".join(alert_card_html(a, now) for a in ordered)


def panel_header_html(
    sensor_label: str, status_label: str, badge: str, value_str: str, meta_str: str
) -> str:
    """Cihaz Detayı sensör paneli üst bloğu: ad + renkli durum pill'i + değer + meta.

    Args:
        sensor_label: Türkçe sensör adı.
        status_label: Durum metni (NORMAL/DİKKAT/KRİTİK).
        badge: ok|warning|critical → pill renk sınıfı.
        value_str: Güncel değer (örn. "76 °C").
        meta_str: Eşik/açıklama satırı (serbest metin → escape).

    Returns:
        `.mg-panel` HTML'i (tüm metin html.escape'li).
    """
    b = badge if badge in ("ok", "warning", "critical") else "ok"
    return (
        '<div class="mg-panel">'
        f'<span class="mg-pname"><span class="mg-lamp mg-lamp--{b}"></span>'
        f'{_html.escape(sensor_label)} '
        f'<span class="mg-badge mg-badge--{b}">{_html.escape(status_label)}</span></span>'
        f'<span class="mg-pval">{_html.escape(value_str)}</span>'
        "</div>"
        f'<span class="mg-pmeta">{_html.escape(meta_str)}</span>'
    )


def layer_chips_html(watching: list[str], caught: str | None, score: float | None) -> str:
    """Sensörü izleyen/yakalayan tespit katmanı chip'leri (+uyarı varsa gerçek skor).

    caught verilirse 'Yakalayan: <caught>' vurgulu + skor; yoksa 'İzleyen: <watching...>'.
    watching boş ve caught yoksa boş string.
    """
    if not watching and caught is None:
        return ""
    if caught is not None:
        ordered = list(watching)
        if caught not in ordered:
            ordered = [caught, *ordered]
        chips = "".join(
            f'<span class="mg-chip mg-chip--on">{_html.escape(c)}</span>'
            if c == caught
            else f'<span class="mg-chip">{_html.escape(c)}</span>'
            for c in ordered
        )
        score_html = (
            f'<span class="mg-chip-score">skor {score:.2f}</span>' if score is not None else ""
        )
        return (
            '<div class="mg-layers"><span class="mg-lbl">Yakalayan</span>'
            f"{chips}{score_html}</div>"
        )
    chips = "".join(f'<span class="mg-chip">{_html.escape(c)}</span>' for c in watching)
    return f'<div class="mg-layers"><span class="mg-lbl">İzleyen</span>{chips}</div>'


def distance_gauge_html(pct: int, severity: str) -> str:
    """'Kritiğe uzaklık' ince gauge'ı: dolum=pct%, renk severity'den; pct==0 → 'Güvenli'.

    Args:
        pct: 0..100 (band_position_score*100, yuvarlanmış).
        severity: ok|warning|critical → dolum/etiket rengi sınıfı.
    """
    sev = severity if severity in ("ok", "warning", "critical") else "ok"
    label = "Güvenli" if pct <= 0 else f"%{pct}"
    fill = max(0, min(100, pct))
    return (
        '<div class="mg-gauge-row"><span class="mg-glbl">Kritiğe uzaklık</span>'
        f'<span class="mg-gauge"><span class="mg-gfill mg-gfill--{sev}" '
        f'style="width:{fill}%"></span></span>'
        f'<span class="mg-gpct mg-gpct--{sev}">{label}</span></div>'
    )


def header_html(now_str: str) -> str:
    """Başlık şeridi (nötr açıklayıcı başlık — marka adı yok + canlı durum + saat).

    Args:
        now_str: Gösterilecek saat (örn. "14:32:05").

    Returns:
        st.markdown(unsafe_allow_html=True) ile basılacak HTML.
    """
    return (
        '<div class="mg-header">'
        '<span class="mg-brand">MAST İZLEME'
        "<small>TELESKOPİK MAST · DURUM İZLEME · GÖZLEM MODU</small></span>"
        f'<span class="mg-live"><span class="mg-livedot"></span>CANLI · {now_str}</span>'
        "</div>"
    )

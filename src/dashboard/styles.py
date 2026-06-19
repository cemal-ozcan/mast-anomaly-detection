"""Clean Corporate kurumsal görünüm: CSS + saf HTML-builder'lar (yeniden tasarım 2026-06-19).

SAF — streamlit/DB import ETMEZ (dashboard.fleet/dashboard.transform/alerts.models saf leaf +
stdlib html). app.py bu string'leri st.markdown(unsafe_allow_html=True) ile basar. unsafe_allow_html
ile basılan serbest-metin html.escape ile kaçışlanır (yalnız iç/sentetik veri ama disiplin).
CSS Streamlit 1.36.0 DOM'una göre yazıldı (requirements pinli); canlı smoke ile doğrulanır.
"""
from __future__ import annotations

# Tema paleti (spec § 1/§ 2)
_BG = "#f4f6fb"
_SURFACE = "#ffffff"
_PRIMARY = "#1d4ed8"
_TEXT = "#1e293b"
_MUTED = "#64748b"
_BORDER = "#e2e8f0"
_OK = "#16a34a"
_WARN = "#d97706"
_CRIT = "#b91c1c"

APP_CSS = f"""
<style>
/* Streamlit chrome gizle (temiz demo yüzeyi) */
#MainMenu {{visibility: hidden;}}
header[data-testid="stHeader"] {{display: none;}}
div[data-testid="stToolbar"] {{display: none;}}
footer {{visibility: hidden;}}
/* Açık kurumsal zemini zorla (tarayıcı tema-seçici ezmesine karşı) */
.stApp {{background: {_BG} !important;}}
.block-container {{padding-top: 1.2rem; max-width: 1500px;}}
section[data-testid="stSidebar"] {{background: {_SURFACE} !important; border-right: 1px solid {_BORDER};}}
html, body, .stApp, [class*="css"] {{color: {_TEXT}; font-family: "Inter","Segoe UI",sans-serif;}}

/* Başlık şeridi */
.mg-header {{display:flex; align-items:center; justify-content:space-between;
  padding:14px 18px; background:{_SURFACE}; border:1px solid {_BORDER}; border-radius:12px;
  border-left:5px solid {_PRIMARY}; margin-bottom:14px;}}
.mg-header .mg-brand {{font-size:20px; font-weight:700; color:{_TEXT};}}
.mg-header .mg-brand small {{color:{_MUTED}; font-weight:500; font-size:13px; margin-left:8px;}}
.mg-header .mg-live {{color:{_OK}; font-weight:600; font-size:13px;}}

/* KPI kartları */
.mg-kpis {{display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:16px;}}
.mg-kpi {{background:{_SURFACE}; border:1px solid {_BORDER}; border-radius:12px; padding:14px 16px;
  border-top:3px solid {_PRIMARY};}}
.mg-kpi--warning {{border-top-color:{_WARN};}}
.mg-kpi--critical {{border-top-color:{_CRIT};}}
.mg-kpi .mg-kpi-val {{font-size:30px; font-weight:700; line-height:1.1; color:{_TEXT};}}
.mg-kpi--critical .mg-kpi-val {{color:{_CRIT};}}
.mg-kpi--warning .mg-kpi-val {{color:{_WARN};}}
.mg-kpi .mg-kpi-lbl {{font-size:12px; color:{_MUTED}; text-transform:uppercase; letter-spacing:.04em;}}

/* Filo kartları */
.mg-fleet {{display:grid; grid-template-columns:repeat(6,1fr); gap:10px; margin-bottom:18px;}}
.mg-card {{background:{_SURFACE}; border:1px solid {_BORDER}; border-radius:12px; overflow:hidden;}}
.mg-card .mg-strip {{height:5px; background:{_OK};}}
.mg-card--warning .mg-strip {{background:{_WARN};}}
.mg-card--critical .mg-strip {{background:{_CRIT};}}
.mg-card .mg-body {{padding:10px 12px;}}
.mg-card .mg-dev {{font-weight:700; font-size:14px; color:{_TEXT};}}
.mg-card .mg-badge {{font-size:11px; font-weight:700; padding:1px 7px; border-radius:999px;}}
.mg-badge--ok {{background:#dcfce7; color:{_OK};}}
.mg-badge--warning {{background:#fef3c7; color:{_WARN};}}
.mg-badge--critical {{background:#fee2e2; color:{_CRIT};}}
.mg-card .mg-state {{font-size:11px; color:{_MUTED}; margin:2px 0 8px;}}
.mg-metrics {{display:grid; grid-template-columns:1fr auto; gap:2px 8px; font-size:11.5px;}}
.mg-metrics .mg-k {{color:{_MUTED};}}
.mg-metrics .mg-v {{text-align:right; font-variant-numeric:tabular-nums; color:{_TEXT};}}
.mg-metrics .mg-v--hot {{color:{_CRIT}; font-weight:700;}}
.mg-card .mg-toprule {{margin-top:8px; font-size:11px; color:{_CRIT};}}

/* Uyarı satır-kartları */
.mg-alert {{display:flex; align-items:center; gap:10px; background:{_SURFACE};
  border:1px solid {_BORDER}; border-left:4px solid {_MUTED}; border-radius:10px;
  padding:8px 12px; margin-bottom:6px; font-size:13px;}}
.mg-alert--critical {{border-left-color:{_CRIT};}}
.mg-alert--high {{border-left-color:{_WARN};}}
.mg-alert--warning {{border-left-color:{_WARN};}}
.mg-pill {{font-size:11px; font-weight:700; padding:1px 8px; border-radius:999px; white-space:nowrap;}}
.mg-pill--critical {{background:#fee2e2; color:{_CRIT};}}
.mg-pill--high {{background:#ffedd5; color:{_WARN};}}
.mg-pill--warning {{background:#fef9c3; color:{_WARN};}}
.mg-alert .mg-when {{color:{_MUTED}; min-width:64px;}}
.mg-alert .mg-dev2 {{font-weight:600; min-width:90px;}}
.mg-alert .mg-desc {{color:{_TEXT}; flex:1;}}
.mg-empty {{color:{_MUTED}; font-size:13px; padding:6px 2px;}}

/* Grafik başlığı (arızalı sensör vurgusu) */
.mg-chart-title {{font-weight:700; font-size:14px; color:{_TEXT}; margin:4px 0 0;}}
.mg-chart-title--alert {{color:{_CRIT};}}
.mg-section {{font-weight:700; font-size:15px; color:{_TEXT}; margin:10px 0 6px;}}
</style>
"""


def header_html(now_str: str) -> str:
    """MastGuard başlık şeridi (sektör-nötr ürün adı + canlı durum + saat).

    Args:
        now_str: Gösterilecek saat (örn. "14:32:05").

    Returns:
        st.markdown(unsafe_allow_html=True) ile basılacak HTML.
    """
    return (
        '<div class="mg-header">'
        '<span class="mg-brand">🛡 MastGuard'
        "<small>Teleskopik Mast Filo İzleme · gözlem modu</small></span>"
        f'<span class="mg-live">● canlı · {now_str}</span>'
        "</div>"
    )

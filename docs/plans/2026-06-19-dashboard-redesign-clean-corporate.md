# Dashboard Yeniden Tasarım "Clean Corporate" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mevcut Streamlit dashboard'u, veri/mantık katmanına dokunmadan, sunulabilir profesyonel bir "Clean Corporate" komuta merkezine dönüştürmek.

**Architecture:** Tüm kurumsal görünüm yeni saf `src/dashboard/styles.py` modülünde toplanır: `APP_CSS` (deterministik açık tema + chrome gizleme) + saf HTML-builder fonksiyonları (string döner → unit-testlenebilir). `app.py` bunları `st.markdown(unsafe_allow_html=True)` ile basar (ince wiring). `charts.py` okunabilirlik için stillenir. `fleet.py`/`transform.py`/repository/tespit DEĞİŞMEZ.

**Tech Stack:** Python 3.11, Streamlit 1.36.0, Altair 5.5, pandas, pytest, mypy (strict), ruff.

## Global Constraints

- **Spec (tek hakem):** `docs/specs/2026-06-19-dashboard-redesign-clean-corporate-design.md`.
- **Streamlit-native:** enjekte CSS + Altair; React/özel-frontend YOK; yeni ağır bağımlılık YOK.
- **Veri/mantık DEĞİŞMEZ:** `Anomaly`/`fuse_anomalies`/`_detect_once`/repository/`fleet.py` türetimi/`transform.split_alerts_by_axis`+`latest_alert_per_device`+`relative_time`/gözlem modu. Dashboard yalnız okur + ack yazar.
- **Estetik:** Clean Corporate — beyaz/`#f8fafc` zemin, lacivert `#1d4ed8` vurgu, slate `#1e293b` metin, sans-serif, ferah boşluk.
- **Severity renkleri** (mevcut `charts.SEVERITY_COLORS`): critical `#b91c1c`, high `#ea580c`, warning `#a16207`.
- **Güvenlik:** `unsafe_allow_html` ile basılan TÜM serbest-metin (`açıklama`, sensör/kural adları) `html.escape()` ile kaçışlanır.
- **Ürün adı:** "MastGuard" (sektör-nötr; gerçek firma adı YOK).
- **`styles.py` SAF:** streamlit/DB import etmez (fleet/transform/alerts.models — hepsi saf leaf — + stdlib `html`).
- **Tip ipuçları + docstring zorunlu** (mypy strict); `loguru`.
- **Test:** `.venv/bin/python -m pytest <path> -q -p no:cacheprovider --no-cov`. Tam suite: `.venv/bin/python -m pytest`. `mypy src/... tests/...` + `ruff check src tests` (ruff homebrew PATH). CI (GitHub Actions) PR'da koşar.
- **Görsel doğrulama:** her task sonrası + closure'da canlı `demo_up.sh` → kullanıcı ekran görüntüsü → iterasyon (görsel ince ayar testle değil gözle doğrulanır).
- **Yürütme:** controller-inline + salt-okunur reviewer (Bash/Write subagent yok).

---

## Dosya Haritası

| Dosya | Sorumluluk | Değişim |
|---|---|---|
| `src/dashboard/styles.py` | kurumsal CSS + saf HTML-builder'lar | **YENİ** |
| `src/dashboard/app.py` | ince wiring (CSS enjekte, builder'ları bas) | rework (presentation) |
| `src/dashboard/charts.py` | okunabilir Altair stili | `build_sensor_chart` stillenir |
| `src/dashboard/transform.py` | (ölü) `alerts_to_frame`/`severity_row_style` kaldırılır | Task 4 |
| `src/dashboard/fleet.py` | DEĞİŞMEZ (DeviceHealth/FleetKpis tüketilir) | — |
| tests | saf builder'lar TDD | yeni `test_dashboard_styles.py` |

---

### Task 1: `styles.py` temel — `APP_CSS` + chrome gizleme + başlık şeridi + wiring

**Files:**
- Create: `src/dashboard/styles.py`
- Modify: `src/dashboard/app.py` (`main()`: page_config + CSS enjekte + header)
- Test: `tests/unit/test_dashboard_styles.py` (yeni)

**Interfaces:**
- Produces:
  - `APP_CSS: str` — açık tema zorlama (`.stApp` arka plan) + Streamlit chrome gizleme + `mg-*` bileşen sınıfları.
  - `header_html(now_str: str) -> str` — MastGuard başlık şeridi (sektör-nötr).

- [ ] **Step 1: Write failing tests** (`tests/unit/test_dashboard_styles.py`)

```python
"""dashboard.styles saf CSS + HTML-builder testleri (Clean Corporate yeniden tasarım)."""
from __future__ import annotations

from dashboard.styles import APP_CSS, header_html


def test_app_css_nonempty_and_hides_chrome() -> None:
    assert isinstance(APP_CSS, str) and len(APP_CSS) > 100
    # Streamlit chrome gizleme + açık zemin zorlama selektörleri.
    assert "#MainMenu" in APP_CSS
    assert 'data-testid="stToolbar"' in APP_CSS or "stToolbar" in APP_CSS
    assert "footer" in APP_CSS
    assert "#ffffff" in APP_CSS or "#f8fafc" in APP_CSS


def test_header_html_contains_brand_and_clock() -> None:
    html = header_html("14:32:05")
    assert "MastGuard" in html
    assert "14:32:05" in html
    assert "mg-header" in html
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_styles.py -q -p no:cacheprovider --no-cov`
Expected: FAIL (modül yok).

- [ ] **Step 3: Implement `src/dashboard/styles.py`**

```python
"""Clean Corporate kurumsal görünüm: CSS + saf HTML-builder'lar (yeniden tasarım 2026-06-19).

SAF — streamlit/DB import ETMEZ (fleet/transform/alerts.models saf leaf + stdlib html).
app.py bu string'leri st.markdown(unsafe_allow_html=True) ile basar. unsafe_allow_html ile
basılan serbest-metin html.escape ile kaçışlanır (yalnız iç/sentetik veri ama disiplin).
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
```

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_styles.py -q -p no:cacheprovider --no-cov`
Expected: PASS.

- [ ] **Step 5: Wire into `app.py` `main()`**

`main()` başındaki şu bloğu:
```python
    st.set_page_config(page_title="Mast Filo İzleme", layout="wide")
    st.title("Mast Filo İzleme")
    st.caption("Teleskopik mast filosu — gerçek zamanlı telemetri ve erken uyarı (gözlem modu)")
```
ŞUNUNLA değiştir:
```python
    st.set_page_config(page_title="MastGuard · Mast İzleme", layout="wide")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(
        header_html(datetime.now(UTC).strftime("%H:%M:%S")), unsafe_allow_html=True
    )
```
Import ekle (app.py transform/fleet importları yanına):
```python
from dashboard.styles import APP_CSS, header_html  # noqa: E402
```

- [ ] **Step 6: Full suite + mypy + ruff + boot smoke + commit**

Run: `.venv/bin/python -m pytest -q -p no:cacheprovider --no-cov` → PASS
Run: `.venv/bin/python -m mypy src/dashboard tests/unit` + `ruff check src/dashboard tests/unit` → temiz
Run boot smoke: `DASHBOARD_DB_PATH=/tmp/empty_mg.db PYTHONPATH=src .venv/bin/python -c "import dashboard.app"` → traceback yok

```bash
git add src/dashboard/styles.py src/dashboard/app.py tests/unit/test_dashboard_styles.py
git commit -m "feat(dashboard): styles.py temel — kurumsal CSS + chrome gizleme + MastGuard başlık"
```

---

### Task 2: KPI bandı (renk-kodlu)

**Files:**
- Modify: `src/dashboard/styles.py` (+`kpi_card_html`, +`kpis_html`)
- Modify: `src/dashboard/app.py` (`_render_overview` KPI bloğu)
- Test: `tests/unit/test_dashboard_styles.py`

**Interfaces:**
- Consumes: `fleet.FleetKpis` (device_count, open_alert_count, critical_alert_count, last_detection).
- Produces:
  - `kpi_card_html(label: str, value: str, tone: str) -> str` (tone ∈ {"neutral","warning","critical"}).
  - `kpis_html(kpis: FleetKpis) -> str` — 4 kartlık `.mg-kpis` ızgarası (Kritik>0→critical tone, Açık>0→warning tone).

- [ ] **Step 1: Write failing tests** (append)

```python
from dashboard.styles import kpi_card_html, kpis_html


def test_kpi_card_tone_classes() -> None:
    assert "mg-kpi--critical" in kpi_card_html("Kritik", "1", "critical")
    assert "mg-kpi--warning" in kpi_card_html("Açık", "4", "warning")
    n = kpi_card_html("Cihaz", "6", "neutral")
    assert "mg-kpi--critical" not in n and "mg-kpi--warning" not in n
    assert ">6<" in n and "Cihaz" in n


def test_kpis_html_tone_from_counts() -> None:
    from dashboard.fleet import FleetKpis

    html = kpis_html(FleetKpis(device_count=6, open_alert_count=4, critical_alert_count=1,
                               last_detection="1 dk önce"))
    assert "mg-kpis" in html
    assert "mg-kpi--critical" in html  # kritik>0
    assert "1 dk önce" in html


def test_kpis_html_empty_last_detection() -> None:
    from dashboard.fleet import FleetKpis

    html = kpis_html(FleetKpis(device_count=6, open_alert_count=0, critical_alert_count=0,
                               last_detection="—"))
    assert "Henüz yok" in html  # boş "—" dostça gösterilir
    assert "mg-kpi--critical" not in html
```
> NOT: ilk satırdaki `from fleet_import_helper ...` yanlış — SİL; testlerde `from dashboard.fleet import FleetKpis` kullan (yukarıdaki gibi). `dashboard.fleet` modülü editable/PYTHONPATH ile erişilir (paket prefix'i `dashboard.`).

- [ ] **Step 2: Run to verify FAIL** → `ImportError: kpi_card_html`.

- [ ] **Step 3: Implement** (append `styles.py`; `from dashboard.fleet import FleetKpis` modül başına — fleet saf leaf)

```python
import html as _html

from dashboard.fleet import FleetKpis


def kpi_card_html(label: str, value: str, tone: str) -> str:
    """Tek KPI kartı (tone: neutral|warning|critical → üst-çizgi + değer rengi)."""
    cls = "mg-kpi" if tone == "neutral" else f"mg-kpi mg-kpi--{tone}"
    return (
        f'<div class="{cls}"><div class="mg-kpi-val">{_html.escape(value)}</div>'
        f'<div class="mg-kpi-lbl">{_html.escape(label)}</div></div>'
    )


def kpis_html(kpis: FleetKpis) -> str:
    """4 KPI kartı ızgarası; tone sayımlardan türetilir (Kritik>0→critical, Açık>0→warning)."""
    crit_tone = "critical" if kpis.critical_alert_count > 0 else "neutral"
    open_tone = "warning" if kpis.open_alert_count > 0 else "neutral"
    last = kpis.last_detection if kpis.last_detection and kpis.last_detection != "—" else "Henüz yok"
    cards = (
        kpi_card_html("Cihaz", str(kpis.device_count), "neutral")
        + kpi_card_html("Açık Uyarı", str(kpis.open_alert_count), open_tone)
        + kpi_card_html("Kritik", str(kpis.critical_alert_count), crit_tone)
        + kpi_card_html("Son Tespit", last, "neutral")
    )
    return f'<div class="mg-kpis">{cards}</div>'
```

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Wire into `_render_overview`** — mevcut `st.columns(4)` + 4×`st.metric` bloğunu (KPI satırı) şununla değiştir:
```python
    st.markdown(kpis_html(kpis), unsafe_allow_html=True)
```
(`kpis = compute_kpis(...)` satırı kalır; `kpi_cols`/`st.metric` satırları silinir.) Import: `from dashboard.styles import APP_CSS, header_html, kpis_html`.

- [ ] **Step 6: Full suite + mypy + ruff + commit**
```bash
git add src/dashboard/styles.py src/dashboard/app.py tests/unit/test_dashboard_styles.py
git commit -m "feat(dashboard): renk-kodlu KPI bandı (kpis_html)"
```

---

### Task 3: Filo kartları (metin yığını → kompakt kart)

**Files:**
- Modify: `src/dashboard/styles.py` (+`device_card_html`, +`fleet_html`)
- Modify: `src/dashboard/app.py` (`_render_fleet_cards` değişimi)
- Test: `tests/unit/test_dashboard_styles.py`

**Interfaces:**
- Consumes: `fleet.DeviceHealth` (device_id, badge ∈ {ok,warning,critical}, state, snapshots[(sensor,value,unit,highlighted)], open_alert_count, top_rule).
- Produces:
  - `device_card_html(health: DeviceHealth) -> str` — severity strip + badge + state + 2-kolon metrik ızgarası + top_rule.
  - `fleet_html(fleet: list[DeviceHealth]) -> str` — `.mg-fleet` ızgarası.

- [ ] **Step 1: Write failing tests** (append)

```python
from dashboard.styles import device_card_html, fleet_html


def _health(badge="ok", highlighted=False, top_rule=None, n=0):
    from dashboard.fleet import DeviceHealth, SensorSnapshot
    return DeviceHealth(
        device_id="device_004", badge=badge, state="holding",
        snapshots=(SensorSnapshot("motor_voltage", 22.79, "V", highlighted),
                   SensorSnapshot("motor_current", 0.53, "A", False)),
        open_alert_count=n, top_rule=top_rule,
    )


def test_device_card_badge_and_strip() -> None:
    h = device_card_html(_health(badge="critical", n=1, top_rule="motor_voltage_erratic"))
    assert "mg-card--critical" in h and "mg-badge--critical" in h
    assert "device_004" in h and "holding" in h
    assert "motor_voltage" in h and "22.79" in h  # metrik değer (kelime bölünmesi yok)
    assert "motor_voltage_erratic" in h  # top rule
    assert "1 açık" in h


def test_device_card_highlighted_value_class() -> None:
    assert "mg-v--hot" in device_card_html(_health(badge="critical", highlighted=True))


def test_device_card_ok_no_toprule() -> None:
    h = device_card_html(_health(badge="ok", n=0, top_rule=None))
    assert "mg-badge--ok" in h and "mg-toprule" not in h


def test_fleet_html_wraps_grid() -> None:
    assert 'class="mg-fleet"' in fleet_html([_health(), _health()])
```

- [ ] **Step 2: FAIL** → ImportError.

- [ ] **Step 3: Implement** (append `styles.py`)

```python
from dashboard.fleet import DeviceHealth

_BADGE_LABEL = {"ok": "OK", "warning": "UYARI", "critical": "KRİTİK"}


def device_card_html(health: DeviceHealth) -> str:
    """Tek filo kartı: severity strip + badge + state + hizalı 2-kolon metrik ızgarası + top rule."""
    badge = health.badge if health.badge in _BADGE_LABEL else "ok"
    rows = ""
    for s in health.snapshots:
        v_cls = "mg-v mg-v--hot" if s.highlighted else "mg-v"
        rows += (
            f'<span class="mg-k">{_html.escape(s.sensor)}</span>'
            f'<span class="{v_cls}">{s.value:.2f} {_html.escape(s.unit)}</span>'
        )
    toprule = ""
    if health.open_alert_count and health.top_rule:
        toprule = (
            f'<div class="mg-toprule">⚠ {health.open_alert_count} açık · '
            f"{_html.escape(health.top_rule)}</div>"
        )
    return (
        f'<div class="mg-card mg-card--{badge}"><div class="mg-strip"></div><div class="mg-body">'
        f'<span class="mg-dev">{_html.escape(health.device_id)}</span> '
        f'<span class="mg-badge mg-badge--{badge}">{_BADGE_LABEL[badge]}</span>'
        f'<div class="mg-state">state: {_html.escape(health.state)}</div>'
        f'<div class="mg-metrics">{rows}</div>{toprule}'
        "</div></div>"
    )


def fleet_html(fleet: list[DeviceHealth]) -> str:
    """Filo kartları ızgarası."""
    return f'<div class="mg-fleet">{"".join(device_card_html(h) for h in fleet)}</div>'
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Wire** — `app.py` `_render_fleet_cards(fleet_health)` gövdesini şununla değiştir (st.columns/st.container bloğu yerine):
```python
def _render_fleet_cards(fleet_health: list[DeviceHealth]) -> None:
    """Filo sağlık kartlarını kurumsal HTML ızgarasıyla çizer (Clean Corporate)."""
    if not fleet_health:
        return
    st.markdown(fleet_html(fleet_health), unsafe_allow_html=True)
```
Import'a `fleet_html` ekle. (`BADGE_*`/`_BADGE_LABELS`/`zip`/`st.container` artık kullanılmıyorsa temizle — ruff unused yakalar.)

- [ ] **Step 6: Full suite + mypy + ruff + canlı bak + commit**
```bash
git add src/dashboard/styles.py src/dashboard/app.py tests/unit/test_dashboard_styles.py
git commit -m "feat(dashboard): filo kartları metin-yığını→kompakt kurumsal kart (device_card_html)"
```

---

### Task 4: Uyarı satır-kartları (iki eksen) + ölü `alerts_to_frame` temizliği

**Files:**
- Modify: `src/dashboard/styles.py` (+`alert_card_html`, +`alerts_section_html`)
- Modify: `src/dashboard/app.py` (`_render_overview` uyarı bloğu + `_render_alert_table` kaldır)
- Modify: `src/dashboard/transform.py` (ölü `alerts_to_frame` + `severity_row_style` + `_ALERT_COLUMNS`/`_SEVERITY_ROW_*` kaldır)
- Test: `tests/unit/test_dashboard_styles.py` (+) ; `tests/unit/test_dashboard_alerts_transform.py` (alerts_to_frame testlerini kaldır)

**Interfaces:**
- Consumes: `alerts.models.Alert`, `transform.relative_time(now, ts)`, `transform.split_alerts_by_axis`.
- Produces:
  - `alert_card_html(alert: Alert, now: datetime) -> str` — göreli zaman + cihaz + severity pill + sensör/kural + kaçışlanmış açıklama.
  - `alerts_section_html(title: str, alerts: list[Alert], now: datetime, empty_msg: str) -> str`.

- [ ] **Step 1: Write failing tests** (append to `test_dashboard_styles.py`)

```python
from datetime import UTC, datetime

from dashboard.styles import alert_card_html, alerts_section_html


def _alert(severity="critical", desc="motor_voltage std 4.77V eşik <x>"):
    from alerts.models import Alert
    return Alert(id=1, device_id="device_004", rule_name="motor_voltage_erratic", sensor="motor_voltage",
                 severity=severity, score=0.94, window_start="2026-06-19T12:55:00.000Z",
                 window_end="2026-06-19T12:57:29.854Z", value=4.77, description=desc,
                 created_at="2026-06-19T12:57:29.854Z", status="active", acknowledged_at=None,
                 resolved_at=None, clean_streak=0, rule_set="motor_voltage_erratic")


def test_alert_card_pill_and_escape() -> None:
    now = datetime(2026, 6, 19, 12, 58, 0, tzinfo=UTC)
    h = alert_card_html(_alert(severity="critical"), now)
    assert "mg-pill--critical" in h and "mg-alert--critical" in h
    assert "device_004" in h and "motor_voltage_erratic" in h
    assert "&lt;x&gt;" in h  # açıklama html.escape'lendi
    assert "<x>" not in h


def test_alerts_section_empty() -> None:
    now = datetime(2026, 6, 19, 12, 58, 0, tzinfo=UTC)
    h = alerts_section_html("Arıza Uyarıları", [], now, "Açık arıza uyarısı yok.")
    assert "Açık arıza uyarısı yok." in h and "mg-empty" in h
    assert "Arıza Uyarıları" in h


def test_alerts_section_lists_alerts() -> None:
    now = datetime(2026, 6, 19, 12, 58, 0, tzinfo=UTC)
    h = alerts_section_html("Arıza Uyarıları", [_alert()], now, "yok")
    assert "device_004" in h and "mg-alert" in h
```

- [ ] **Step 2: FAIL** → ImportError.

- [ ] **Step 3: Implement** (append `styles.py`)

```python
from datetime import datetime

from alerts.models import Alert
from dashboard.transform import relative_time

_PILL = {"critical": "critical", "high": "high", "warning": "warning"}


def alert_card_html(alert: Alert, now: datetime) -> str:
    """Tek uyarı satır-kartı: göreli zaman + cihaz + severity pill + sensör·kural + açıklama (escape)."""
    sev = alert.severity if alert.severity in _PILL else "warning"
    when = relative_time(now, alert.created_at)
    return (
        f'<div class="mg-alert mg-alert--{sev}">'
        f'<span class="mg-pill mg-pill--{sev}">{_html.escape(alert.severity)}</span>'
        f'<span class="mg-when">{_html.escape(when)}</span>'
        f'<span class="mg-dev2">{_html.escape(alert.device_id)}</span>'
        f'<span class="mg-desc">{_html.escape(alert.sensor)} · '
        f"{_html.escape(alert.rule_name)} — {_html.escape(alert.description)}</span>"
        "</div>"
    )


def alerts_section_html(title: str, alerts: list[Alert], now: datetime, empty_msg: str) -> str:
    """Bir uyarı ekseni: başlık + satır-kartları (kritik üstte) veya boş-durum mesajı."""
    head = f'<div class="mg-section">{_html.escape(title)}</div>'
    if not alerts:
        return head + f'<div class="mg-empty">{_html.escape(empty_msg)}</div>'
    rank = {"critical": 3, "high": 2, "warning": 1, "info": 0}
    ordered = sorted(alerts, key=lambda a: rank.get(a.severity, 0), reverse=True)
    return head + "".join(alert_card_html(a, now) for a in ordered)
```
> `relative_time(now, ts) -> str` mevcut (transform.py); `Alert.rule_set`/`clean_streak` (8.7/8.8) Alert imzasında — test constructor'ı tam alanlı.

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Wire `_render_overview`** — `st.subheader("🚨 Uyarılar")` + selectbox + `split_alerts_by_axis` + iki `_render_alert_table` bloğunu şununla değiştir:
```python
    st.markdown('<div class="mg-section">🚨 Uyarılar</div>', unsafe_allow_html=True)
    choice = st.selectbox("Görünüm", _VIEW_OPTIONS, index=0, key="alert_view", label_visibility="collapsed")
    visible = _filter_view(alerts, choice or "Cihaz özeti")
    faults, data_quality = split_alerts_by_axis(visible)
    st.markdown(alerts_section_html("Arıza Uyarıları", faults, now, "Açık arıza uyarısı yok."),
                unsafe_allow_html=True)
    st.markdown(alerts_section_html("Veri Kalitesi / Sensör Sağlığı", data_quality, now,
                                    "Tüm sensörler sağlıklı."), unsafe_allow_html=True)
```
`_render_alert_table` fonksiyonunu SİL (artık kullanılmıyor). Import: `from dashboard.styles import ... alerts_section_html`; `alerts_to_frame`/`severity_row_style` importlarını app.py'den KALDIR.

- [ ] **Step 6: Ölü kod temizliği** — `transform.py`'den `alerts_to_frame` + `severity_row_style` + ilgili `_ALERT_COLUMNS`/`_SEVERITY_*` sabitlerini SİL (artık yalnız HTML kullanıyoruz). `tests/unit/test_dashboard_alerts_transform.py`'den `alerts_to_frame`/`severity_row_style` testlerini SİL (is_data_quality/split testleri KALIR). `grep -rn "alerts_to_frame\|severity_row_style" src tests` → yalnızca kalmaması gereken yerde 0 sonuç.

- [ ] **Step 7: Full suite + mypy + ruff + commit**
```bash
git add src/dashboard/styles.py src/dashboard/app.py src/dashboard/transform.py tests/unit/test_dashboard_styles.py tests/unit/test_dashboard_alerts_transform.py
git commit -m "feat(dashboard): uyarı satır-kartları iki eksen (alert_card_html) + ölü alerts_to_frame temizliği"
```

---

### Task 5: Grafikler — okunabilir 2×3 ızgara + arızalı sensör vurgusu

**Files:**
- Modify: `src/dashboard/charts.py` (`build_sensor_chart` stil iyileştirme)
- Modify: `src/dashboard/app.py` (`_render_charts` 2×3 + vurgulu başlık)
- Test: `tests/unit/test_dashboard_charts.py` (mevcut testler yeşil + 1 stil-sanity)

**Interfaces:**
- Consumes: mevcut `build_sensor_chart(frame, alerts, sensor, unit)`.
- Produces: aynı imza; daha okunur stil (sabit yükseklik, ince çizgi, açık grid, okunur eksen).

- [ ] **Step 1: Stil sanity testi** (append `test_dashboard_charts.py`)

```python
def test_build_sensor_chart_has_fixed_height() -> None:
    import pandas as pd
    from dashboard.charts import build_sensor_chart
    frame = pd.DataFrame({"timestamp": pd.to_datetime(["2026-06-19T12:00:00Z"], utc=True),
                          "value": [1.0], "state": ["holding"]})
    chart = build_sensor_chart(frame, [], "motor_current", "A")
    d = chart.to_dict()
    # properties height set edilmiş olmalı (okunabilir eşit yükseklik)
    assert d.get("height") == 200 or d.get("spec", {}).get("height") == 200
```

- [ ] **Step 2: FAIL** (height set değil).

- [ ] **Step 3: Implement `charts.py`** — `line` zincirine ve dönüşlere stil ekle. `line` tanımından sonra ve her `return`'den önce yüksekliği uygula; eksen/grid okunurluğunu `mark_line(strokeWidth=1.5)` + `.properties(height=200)` + axis config ile artır. Pratik minimal değişiklik: `build_sensor_chart` sonunda chart'a `.properties(height=200)` ekle ve `mark_line(color=LINE_COLOR, strokeWidth=1.5)` yap; `alt.Y(... axis=alt.Axis(grid=True, gridColor="#eef2f7", labelFontSize=11, titleFontSize=11))` ve `alt.X(... axis=alt.Axis(labelFontSize=10))`. (Tam diff implementasyonda; yükseklik 200 testi yeşil olmalı.) Both return yolları (`line.interactive()` ve `alt.layer(...).interactive()`) `.properties(height=200)` taşımalı — ortak helper veya her ikisine uygula.

- [ ] **Step 4: PASS** (height testi + mevcut chart testleri).

- [ ] **Step 5: Wire `_render_charts` 2×3 + vurgu** — `cols = st.columns(2)` → `cols = st.columns(3)`; döngüde `i % 2` → `i % 3`; her grafik başlığını `st.subheader(sensor)` yerine vurgulu HTML başlık yap:
```python
        sensor_has_alert = any(a.sensor == sensor for a in device_alerts)
        with cols[i % 3]:
            title_cls = "mg-chart-title mg-chart-title--alert" if sensor_has_alert else "mg-chart-title"
            st.markdown(f'<div class="{title_cls}">{sensor}</div>', unsafe_allow_html=True)
            st.altair_chart(cast(alt.Chart, build_sensor_chart(frame, device_alerts, sensor, unit)),
                            use_container_width=True, theme="streamlit")
```

- [ ] **Step 6: Full suite + mypy + ruff + canlı bak + commit**
```bash
git add src/dashboard/charts.py src/dashboard/app.py tests/unit/test_dashboard_charts.py
git commit -m "feat(dashboard): okunabilir 2×3 grafik ızgarası + arızalı sensör vurgusu"
```

---

### Task 6: Closure — canlı görsel iterasyon + docs/memory

> **Controller-run (TDD task değil).**

- [ ] **Step 1: Tam suite + mypy + ruff + CI** — hepsi yeşil.
- [ ] **Step 2: Canlı `demo_up.sh` → kullanıcıdan ekran görüntüsü** → görsel değerlendir + ince ayar (renk/spacing/yükseklik/CSS selektör). Hedef (spec § 5): açık kurumsal tema render oluyor (koyu DEĞİL), chrome gizli, kartlar okunur (metin-yığını yok), KPI renk-kodlu, grafikler okunur, iki-eksen uyarı temiz, MastGuard başlık. **Streamlit 1.36 chrome-selektörleri canlıda doğrulanır; gerekirse düzeltilir.** Teardown + config `.bak` geri yükle.
- [ ] **Step 3: Docs** — gerekirse `docs/DEMO.md` ekran görüntüsü/açıklama; CLAUDE.md dashboard runtime contract notu (Clean Corporate + styles.py).
- [ ] **Step 4: Memory** — `project_active_phase.md`: dashboard yeniden tasarım DONE + styles.py runtime contract.
- [ ] **Step 5: Final whole-branch review** (salt-okunur) → fix loop.
- [ ] **Step 6:** Kullanıcı onayıyla PR/merge.

---

## Self-Review (yazar kontrolü)

**1. Spec coverage:** §0 tema+chrome+header → T1. §1 KPI → T2. §2 filo kartları → T3. §3 uyarılar iki eksen → T4. §4 grafikler 2×3+vurgu → T5. §5 test → her task TDD + T6 canlı. §6 değişmez kontratlar → Global Constraints (veri/mantık/fleet/transform-logic dokunulmaz). MastGuard adı → T1. Ölü kod (alerts_to_frame) → T4. ✓

**2. Placeholder scan:** Task 5 Step 3 "tam diff implementasyonda" — stil değerleri açıkça verildi (height=200, strokeWidth=1.5, axis config); height testi somut kapı. Diğer kod blokları tam. Test snippet'indeki yanlış `from fleet_import_helper` satırı NOT ile düzeltildi (`from dashboard.fleet import FleetKpis`). ✓

**3. Type consistency:** `kpi_card_html(label,value,tone)`/`kpis_html(FleetKpis)` (T2) ↔ app wiring tutarlı. `device_card_html(DeviceHealth)`/`fleet_html(list)` (T3) ↔ `_render_fleet_cards`. `alert_card_html(Alert,datetime)`/`alerts_section_html(title,list,now,empty)` (T4) ↔ `_render_overview`. `styles` importları: `fleet.FleetKpis/DeviceHealth`, `alerts.models.Alert`, `transform.relative_time` — hepsi saf leaf, döngü yok (styles→fleet→transform; styles→transform; styles→alerts.models). `html.escape` her serbest-metinde. ✓

# Dashboard — İki Sayfa Gezinme + Radar Grafikler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard'u iki sayfaya böl (Filo Genel Bakış → soldaki menüden seçilen Cihaz Detayı) ve Cihaz Detayı'ndaki grafikleri, gerçek eşiklere göre yeşil/sarı/kırmızı bölgeli + durum-etiketli "radar" panellerine çevir.

**Architecture:** Tek `app.py` + `st.session_state` sürücülü sol-menü gezinme (ağır multipage YOK). Yeni saf `thresholds.py` config'ten seviye-eşiklerini okur; `charts.build_sensor_chart` geriye-uyumlu `band` parametresiyle bölge+eşik katmanları ekler; `fleet.sensor_badge` + `labels.sensor_status_label` + `styles.panel_header_html` panel başlığını besler. Veri/tespit/gözlem-modu DEĞİŞMEZ.

**Tech Stack:** Python 3.11, Streamlit 1.36.0, Altair 5.5, pandas, pytest, mypy strict, ruff.

## Global Constraints

- **Streamlit-native** — React/özel frontend YOK; yeni ağır bağımlılık YOK (altair mevcut).
- **Veri/tespit/mantık katmanı DEĞİŞMEZ** — `Anomaly`/`fuse_anomalies`/`Detector`/`_detect_once`/repository/`fleet.derive_*`/`split_alerts_by_axis`/migration şeması; dashboard yalnız okur + uyarı durumu (ack) yazar (gözlem modu).
- **Eşik/sayı değerleri config'ten** — `config/detectors.yaml` (hard-code yasak; config = tek hakikat). Dosya yok/bozuksa graceful (bölgesiz grafik).
- **`build_sensor_chart` imzası geriye-uyumlu genişler** — `band: LevelBand | None = None`, mevcut 4-arg pozisyonel çağrı kırılmaz.
- **Sektör-nötr** — gerçek firma/ürün adı yok ("MastGuard" placeholder korunur).
- **`unsafe_allow_html` güvenliği** — serbest-metin `html.escape()`; sayısal değerler format'lanır.
- **Yürütme ortamı:** subagent'lar Bash/Write izinsiz → controller-inline implement + salt-okunur reviewer hibridi. Her task sonunda **tam suite + mypy strict + ruff** (CLAUDE.md disiplini): `.venv/bin/python -m pytest`, `.venv/bin/python -m mypy src/... tests/...`, `ruff check src/... tests/...` (ruff = homebrew PATH).
- **Dal:** `dashboard-redesign-clean-corporate` üzerinde devam.

---

### Task 1: `thresholds.py` — LevelBand + level_band (saf)

Seviye-eşikli sensörlerin config'teki uyarı/kritik değerlerini okuyan saf modül. Radar bölgelerinin tek hakikat kaynağı.

**Files:**
- Create: `src/dashboard/thresholds.py`
- Test: `tests/unit/test_dashboard_thresholds.py`

**Interfaces:**
- Consumes: `detectors.config.DetectorConfig` (alan `rules: tuple[RuleConfig, ...]`, her `RuleConfig`: `name: str`, `enabled: bool`, `params: dict[str, Any]`).
- Produces: `LevelBand(warn: float, trip: float)` (frozen dataclass) ve `level_band(config: DetectorConfig | None, sensor: str) -> LevelBand | None`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_dashboard_thresholds.py`:
```python
"""dashboard.thresholds — config'ten seviye-eşiği okuma birim testleri."""
from __future__ import annotations

from typing import Any

from detectors.config import DetectorConfig, RuleConfig


def _cfg(*rules: RuleConfig) -> DetectorConfig:
    return DetectorConfig(poll_interval_s=5.0, window_s=120, rules=tuple(rules))


def _rule(name: str, params: dict[str, Any], enabled: bool = True) -> RuleConfig:
    return RuleConfig(name=name, severity="warning", enabled=enabled, params=params)


def test_level_band_temperature() -> None:
    from dashboard.thresholds import LevelBand, level_band

    cfg = _cfg(_rule("motor_temperature_high",
                     {"critical_threshold_c": 95.0, "trip_c": 130.0}))
    assert level_band(cfg, "motor_temperature") == LevelBand(warn=95.0, trip=130.0)


def test_level_band_current_and_vibration() -> None:
    from dashboard.thresholds import LevelBand, level_band

    cfg = _cfg(
        _rule("motor_current_high", {"threshold_a": 9.0, "trip_a": 11.0}),
        _rule("vibration_elevated", {"threshold_g": 0.37, "trip_g": 0.50}),
    )
    assert level_band(cfg, "motor_current") == LevelBand(warn=9.0, trip=11.0)
    assert level_band(cfg, "vibration") == LevelBand(warn=0.37, trip=0.50)


def test_level_band_none_for_non_level_sensors() -> None:
    from dashboard.thresholds import level_band

    cfg = _cfg(_rule("motor_temperature_high",
                     {"critical_threshold_c": 95.0, "trip_c": 130.0}))
    # slope/varyans/kuralsız sensörler seviye-bandı taşımaz
    assert level_band(cfg, "hydraulic_pressure") is None
    assert level_band(cfg, "motor_voltage") is None
    assert level_band(cfg, "mast_position") is None


def test_level_band_none_when_rule_disabled_or_missing() -> None:
    from dashboard.thresholds import level_band

    disabled = _cfg(_rule("motor_temperature_high",
                          {"critical_threshold_c": 95.0, "trip_c": 130.0}, enabled=False))
    assert level_band(disabled, "motor_temperature") is None
    assert level_band(_cfg(), "motor_temperature") is None  # kural yok
    assert level_band(None, "motor_temperature") is None    # config yok


def test_level_band_none_when_trip_not_above_warn() -> None:
    from dashboard.thresholds import level_band

    bad = _cfg(_rule("motor_current_high", {"threshold_a": 11.0, "trip_a": 9.0}))
    assert level_band(bad, "motor_current") is None  # trip <= warn → çizilemez


def test_level_band_none_on_missing_param() -> None:
    from dashboard.thresholds import level_band

    cfg = _cfg(_rule("motor_current_high", {"threshold_a": 9.0}))  # trip_a yok
    assert level_band(cfg, "motor_current") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_thresholds.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.thresholds'`.

- [ ] **Step 3: Write minimal implementation**

`src/dashboard/thresholds.py`:
```python
"""Seviye-eşikli sensörlerin radar bölgelerini config'ten okur (saf — streamlit/DB import etmez).

Dürüstlük: yalnız detector'ın SEVİYE eşiği kullandığı sensörlere (sıcaklık/akım/titreşim) band
üretir; slope (hidrolik), varyans (voltaj) ve kuralsız (mast_position) sensörlerde None döner —
sahte yatay bant uydurulmaz. Eşikler config = tek hakikat (hard-code yok).
"""
from __future__ import annotations

from dataclasses import dataclass

from detectors.config import DetectorConfig

# sensör → (kural adı, uyarı-param, kritik-param). Yalnız seviye-eşikli sensörler.
SENSOR_LEVEL_RULES: dict[str, tuple[str, str, str]] = {
    "motor_temperature": ("motor_temperature_high", "critical_threshold_c", "trip_c"),
    "motor_current": ("motor_current_high", "threshold_a", "trip_a"),
    "vibration": ("vibration_elevated", "threshold_g", "trip_g"),
}


@dataclass(frozen=True)
class LevelBand:
    """Bir sensörün seviye-eşiği: uyarı (warn) ve kritik (trip) sınırı."""

    warn: float
    trip: float


def level_band(config: DetectorConfig | None, sensor: str) -> LevelBand | None:
    """Sensörün seviye-bandını config'ten üretir; seviye-eşikli değilse/kural yoksa None.

    Args:
        config: Yüklenmiş DetectorConfig veya None (config okunamadıysa).
        sensor: Sensör adı.

    Returns:
        LevelBand(warn, trip) — sensör seviye-eşikli + kural enabled + iki param mevcut +
        trip > warn ise; aksi halde None.
    """
    if config is None or sensor not in SENSOR_LEVEL_RULES:
        return None
    rule_name, warn_key, trip_key = SENSOR_LEVEL_RULES[sensor]
    rule = next((r for r in config.rules if r.name == rule_name and r.enabled), None)
    if rule is None:
        return None
    try:
        warn = float(rule.params[warn_key])
        trip = float(rule.params[trip_key])
    except (KeyError, TypeError, ValueError):
        return None
    if trip <= warn:
        return None
    return LevelBand(warn=warn, trip=trip)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_thresholds.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Full gate + commit**

Run:
```
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/dashboard src/detectors tests/unit
ruff check src/dashboard tests/unit
```
Expected: tüm suite yeşil, mypy temiz, ruff temiz.
```bash
git add src/dashboard/thresholds.py tests/unit/test_dashboard_thresholds.py
git commit -m "feat(dashboard): thresholds.py — config'ten seviye-eşiği (radar bölgeleri için)"
```

---

### Task 2: `labels.py` — sensör durum etiketleri

Sensör okuması için "NORMAL/DİKKAT/KRİTİK" sözlüğü (mast "SAĞLIKLI" ama sensör "NORMAL" daha doğal okunur).

**Files:**
- Modify: `src/dashboard/labels.py` (sonuna ekleme)
- Test: `tests/unit/test_dashboard_labels.py` (yeni test ekleme)

**Interfaces:**
- Produces: `SENSOR_STATUS_LABELS: dict[str,str]` ve `sensor_status_label(badge: str) -> str`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_dashboard_labels.py` dosyasının sonuna ekle:
```python
def test_sensor_status_label() -> None:
    from dashboard.labels import sensor_status_label

    assert sensor_status_label("ok") == "NORMAL"
    assert sensor_status_label("warning") == "DİKKAT"
    assert sensor_status_label("critical") == "KRİTİK"
    assert sensor_status_label("bilinmeyen") == "bilinmeyen"  # fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_labels.py::test_sensor_status_label -q`
Expected: FAIL — `ImportError: cannot import name 'sensor_status_label'`.

- [ ] **Step 3: Write minimal implementation**

`src/dashboard/labels.py` — `BADGE_LABELS` tanımının hemen altına ekle:
```python
# Sensör OKUMASI durumu (mast "SAĞLIKLI", sensör "NORMAL" daha doğal). DİKKAT/KRİTİK ortak.
SENSOR_STATUS_LABELS: dict[str, str] = {"ok": "NORMAL", "warning": "DİKKAT", "critical": "KRİTİK"}
```
Ve dosyanın sonuna fonksiyon:
```python
def sensor_status_label(badge: str) -> str:
    """Sensör rozetini (ok/warning/critical) okuma-durumuna çevirir (bilinmeyen → ham)."""
    return SENSOR_STATUS_LABELS.get(badge, badge)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_labels.py -q`
Expected: PASS.

- [ ] **Step 5: Full gate + commit**

Run:
```
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/dashboard tests/unit
ruff check src/dashboard tests/unit
```
```bash
git add src/dashboard/labels.py tests/unit/test_dashboard_labels.py
git commit -m "feat(dashboard): sensor_status_label — sensör okuması NORMAL/DİKKAT/KRİTİK"
```

---

### Task 3: `fleet.py` — severity_to_badge çıkarımı + sensor_badge

Gömülü severity→rozet mantığını saf helper'a çıkar (DRY); sensör-bazlı rozet ekle.

**Files:**
- Modify: `src/dashboard/fleet.py` (`derive_device_health` refactor + 2 yeni fonksiyon)
- Test: `tests/unit/test_dashboard_fleet.py` (yeni testler ekleme)

**Interfaces:**
- Consumes: `alerts.models.Alert` (`severity: str`, `sensor: str`, `device_id`, `status`); `dashboard.transform.OPEN_STATUSES`; `BADGE_OK/BADGE_WARNING/BADGE_CRITICAL` (fleet sabitleri).
- Produces: `severity_to_badge(severities: list[str]) -> str` ve `sensor_badge(device_alerts: list[Alert], sensor: str) -> str`. **Semantik:** yalnız `critical` → `critical`; başka herhangi bir severity → `warning`; boş → `ok` (mevcut filo davranışıyla birebir — `high` da `warning`'e iner).
- **Davranış değişmez:** `derive_device_health` çıktısı aynen kalır (yalnız iç refactor).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_dashboard_fleet.py` sonuna ekle:
```python
def test_severity_to_badge_collapse() -> None:
    from dashboard.fleet import (BADGE_CRITICAL, BADGE_OK, BADGE_WARNING,
                                 severity_to_badge)

    assert severity_to_badge([]) == BADGE_OK
    assert severity_to_badge(["warning"]) == BADGE_WARNING
    assert severity_to_badge(["high"]) == BADGE_WARNING       # high → warning (mevcut semantik)
    assert severity_to_badge(["warning", "critical"]) == BADGE_CRITICAL


def test_sensor_badge_per_sensor() -> None:
    from dashboard.fleet import BADGE_CRITICAL, BADGE_OK, BADGE_WARNING, sensor_badge

    alerts = [
        _alert(1, "dev", severity="critical", sensor="motor_temperature"),
        _alert(2, "dev", severity="warning", sensor="vibration"),
    ]
    assert sensor_badge(alerts, "motor_temperature") == BADGE_CRITICAL
    assert sensor_badge(alerts, "vibration") == BADGE_WARNING
    assert sensor_badge(alerts, "motor_current") == BADGE_OK  # uyarı yok


def test_sensor_badge_ignores_closed_alerts() -> None:
    from dashboard.fleet import BADGE_OK, sensor_badge

    closed = [_alert(1, "dev", status="resolved", severity="critical",
                     sensor="motor_temperature")]
    assert sensor_badge(closed, "motor_temperature") == BADGE_OK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_fleet.py::test_severity_to_badge_collapse -q`
Expected: FAIL — `ImportError: cannot import name 'severity_to_badge'`.

- [ ] **Step 3: Write minimal implementation**

`src/dashboard/fleet.py` — `BADGE_CRITICAL = "critical"` satırının altına iki saf fonksiyon ekle. (`OPEN_STATUSES` zaten `fleet.py:8`'de import edilmiş — `from dashboard.transform import OPEN_STATUSES, relative_time`.)
```python
def severity_to_badge(severities: list[str]) -> str:
    """Severity listesini rozete indirger: critical varsa critical; herhangi varsa warning; yoksa ok.

    Filo semantiği: yalnız `critical` ayrıcalıklı; `high` dahil diğer her açık severity `warning`'e iner.
    """
    if any(s == "critical" for s in severities):
        return BADGE_CRITICAL
    if severities:
        return BADGE_WARNING
    return BADGE_OK


def sensor_badge(device_alerts: list[Alert], sensor: str) -> str:
    """Bir sensöre AÇIK uyarıların rozeti (açık yoksa ok). device_alerts cihaza önceden filtreli.

    Status filtresini kendi içinde yapar (çağıran hatasına karşı sağlam; saf). `severity` → `str`
    listesi → mypy temiz.
    """
    sevs = [a.severity for a in device_alerts
            if a.sensor == sensor and a.status in OPEN_STATUSES]
    return severity_to_badge(sevs)
```

Sonra `derive_device_health` içindeki gömülü dalı (mevcut `fleet.py:73-78`) `severity_to_badge`'e çevir — şu bloğu:
```python
    if any(a.severity == "critical" for a in open_alerts):
        badge = BADGE_CRITICAL
    elif open_alerts:
        badge = BADGE_WARNING
    else:
        badge = BADGE_OK
```
şununla değiştir (davranış aynen korunur — `open_alerts` zaten açık-filtreli):
```python
    badge = severity_to_badge([a.severity for a in open_alerts])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_fleet.py -q`
Expected: PASS (yeni 3 test + mevcut fleet testleri — özellikle `test_badge_critical_beats_warning` refactor sonrası hâlâ yeşil).

- [ ] **Step 5: Full gate + commit**

Run:
```
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/dashboard tests/unit
ruff check src/dashboard tests/unit
```
```bash
git add src/dashboard/fleet.py tests/unit/test_dashboard_fleet.py
git commit -m "feat(dashboard): severity_to_badge çıkarımı (DRY) + sensor_badge (sensör-bazlı durum)"
```

---

### Task 4: `charts.py` — band parametresi (radar bölgeleri + eşik çizgileri)

`build_sensor_chart`'a geriye-uyumlu `band` ekle: yeşil/sarı/kırmızı bölge `mark_rect`'leri + uyarı/kritik kesikli eşik çizgileri + y-domain eşikleri kapsayacak şekilde genişler.

**Files:**
- Modify: `src/dashboard/charts.py`
- Test: `tests/unit/test_dashboard_charts.py` (yeni testler; mevcutlar `band=None` ile değişmeden geçer)

**Interfaces:**
- Consumes: `dashboard.thresholds.LevelBand` (Task 1).
- Produces: `build_sensor_chart(frame, alerts, sensor, unit, band: LevelBand | None = None)` (yeni opsiyonel arg).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_dashboard_charts.py` sonuna ekle:
```python
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
    # eşik çizgileri: y encoding'li mark_rule (anomali rule x encoding kullanır)
    thresh = [ly for ly in spec["layer"]
              if ly["mark"]["type"] == "rule" and "y" in ly.get("encoding", {})]
    assert thresh
    # y-domain trip'i (11) kapsar → çizginin sınıra uzaklığı görünür
    line = [ly for ly in spec["layer"] if ly["mark"]["type"] == "line"][0]
    domain = line["encoding"]["y"]["scale"]["domain"]
    assert domain[1] >= 11.0


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_charts.py::test_chart_band_adds_zone_and_threshold_layers -q`
Expected: FAIL — `TypeError: build_sensor_chart() got an unexpected keyword argument 'band'`.

- [ ] **Step 3: Write minimal implementation**

`src/dashboard/charts.py`:

(a) Üst sabitlere (örn. `BAND_OPACITY = 0.15` altına) ekle:
```python
# Radar bölge renkleri (açık zemin; düşük opaklık ki çizgi/overlay üstte okunsun)
ZONE_OK = "#16a34a"
ZONE_WARN = "#d97706"
ZONE_CRIT = "#dc2626"
ZONE_OPACITY = 0.10
```

(b) Yeni saf yardımcı (modül seviyesinde, `build_sensor_chart`'tan önce):
Modül başına import ekle (mevcut `from alerts.models import Alert` yanına):
```python
from dashboard.thresholds import LevelBand
```
Yeni saf yardımcı:
```python
def _band_layers(
    lo: float, hi: float, band: LevelBand, y_scale: alt.Scale, x_domain: list
) -> list[alt.Chart]:
    """Seviye-bandı için bölge rect'leri + uyarı/kritik kesikli eşik çizgileri (paylaşılan y_scale).

    BÖLGE rect'i tam-genişlik için açık x-span taşır (x_domain = [tmin, tmax]); yalnız y/y2
    veren bir rect Vega-Lite'ta tam genişliğe yayılmaz (plan-review blocker'ı). Eşik çizgileri
    (mark_rule, yalnız y) doğal olarak tam-genişlik yatay çizgidir.
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
```

(c) `build_sensor_chart` imzasını ve gövdesini güncelle. Yeni tam fonksiyon:
```python
def build_sensor_chart(
    frame: pd.DataFrame,
    alerts: list[Alert],
    sensor: str,
    unit: str,
    band: LevelBand | None = None,
) -> alt.LayerChart | alt.Chart:
    """Bir sensörün telemetri çizgisi + opsiyonel radar bölgeleri + anomali overlay'i (spec § 3).

    Args:
        frame: readings_to_chart_frame çıktısı (timestamp/value/state; downsample'lı).
        alerts: Seçili cihazın uyarıları (içeride sensor'e filtrelenir).
        sensor: Sensör adı (y-ekseni başlığı).
        unit: Birim etiketi.
        band: Seviye-bandı (warn/trip) verilirse yeşil/sarı/kırmızı bölge + eşik çizgileri eklenir
            ve y-ekseni eşikleri kapsayacak şekilde genişler; None → klasik davranış.

    Returns:
        İnteraktif Altair chart'ı (band/uyarı yoksa tek çizgi; varsa katmanlı).
    """
    y_title = f"{sensor} ({unit})" if unit else sensor
    frame_empty = bool(frame.empty)
    x_domain = None if frame_empty else [frame["timestamp"].min(), frame["timestamp"].max()]

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
    x_enc = (
        alt.X("timestamp:T", title=None, scale=alt.Scale(domain=x_domain),
              axis=alt.Axis(labelFontSize=10))
        if fix_x
        else alt.X("timestamp:T", title=None, axis=alt.Axis(labelFontSize=10))
    )
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
    if band_bounds is not None and x_domain is not None:
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
        return line.interactive().properties(height=CHART_HEIGHT)
    layers.append(line)
    return alt.layer(*layers).interactive().properties(height=CHART_HEIGHT)
```

> DİKKAT (geriye-uyumluluk): `band=None` + uyarı yok → `layers` boş → tek çizgi (mevcut `test_chart_without_alerts_single_line_layer` geçer). `band=None` + uyarı var → katmanlar `[rect(overlay), rule, text, line]` → mevcut `test_chart_with_alert_has_four_layers` (`marks == ["rect","rule","text","line"]`) geçer.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_charts.py -q`
Expected: PASS (yeni 2 + mevcut 5; özellikle 4-katman ve tek-çizgi geriye-uyum testleri yeşil).

- [ ] **Step 5: Full gate + commit**

Run:
```
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/dashboard tests/unit
ruff check src/dashboard tests/unit
```
```bash
git add src/dashboard/charts.py tests/unit/test_dashboard_charts.py
git commit -m "feat(dashboard): build_sensor_chart band parametresi — radar bölgeleri + eşik çizgileri"
```

---

### Task 5: `styles.py` — panel_header_html + CSS

Cihaz Detayı'ndaki her sensör panelinin üst bloğu: sensör adı + renkli durum pill'i + güncel değer + meta.

**Files:**
- Modify: `src/dashboard/styles.py` (CSS bloğuna `.mg-panel*` + yeni fonksiyon)
- Test: `tests/unit/test_dashboard_styles.py` (yeni testler)

**Interfaces:**
- Produces: `panel_header_html(sensor_label: str, status_label: str, badge: str, value_str: str, meta_str: str) -> str`. `badge ∈ {ok,warning,critical}` → pill renk sınıfı (`mg-badge--{badge}`, mevcut sınıflar yeniden kullanılır).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_dashboard_styles.py` sonuna ekle:
```python
def test_panel_header_html_status_and_escape() -> None:
    from dashboard.styles import panel_header_html

    h = panel_header_html("Motor Sıcaklığı", "KRİTİK", "critical", "76 °C",
                          "Uyarı 95 · Kritik 130 <x>")
    assert "mg-panel" in h
    assert "Motor Sıcaklığı" in h
    assert "KRİTİK" in h
    assert "mg-badge--critical" in h  # mevcut pill renk sınıfı yeniden kullanılır
    assert "76 °C" in h
    assert "&lt;x&gt;" in h and "<x>" not in h  # meta html.escape'li


def test_panel_header_html_ok_uses_ok_class() -> None:
    from dashboard.styles import panel_header_html

    h = panel_header_html("Titreşim", "NORMAL", "ok", "0.12 g", "Uyarı 0.37 · Kritik 0.5")
    assert "mg-badge--ok" in h and "NORMAL" in h
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_styles.py::test_panel_header_html_ok_uses_ok_class -q`
Expected: FAIL — `ImportError: cannot import name 'panel_header_html'`.

- [ ] **Step 3: Write minimal implementation**

`src/dashboard/styles.py` — `APP_CSS` içinde `.mg-section {{...}}` satırından ÖNCE (kapanış `</style>` üstünde) panel CSS'i ekle:
```css
/* Cihaz Detayı sensör paneli */
.mg-panel {{display:flex; align-items:flex-start; justify-content:space-between; gap:8px;
  margin:4px 0 2px;}}
.mg-panel .mg-pname {{font-weight:700; font-size:15px; color:{_TEXT};}}
.mg-panel .mg-pval {{font-size:13px; color:{_MUTED};}}
.mg-panel .mg-pmeta {{display:block; font-size:12px; color:{_MUTED}; margin-top:1px;}}
```
> Not: f-string CSS olduğu için süslü parantezler `{{ }}` ile kaçışlanır (mevcut blok deseni).

Sonra `header_html`'den önce/sonra yeni fonksiyon:
```python
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
        f'<span class="mg-pname">{_html.escape(sensor_label)} '
        f'<span class="mg-badge mg-badge--{b}">{_html.escape(status_label)}</span></span>'
        f'<span class="mg-pval">{_html.escape(value_str)}</span>'
        "</div>"
        f'<span class="mg-pmeta">{_html.escape(meta_str)}</span>'
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_styles.py -q`
Expected: PASS.

- [ ] **Step 5: Full gate + commit**

Run:
```
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/dashboard tests/unit
ruff check src/dashboard tests/unit
```
```bash
git add src/dashboard/styles.py tests/unit/test_dashboard_styles.py
git commit -m "feat(dashboard): panel_header_html + .mg-panel CSS (Cihaz Detayı sensör başlığı)"
```

---

### Task 6: `app.py` — iki sayfa gezinme + Cihaz Detayı render

Sol-menü gezinme (Filo ↔ Cihaz), Cihaz Detayı fragment'i (6 radar paneli), config yükleme, geri-dön butonu. İnce wiring → birim test yok; boot smoke + canlı doğrulama.

**Files:**
- Modify: `src/dashboard/app.py`
- Test: `tests/unit/test_dashboard_app_boot.py` (mevcut, değişmeden yeşil kalmalı)

**Interfaces:**
- Consumes: `thresholds.level_band` (T1), `labels.sensor_status_label` (T2), `fleet.sensor_badge` (T3), `charts.build_sensor_chart(..., band=)` (T4), `styles.panel_header_html` (T5), `detectors.config.load_detector_config`/`DetectorConfig`, mevcut `_fetch_alerts_safe`/`fetch_window`/`window_to_since`/`downsample_frame`/`readings_to_chart_frame`/`WINDOW_OPTIONS`/`OPEN_STATUSES`/`device_label`/`sensor_label`.

- [ ] **Step 1: Import bloğunu genişlet**

`src/dashboard/app.py` import bölümünde — **MEVCUT import satırlarını GENİŞLET, yeni satır EKLEME** (duplicate-import lint/F811'i önle). Plan-review minor: `sensor_label` zaten `app.py:40`'ta, fleet bloğu `app.py:35-39`'da `DeviceHealth/compute_kpis/derive_fleet`'i, styles bloğu `app.py:41-48`'de 6 ismi import ediyor.

- `from dashboard.fleet import (...)` mevcut bloğuna **yalnız `sensor_badge`** ekle (DeviceHealth/compute_kpis/derive_fleet zaten var):
```python
from dashboard.fleet import (  # noqa: E402
    DeviceHealth,
    compute_kpis,
    derive_fleet,
    sensor_badge,
)
```
- `from dashboard.labels import sensor_label` (app.py:40) satırını şununla **DEĞİŞTİR** (ikinci import ekleme):
```python
from dashboard.labels import sensor_label, sensor_status_label  # noqa: E402
```
- `from dashboard.styles import (...)` mevcut bloğuna **yalnız `panel_header_html`** ekle:
```python
from dashboard.styles import (  # noqa: E402
    APP_CSS,
    alerts_section_html,
    fleet_html,
    fleet_summary_html,
    header_html,
    kpis_html,
    panel_header_html,
)
```
- **Yeni** iki import satırı ekle (bu modüller henüz import edilmiyor):
```python
from dashboard.thresholds import LevelBand, level_band  # noqa: E402
from detectors.config import DetectorConfig, load_detector_config  # noqa: E402
```

- [ ] **Step 2: Config yükleme + nav sabitleri + callback ekle**

`ALERTS_FETCH_LIMIT = 200` ve `_VIEW_OPTIONS` yakınına ekle:
```python
FLEET_LABEL = "🏠 Filo Genel Bakış"
```
`_resolve_db_path` yanına:
```python
def _resolve_detectors_config_path() -> Path:
    """DASHBOARD_DETECTORS_CONFIG env override; yoksa config/detectors.yaml."""
    return Path(os.environ.get("DASHBOARD_DETECTORS_CONFIG", "config/detectors.yaml"))


@st.cache_resource
def _get_detector_config() -> DetectorConfig | None:
    """detectors.yaml bir kez okunur (radar eşikleri için); okunamazsa None → bölgesiz grafik."""
    try:
        return load_detector_config(_resolve_detectors_config_path())
    except (FileNotFoundError, ValueError) as e:
        logger.info("detector config okunamadı (bölgesiz grafik): {}", e)
        return None


def _go_fleet() -> None:
    """Geri-dön butonu callback'i: sol-menü seçimini filoya çevirir (widget-state idiyomu)."""
    st.session_state["nav"] = FLEET_LABEL
```

- [ ] **Step 3: `_render_charts`'ı `_render_device_detail` ile değiştir**

Mevcut `@st.experimental_fragment(run_every="2s")` `_render_charts(...)` fonksiyonunu tümüyle şununla değiştir:
```python
def _value_str(value: float | None, unit: str) -> str:
    """Güncel değeri okunur biçimde formatlar (yoksa '—')."""
    if value is None:
        return "—"
    return f"{value:.1f} {unit}".strip()


def _meta_str(band: LevelBand | None, unit: str) -> str:
    """Panel meta satırı: seviye-bandı varsa eşikleri yaz; yoksa boş (sinyali çizgi+durum taşır)."""
    if band is None:
        return ""
    return f"Uyarı {band.warn:g} · Kritik {band.trip:g} {unit}".strip()


@st.experimental_fragment(run_every="2s")
def _render_device_detail(
    repository: TelemetryRepository, device_id: str, window: str,
    config: DetectorConfig | None,
) -> None:
    """Seçili cihazın 6 sensörünü radar paneli (durum + eşik-bölgeli grafik) olarak çizer (spec § 3)."""
    since = window_to_since(datetime.now(UTC), window)
    alerts, _ = _fetch_alerts_safe(repository)
    device_alerts = [a for a in alerts if a.device_id == device_id]
    if since is not None:
        device_alerts = [a for a in device_alerts if a.window_end >= since]
    cols = st.columns(3)
    for i, sensor in enumerate(SIX_SENSORS):
        try:
            readings = repository.fetch_window(device_id, sensor, since)
        except OperationalError as e:
            logger.error("Okuma hatası device={} sensor={}: {}", device_id, sensor, e)
            with cols[i % 3]:
                st.error(f"{sensor_label(sensor)}: okuma hatası")
            continue
        frame = downsample_frame(readings_to_chart_frame(readings))
        unit = readings[-1].unit if readings else ""
        last_val = readings[-1].value if readings else None
        badge = sensor_badge(device_alerts, sensor)
        band = level_band(config, sensor)
        with cols[i % 3]:
            st.markdown(
                panel_header_html(
                    sensor_label(sensor), sensor_status_label(badge), badge,
                    _value_str(last_val, unit), _meta_str(band, unit),
                ),
                unsafe_allow_html=True,
            )
            st.altair_chart(
                cast(alt.Chart, build_sensor_chart(frame, device_alerts, sensor, unit, band=band)),
                use_container_width=True,
                theme="streamlit",
            )
```

- [ ] **Step 4: `main()` gezinmesini güncelle**

`main()` içinde `if not devices:` guard'ından SONRAKİ TÜM satırları (mevcut `app.py:261-267`: `_render_overview(repository)` + `_render_alert_management(repository)` + `st.divider()` + iki `st.sidebar.selectbox` + `_render_charts(...)`) şununla **tamamen değiştir** — eski `st.divider()` ve eski sidebar selectbox satırları ORTADA KALMAMALI (orphan bırakma):
```python
    config = _get_detector_config()
    nav_options = [FLEET_LABEL] + [device_label(d) for d in devices]
    label_to_device = {device_label(d): d for d in devices}
    choice = st.sidebar.selectbox("Sayfa", nav_options, key="nav")

    if not choice or choice == FLEET_LABEL:
        _render_overview(repository)
        _render_alert_management(repository)
        return

    device_id = label_to_device.get(choice, devices[0])
    st.button("← Filoya dön", on_click=_go_fleet, key="back_btn")
    st.markdown(
        f'<div class="mg-section">{device_label(device_id)} · Sensör Durumu</div>',
        unsafe_allow_html=True,
    )
    window = (
        st.sidebar.selectbox("Zaman aralığı", list(WINDOW_OPTIONS.keys()), index=1, key="win")
        or list(WINDOW_OPTIONS.keys())[1]
    )
    _render_device_detail(repository, device_id, window, config)
```
> Not: `device_label(device_id)` `mg-section` içinde — `device_id` iç/sentetik (`device_00N`), serbest kullanıcı girdisi değil; mevcut `mg-section` kullanım deseniyle tutarlı (escape gerekmez, sabit-format).
> `DeviceHealth`/`compute_kpis`/`derive_fleet`/`alt` import'ları `_render_overview` tarafından hâlâ kullanılıyor — kaldırma.

- [ ] **Step 5: Run boot smoke + full gate**

Run:
```
.venv/bin/python -m pytest tests/unit/test_dashboard_app_boot.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/dashboard src/detectors tests/unit
ruff check src/dashboard tests/unit
```
Expected: boot smoke yeşil (boş-DB → erken `st.info`, fragment'lere ulaşmaz); tam suite yeşil; mypy + ruff temiz.

- [ ] **Step 6: Commit**

```bash
git add src/dashboard/app.py
git commit -m "feat(dashboard): iki-sayfa gezinme (Filo↔Cihaz) + Cihaz Detayı radar panelleri"
```

---

### Task 7: Canlı doğrulama + dokümantasyon

Gerçek 6-cihaz demo ile görsel doğrulama (spec § 5 closure) + CLAUDE.md/memory güncelleme.

**Files:**
- Modify: `CLAUDE.md` (dashboard çalıştırma notu — yeni iki-sayfa davranışı)
- (Kod değişikliği yok.)

- [ ] **Step 1: Demo'yu başlat**

Run: `./scripts/demo_down.sh && ./scripts/demo_up.sh`
~90 sn bekle (arızalar gelişsin). Dashboard: http://localhost:8501

- [ ] **Step 2: Görsel doğrulama (kullanıcı ekran görüntüsü)**

Kontrol listesi (spec § 5):
1. Sol menüden cihaz seçince yalnız o cihaz açılıyor; **"← Filoya dön" tıklanınca `StreamlitAPIException` OLMADAN** filoya dönüyor (plan-review: `session_state["nav"]` callback idiyomu 1.36'da geçerli ama otomasyonla test edilmiyor → canlı doğrula).
2. Seviye sensörlerinde (sıcaklık/akım/titreşim) yeşil/sarı/kırmızı bölge + uyarı/kritik kesikli çizgiler render oluyor; çizginin sınıra uzaklığı görünüyor.
3. Her panelde durum etiketi doğru (NORMAL/DİKKAT/KRİTİK), gerçek uyarılarla tutarlı.
4. Seviye-dışı sensörlerde (hidrolik/voltaj/konum) bölge yok ama durum etiketi + çizgi var.
5. 6-cihaz demo'da arızalı cihazda doğru panel kırmızı/sarı (005 sıcaklık kritik, 003 hidrolik, vb.).
6. Filo Genel Bakış sayfası eskisi gibi (bir-bakışta kartlar + KPI + iki-eksen uyarılar).

- [ ] **Step 3: CLAUDE.md güncelle**

Dashboard çalıştırma maddesine iki-sayfa davranışını ekle (sol menü Filo↔Cihaz; Cihaz Detayı radar panelleri = durum + eşik-bölgeli grafik; eşikler `config/detectors.yaml`'tan; `DASHBOARD_DETECTORS_CONFIG` env override).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(dashboard): iki-sayfa gezinme + radar grafik çalıştırma notu (canlı smoke doğrulandı)"
```

---

## Self-Review

**1. Spec coverage:**
- § 2 iki sayfa + sol-menü selectbox → Task 6 ✓
- § 2 A-tarzı referans-bölgeli panel → Task 4 (charts band) + Task 5 (panel header) ✓
- § 3 `thresholds.level_band` → Task 1 ✓
- § 3 `labels.sensor_status_label` → Task 2 ✓
- § 3 `fleet.severity_to_badge` çıkarımı + `sensor_badge` → Task 3 ✓
- § 3 `charts.build_sensor_chart(band=)` zones + threshold lines + y-domain → Task 4 ✓
- § 3 `styles.panel_header_html` + `.mg-panel` CSS → Task 5 ✓
- § 3 app.py nav + `_render_device_detail` + `_get_detector_config` + geri-dön + meta → Task 6 ✓
- § 5 test stratejisi (her saf helper unit; charts band introspection; boot smoke; canlı) → Task 1-6 + Task 7 ✓
- § 6 değişmeyen kontratlar → Global Constraints + her task'ta veri/tespit dokunulmaz ✓

**2. Placeholder scan:** Tüm kod adımları tam kod içeriyor; "TBD/TODO/handle edge cases" yok. Task 3'teki "Düzeltme" notu kesin son implementasyonu veriyor (status-filtreli `sensor_badge`).

**3. Type consistency:**
- `LevelBand(warn, trip)` — Task 1 tanımlar, Task 4 & Task 6 tüketir (alan adları `warn`/`trip` tutarlı) ✓
- `level_band(config, sensor) -> LevelBand | None` — T1 üretir, T6 çağırır ✓
- `sensor_badge(device_alerts, sensor) -> str` ("ok"/"warning"/"critical") — T3 üretir, T6 + `sensor_status_label`/`panel_header_html`'e besler ✓
- `panel_header_html(sensor_label, status_label, badge, value_str, meta_str)` — T5 tanımlar, T6 aynı sırayla çağırır ✓
- `build_sensor_chart(frame, alerts, sensor, unit, band=None)` — T4 genişletir, T6 `band=` ile çağırır; mevcut çağrılar (testler) 4-arg pozisyonel → kırılmaz ✓

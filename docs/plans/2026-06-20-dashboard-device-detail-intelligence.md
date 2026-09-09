# Dashboard — Cihaz Detayı "Sensör Zekâsı" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Cihaz Detayı'ndaki her sensör paneline (1) izleyen/yakalayan katman chip'leri ve (2) seviye sensörlerinde "kritiğe uzaklık" gauge'ı ekle — arkadaki çok-katmanlı analizi + ISO skoru görünür kıl.

**Architecture:** Yeni saf `dashboard/detection.py` (config'ten katman türetimi). `band_position_score` `detectors.scoring`'ten reuse. `styles.py`'ye 2 saf builder (chip + gauge) + CSS. `app.py._render_device_detail` panel render'ı zenginleşir. Yalnız Cihaz Detayı; landing değişmez. Veri/tespit/gözlem-modu DEĞİŞMEZ.

**Tech Stack:** Python 3.11, Streamlit 1.36, pytest, mypy strict, ruff.

## Global Constraints
- Streamlit-native; yeni ağır bağımlılık YOK.
- Veri/tespit/füzyon/skorlama/migration/gözlem-modu DEĞİŞMEZ; dashboard yalnız okur + ack yazar.
- Skor/eşik config+detector'dan (uydurma yok); seviye-eşiği olmayan sensörde gauge YOK (dürüstlük).
- Serbest metin `html.escape`. Sektör-nötr.
- Gate (her task): `.venv/bin/python -m pytest -q` + `.venv/bin/python -m mypy src/dashboard tests/unit` + `ruff check src/dashboard tests/unit`. Ortam: controller-inline + salt-okunur reviewer. Dal: `dashboard-redesign-clean-corporate`.

---

### Task 1: `detection.py` — katman türetimi (saf)

**Files:** Create `src/dashboard/detection.py` · Test `tests/unit/test_dashboard_detection.py`

**Interfaces — Produces:** `RULE_SENSOR`, `LAYER_RULE`, `LAYER_STAT`, `watching_layers(config, sensor) -> list[str]`, `catching_layer(rule_name) -> str`.

- [ ] **Step 1: Failing test** — `tests/unit/test_dashboard_detection.py`:
```python
"""dashboard.detection — tespit katmanı türetimi (config'ten + rule_name'den)."""
from __future__ import annotations

from typing import Any

from detectors.config import DetectorConfig, RuleConfig, StatisticalConfig


def _rule(name: str, params: dict[str, Any] | None = None, enabled: bool = True) -> RuleConfig:
    return RuleConfig(name=name, severity="warning", enabled=enabled, params=params or {})


def _cfg(rules: list[RuleConfig], stat_sensors: list[str] | None = None) -> DetectorConfig:
    stat = None
    if stat_sensors is not None:
        stat = StatisticalConfig(
            baseline_window_s=300, current_window_s=60,
            detectors=(RuleConfig("three_sigma", "warning", True, {"sensors": stat_sensors}),),
        )
    return DetectorConfig(poll_interval_s=5.0, window_s=120, rules=tuple(rules), statistical=stat)


def test_watching_layers_rule_and_stat() -> None:
    from dashboard.detection import watching_layers
    cfg = _cfg([_rule("motor_current_high", {"threshold_a": 9.0, "trip_a": 11.0})],
               stat_sensors=["motor_current", "vibration"])
    assert watching_layers(cfg, "motor_current") == ["Kural", "İstatistik"]


def test_watching_layers_rule_only() -> None:
    from dashboard.detection import watching_layers
    # motor_voltage: kural var (erratic) ama statistical sensors'ta yok → yalnız Kural
    cfg = _cfg([_rule("motor_voltage_erratic", {"std_threshold_v": 1.0, "trip_std_v": 5.0})],
               stat_sensors=["motor_current"])
    assert watching_layers(cfg, "motor_voltage") == ["Kural"]


def test_watching_layers_out_of_range_covers_all() -> None:
    from dashboard.detection import watching_layers
    cfg = _cfg([_rule("sensor_out_of_range", {"bounds": {"mast_position": [-50, 12000]}})])
    assert "Kural" in watching_layers(cfg, "mast_position")


def test_watching_layers_disabled_and_none() -> None:
    from dashboard.detection import watching_layers
    cfg = _cfg([_rule("motor_current_high", {"threshold_a": 9.0, "trip_a": 11.0}, enabled=False)])
    assert watching_layers(cfg, "motor_current") == []
    assert watching_layers(None, "motor_current") == []


def test_watching_layers_stat_no_sensors_param_covers_all() -> None:
    from dashboard.detection import watching_layers
    # statistical sensors param yoksa tüm sensörleri izler
    cfg = DetectorConfig(
        poll_interval_s=5.0, window_s=120, rules=(),
        statistical=StatisticalConfig(300, 60, (RuleConfig("three_sigma", "warning", True, {}),)),
    )
    assert watching_layers(cfg, "motor_temperature") == ["İstatistik"]


def test_catching_layer() -> None:
    from dashboard.detection import catching_layer
    assert catching_layer("motor_temperature_high") == "Kural"
    assert catching_layer("three_sigma:motor_current") == "İstatistik"
    assert catching_layer("iqr:vibration") == "İstatistik"
    assert catching_layer("fused(3)") == "Çoklu katman"
```

- [ ] **Step 2: Run FAIL** — `.venv/bin/python -m pytest tests/unit/test_dashboard_detection.py -q` → ModuleNotFoundError.

- [ ] **Step 3: Implement** — `src/dashboard/detection.py`:
```python
"""Tespit katmanı türetimi (saf — streamlit/DB import etmez).

Bir sensörü hangi katmanların izlediğini config'ten, bir uyarıyı hangi katmanın yakaladığını
rule_name'den türetir. Amaç: arkadaki çok-katmanlı analizi (kural + istatistik + füzyon) arayüzde
görünür kılmak. Uydurma yok — yalnız config + gerçek kural adları.
"""
from __future__ import annotations

from detectors.config import DetectorConfig

LAYER_RULE = "Kural"
LAYER_STAT = "İstatistik"

# Kural adı → hedef sensör. None: sensör param'dan (frozen) ya da tüm bounds (out_of_range).
RULE_SENSOR: dict[str, str | None] = {
    "motor_temperature_high": "motor_temperature",
    "motor_current_high": "motor_current",
    "vibration_elevated": "vibration",
    "hydraulic_pressure_decline": "hydraulic_pressure",
    "motor_voltage_erratic": "motor_voltage",
    "sensor_frozen": None,
    "sensor_out_of_range": None,
}


def _rule_targets_sensor(rule_name: str, params: dict, sensor: str) -> bool:
    """Bir kuralın (params'ıyla) verilen sensörü hedefleyip hedeflemediği."""
    if rule_name not in RULE_SENSOR:
        return False
    target = RULE_SENSOR[rule_name]
    if target is not None:
        return target == sensor
    if rule_name == "sensor_frozen":
        return params.get("sensor") == sensor
    if rule_name == "sensor_out_of_range":
        return sensor in (params.get("bounds") or {})
    return False


def watching_layers(config: DetectorConfig | None, sensor: str) -> list[str]:
    """Sensörü izleyen tespit katmanları (sıra: Kural, İstatistik); config yoksa boş.

    Kural: aktif bir kural sensörü hedefliyorsa. İstatistik: aktif bir statistical dedektörün
    `sensors` param'ı sensörü içeriyorsa (param yok/boş → tüm sensörler).
    """
    if config is None:
        return []
    layers: list[str] = []
    if any(
        r.enabled and _rule_targets_sensor(r.name, r.params, sensor) for r in config.rules
    ):
        layers.append(LAYER_RULE)
    stat = config.statistical
    if stat is not None:
        for d in stat.detectors:
            if not d.enabled:
                continue
            sensors = d.params.get("sensors")
            if not sensors or sensor in sensors:
                layers.append(LAYER_STAT)
                break
    return layers


def catching_layer(rule_name: str) -> str:
    """Uyarıyı yakalayan katman: fused→Çoklu katman; three_sigma/iqr→İstatistik; aksi→Kural."""
    if rule_name.startswith("fused("):
        return "Çoklu katman"
    if rule_name.startswith(("three_sigma:", "iqr:")):
        return LAYER_STAT
    return LAYER_RULE
```

- [ ] **Step 4: Run PASS. Step 5: Gate + commit** — `"feat(dashboard): detection.py — sensör izleyen/yakalayan katman türetimi (config + rule_name)"`

---

### Task 2: `styles.py` — layer chips + distance gauge builder'ları + CSS

**Files:** Modify `src/dashboard/styles.py` · Test `tests/unit/test_dashboard_styles.py`

**Interfaces — Produces:** `layer_chips_html(watching, caught, score) -> str`, `distance_gauge_html(pct, severity) -> str`.

- [ ] **Step 1: Failing test** — `tests/unit/test_dashboard_styles.py` sonuna ekle:
```python
def test_layer_chips_watching() -> None:
    from dashboard.styles import layer_chips_html
    h = layer_chips_html(["Kural", "İstatistik"], None, None)
    assert "İzleyen" in h and "Kural" in h and "İstatistik" in h
    assert "mg-chip" in h


def test_layer_chips_caught_with_score() -> None:
    from dashboard.styles import layer_chips_html
    h = layer_chips_html(["Kural", "İstatistik"], "Kural", 0.2)
    assert "Yakalayan" in h and "mg-chip--on" in h
    assert "skor 0.20" in h


def test_layer_chips_empty() -> None:
    from dashboard.styles import layer_chips_html
    assert layer_chips_html([], None, None) == ""


def test_distance_gauge_safe_and_filled() -> None:
    from dashboard.styles import distance_gauge_html
    safe = distance_gauge_html(0, "ok")
    assert "Güvenli" in safe and "mg-gauge" in safe
    hot = distance_gauge_html(68, "warning")
    assert "%68" in hot and "68%" in hot  # etiket + dolum genişliği
```

- [ ] **Step 2: Run FAIL** (ImportError).

- [ ] **Step 3: Implement** — `styles.py`, `panel_header_html`'den sonra ekle:
```python
def layer_chips_html(watching: list[str], caught: str | None, score: float | None) -> str:
    """Sensörü izleyen/yakalayan tespit katmanı chip'leri (+uyarı varsa gerçek skor).

    caught verilirse 'Yakalayan: <caught>' vurgulu + skor; yoksa 'İzleyen: <watching...>'.
    watching boş ve caught yoksa boş string.
    """
    if not watching and caught is None:
        return ""
    if caught is not None:
        chips = "".join(
            f'<span class="mg-chip mg-chip--on">{_html.escape(c)}</span>' if c == caught
            else f'<span class="mg-chip">{_html.escape(c)}</span>'
            for c in (watching or [caught])
        )
        if caught not in (watching or []):
            chips = f'<span class="mg-chip mg-chip--on">{_html.escape(caught)}</span>' + chips
        score_html = (
            f'<span class="mg-chip-score">skor {score:.2f}</span>' if score is not None else ""
        )
        return f'<div class="mg-layers"><span class="mg-lbl">Yakalayan</span>{chips}{score_html}</div>'
    chips = "".join(f'<span class="mg-chip">{_html.escape(c)}</span>' for c in watching)
    return f'<div class="mg-layers"><span class="mg-lbl">İzleyen</span>{chips}</div>'


def distance_gauge_html(pct: int, severity: str) -> str:
    """'Kritiğe uzaklık' ince gauge'ı: dolum=pct%, renk severity'den; pct==0 → 'Güvenli'.

    Args:
        pct: 0..100 (band_position_score*100, yuvarlanmış).
        severity: ok|warning|critical → dolum rengi sınıfı.
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
```
CSS — `APP_CSS` içinde `.mg-section {{...}}` satırından ÖNCE ekle (f-string `{{ }}`):
```css
/* Cihaz Detayı — katman chip'leri + kritiğe-uzaklık gauge */
.mg-layers {{display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin:8px 0 2px;}}
.mg-layers .mg-lbl {{font-family:{_MONO}; font-size:10px; letter-spacing:.07em; text-transform:uppercase;
  color:{_MUTED}; margin-right:2px;}}
.mg-chip {{font-size:11px; font-weight:500; padding:2px 8px; border:1px solid {_BORDER};
  border-radius:999px; color:{_MUTED};}}
.mg-chip--on {{background:{_CRITBG}; border-color:{_CRITBG}; color:{_CRIT}; font-weight:600;}}
.mg-chip-score {{font-family:{_MONO}; font-size:12px; font-weight:600; color:{_CRIT}; margin-left:auto;}}
.mg-gauge-row {{display:flex; align-items:center; gap:9px; margin:7px 0 2px;}}
.mg-glbl {{font-family:{_MONO}; font-size:10px; letter-spacing:.06em; text-transform:uppercase;
  color:{_MUTED}; min-width:108px;}}
.mg-gauge {{flex:1; height:7px; background:{_BORDER}; border-radius:4px; overflow:hidden;}}
.mg-gfill {{display:block; height:100%; background:{_OK};}}
.mg-gfill--warning {{background:{_WARN};}}
.mg-gfill--critical {{background:{_CRIT};}}
.mg-gfill--ok {{background:{_OK};}}
.mg-gpct {{font-family:{_MONO}; font-size:12px; font-weight:600; min-width:54px; text-align:right; color:{_MUTED};}}
.mg-gpct--warning {{color:{_WARN};}}
.mg-gpct--critical {{color:{_CRIT};}}
```

- [ ] **Step 4: Run PASS. Step 5: Gate + commit** — `"feat(dashboard): layer_chips_html + distance_gauge_html + CSS (sensör zekâsı)"`

---

### Task 3: `app.py` — _render_device_detail zenginleştirme

**Files:** Modify `src/dashboard/app.py` · Test `tests/unit/test_dashboard_app_boot.py` (yeşil kalır)

**Interfaces — Consumes:** Task 1 (`watching_layers`, `catching_layer`), Task 2 (`layer_chips_html`, `distance_gauge_html`), `band_position_score` (detectors.scoring), mevcut `level_band`/`sensor_badge`.

- [ ] **Step 1: Import ekle** (mevcut bloklara MERGE):
```python
from dashboard.detection import catching_layer, watching_layers  # noqa: E402
from dashboard.styles import (  # noqa: E402  → mevcut bloğa ekle:
    ...,
    distance_gauge_html,
    layer_chips_html,
    ...,
)
from detectors.scoring import band_position_score  # noqa: E402
```

- [ ] **Step 2: Yardımcı ekle** — `_meta_str`'den sonra:
```python
def _sensor_alert(device_alerts: list[Alert], sensor: str) -> Alert | None:
    """Bu sensöre ait en yüksek severity açık uyarı (yoksa None)."""
    matches = [a for a in device_alerts if a.sensor == sensor and a.status in OPEN_STATUSES]
    if not matches:
        return None
    rank = {"critical": 3, "high": 2, "warning": 1}
    return max(matches, key=lambda a: rank.get(a.severity, 0))
```
> `Alert` zaten import edili (app.py).

- [ ] **Step 3: Panel render'ı genişlet** — `_render_device_detail` içindeki `with cols[i % 3]:` bloğunu şununla değiştir:
```python
        alert = _sensor_alert(device_alerts, sensor)
        caught = catching_layer(alert.rule_name) if alert else None
        score = alert.score if alert else None
        watching = watching_layers(config, sensor)
        with cols[i % 3]:
            st.markdown(
                panel_header_html(
                    sensor_label(sensor), sensor_status_label(badge), badge,
                    _value_str(last_val, unit), _meta_str(band, unit),
                ),
                unsafe_allow_html=True,
            )
            chips = layer_chips_html(watching, caught, score)
            if chips:
                st.markdown(chips, unsafe_allow_html=True)
            if band is not None:
                raw = score if score is not None else (
                    band_position_score(last_val, band.warn, band.trip)
                    if last_val is not None else 0.0
                )
                st.markdown(
                    distance_gauge_html(round(raw * 100), badge), unsafe_allow_html=True
                )
            st.altair_chart(
                cast(alt.Chart, build_sensor_chart(frame, device_alerts, sensor, unit, band=band)),
                use_container_width=True,
                theme=None,
            )
```

- [ ] **Step 4: Boot smoke + full gate** — `.venv/bin/python -m pytest tests/unit/test_dashboard_app_boot.py -q` + tam gate.

- [ ] **Step 5: Commit** — `"feat(dashboard): Cihaz Detayı panelleri zenginleşti — katman chip'leri + kritiğe-uzaklık gauge"`

---

### Task 4: Canlı doğrulama

**Files:** (kod yok)

- [ ] **Step 1:** `./scripts/demo_down.sh && ./scripts/demo_up.sh`, ~90 sn bekle.
- [ ] **Step 2: Görsel doğrulama (kullanıcı):** Cihaz Detayı'nda:
  1. Sağlıklı seviye sensörü → "İzleyen: Kural · İstatistik" + gauge "Güvenli".
  2. Arızalı seviye sensörü (örn. 005 motor sıcaklığı / 002 akım) → "Yakalayan: Kural" vurgulu + gerçek skor + gauge dolu (renkli).
  3. Slope/varyans sensörü (003 hidrolik / 004 voltaj) arızalıyken → katman + skor var, gauge YOK.
  4. İstatistik kapsamı dışı sensör (motor_voltage/motor_temperature/mast_position) → yalnız "Kural" chip'i.

---

## Self-Review
- **Spec coverage:** katman türetimi (T1), chip+gauge builder+CSS (T2), panel wiring (T3), canlı (T4). ✓
- **Placeholder:** yok; tüm kod tam.
- **Type/isim tutarlılığı:** `watching_layers(config, sensor)->list[str]`, `catching_layer(rule_name)->str`, `layer_chips_html(watching, caught, score)`, `distance_gauge_html(pct:int, severity)`, `_sensor_alert(...)->Alert|None`, `band_position_score(value, warn, trip)` — T3'te aynen tüketiliyor. ✓
- **Dürüstlük:** gauge yalnız `band is not None` (seviye sensörü); skor uyarı varsa gerçek `alert.score`, yoksa anlık band_position. ✓
- **Gözlem modu:** yalnız okuma; landing değişmez. ✓

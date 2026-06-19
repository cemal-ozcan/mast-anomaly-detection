# Faz 8 Iter 8.8 — Veri-Kalitesi Ekseni Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sensör-sağlığı (validity) uyarılarını dashboard'da kestirimci arıza uyarılarından ayrı bir "Veri Kalitesi" panelinde göstermek (sunum-tarafı eksen ayrımı).

**Architecture:** Ayrım sunum tarafında: saf `split_alerts_by_axis` (transform) uyarıları `rule_set` bileşimine göre kestirimci vs veri-kalitesi olarak böler; `app.py` iki ayrı `st.dataframe` render eder. Tespit/reconciliation/füzyon/migration DEĞİŞMEZ. `VALIDITY_RULES` tek-kaynağı `base.py`'ye taşınır (detector + dashboard paylaşır).

**Tech Stack:** Python 3.11, Streamlit, pandas, pytest, mypy (strict), ruff.

## Global Constraints

- **Spec (tek hakem):** `docs/specs/2026-06-19-faz8-iter8-8-data-quality-axis-design.md`.
- **Ayrım yalnız sunum tarafında** — `Anomaly`/`fuse_anomalies`/`Detector` ABC/`_detect_once` reconciliation+deadband (8.7)/severity-banttan+re-activate+in-place (8.6)/gözlem modu/skor [0,1]/ACK yaşam döngüsü/migration şeması DEĞİŞMEZ. **YENİ migration YOK.**
- **`VALIDITY_RULES` içeriği değişmez** (`{"sensor_out_of_range", "sensor_frozen"}`) — yalnız konum `base.py`'ye taşınır.
- **Gating KAPSAM DIŞI** (gerçek-donanım fazı).
- **`transform.py` saf kalır** (streamlit/DB import etmez; `detectors.base` saf leaf → import güvenli).
- **Tip ipuçları zorunlu** (mypy strict), **docstring zorunlu** (Google stili), `loguru` (print yok).
- **Test komutu:** `.venv/bin/python -m pytest <path> -q -p no:cacheprovider --no-cov`. Tam suite: `.venv/bin/python -m pytest`. Lint: `.venv/bin/python -m mypy src ...` + `ruff check ...` (**ruff = homebrew PATH**).
- **Yürütme ortamı:** subagent'lar Bash/Write izinsiz → controller-inline implement + salt-okunur reviewer (8.4-8.7 hibrit).

---

## Dosya Haritası

| Dosya | Sorumluluk | Değişim |
|---|---|---|
| `src/detectors/base.py` | saf kontrat + VALIDITY_RULES tek-kaynak | +`VALIDITY_RULES` constant |
| `src/detectors/service.py` | reconciliation | `VALIDITY_RULES` local tanım → `base`'den import |
| `src/alerts/models.py` | Alert okuma modeli | +`rule_set: str \| None = None` |
| `src/storage/repository.py` | `_row_to_alert` | +`rule_set=row.rule_set` |
| `src/dashboard/transform.py` | saf sınıflandırma | +`is_data_quality_alert`, `split_alerts_by_axis` |
| `src/dashboard/app.py` | iki panel | `_render_overview` split + `_render_alert_table` helper |
| `src/dashboard/fleet.py` | rank tek-kaynak | dup `_SEVERITY_RANK` → `fusion.SEVERITY_RANK` |
| tests | TDD | base, repo, transform |

---

### Task 1: `VALIDITY_RULES` tek-kaynağı `base.py`'ye taşı

**Files:**
- Modify: `src/detectors/base.py` (constant ekle)
- Modify: `src/detectors/service.py:95` (local tanımı kaldır, import et)
- Test: `tests/unit/detectors/test_base.py`

**Interfaces:**
- Produces: `detectors.base.VALIDITY_RULES: frozenset[str]` = `{"sensor_out_of_range", "sensor_frozen"}`.
- `service.py` artık `from detectors.base import ... VALIDITY_RULES` (davranış değişmez; `apply_band_severity` aynı).

- [ ] **Step 1: Write failing test** (append to `tests/unit/detectors/test_base.py`)

```python
def test_validity_rules_constant() -> None:
    """VALIDITY_RULES base.py'de tek-kaynak; sensör-sağlığı kurallarını içerir (Iter 8.8)."""
    from detectors.base import VALIDITY_RULES

    assert VALIDITY_RULES == frozenset({"sensor_out_of_range", "sensor_frozen"})
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_base.py -k validity_rules -q -p no:cacheprovider --no-cov`
Expected: FAIL (`cannot import name 'VALIDITY_RULES'`).

- [ ] **Step 3a: Add constant to base.py** (`src/detectors/base.py`, `Anomaly` dataclass tanımından ÖNCE, importlardan sonra)

```python
# Sensör-sağlığı (veri-kalitesi) kuralları: skoru ikili validity bayrağı (1.0), band konumu DEĞİL
# (severity banttan türetilmez — Iter 8.4/8.6). Tek-kaynak burada (detector + dashboard paylaşır, Iter 8.8).
VALIDITY_RULES: frozenset[str] = frozenset({"sensor_out_of_range", "sensor_frozen"})
```

- [ ] **Step 3b: service.py import + local kaldır** (`src/detectors/service.py`)

`from detectors.base import Anomaly, Detector` → `from detectors.base import VALIDITY_RULES, Anomaly, Detector`
(ruff isort sırası: büyük harf önce mi? Mevcut `Anomaly, Detector` sırasını koru, VALIDITY_RULES'u doğru sıraya koy — ruff düzeltir; gerekirse `from detectors.base import Anomaly, Detector, VALIDITY_RULES`).

service.py:95'teki local `VALIDITY_RULES: frozenset[str] = frozenset({...})` satırını + üstündeki 2 yorum satırını SİL (artık base'den geliyor). `apply_band_severity` içindeki `if anomaly.rule_name in VALIDITY_RULES:` AYNEN kalır (artık import'tan).

- [ ] **Step 4: Run to verify PASS + full suite**

Run: `.venv/bin/python -m pytest -q -p no:cacheprovider --no-cov`
Expected: PASS (base test + tüm mevcut; davranış değişmedi).

- [ ] **Step 5: mypy + ruff + commit**

Run: `.venv/bin/python -m mypy src/detectors` + `ruff check src/detectors`
```bash
git add src/detectors/base.py src/detectors/service.py tests/unit/detectors/test_base.py
git commit -m "refactor(detectors): VALIDITY_RULES tek-kaynak base.py'ye (Faz 8 Iter 8.8)"
```

---

### Task 2: `Alert.rule_set` okuma alanı

**Files:**
- Modify: `src/alerts/models.py` (Alert dataclass)
- Modify: `src/storage/repository.py` (`_row_to_alert`)
- Test: `tests/unit/test_storage_alert_repository.py`

**Interfaces:**
- Produces: `Alert.rule_set: str | None = None` (default'lu → mevcut `Alert(...)` constructor'ları kırılmaz, `clean_streak` deseni). `_row_to_alert` → `rule_set=row.rule_set` (kolon migration 004'ten beri var).

- [ ] **Step 1: Write failing test** (append to `tests/unit/test_storage_alert_repository.py`)

```python
def test_fetch_alerts_carries_rule_set(migrated_engine: Engine) -> None:
    """_row_to_alert rule_set kolonunu Alert'e taşır (Iter 8.8 sınıflandırma için)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(rule="fused(2)"), "2026-06-03T10:00:00.000Z",
                        "motor_current_high,sensor_out_of_range")
    assert repo.fetch_alerts(None, limit=10)[0].rule_set == "motor_current_high,sensor_out_of_range"
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_alert_repository.py -k rule_set -q -p no:cacheprovider --no-cov`
Expected: FAIL (`Alert ... unexpected keyword 'rule_set'` veya AttributeError).

- [ ] **Step 3a: Add Alert field** (`src/alerts/models.py`, `clean_streak` alanından SONRA — son alan)

```python
    clean_streak: int = 0  # Iter 8.7 deadband sayacı (default'lu → mevcut constructor'lar kırılmaz)
    rule_set: str | None = None  # Iter 8.8: fingerprint (eksen sınıflandırması için; nullable)
```

- [ ] **Step 3b: `_row_to_alert` taşısın** (`src/storage/repository.py`, `_row_to_alert`, `clean_streak=row.clean_streak,` satırından sonra)

```python
            clean_streak=row.clean_streak,
            rule_set=row.rule_set,
```

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_alert_repository.py -q -p no:cacheprovider --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/alerts/models.py src/storage/repository.py tests/unit/test_storage_alert_repository.py
git commit -m "feat(storage): Alert.rule_set okuma alanı (Faz 8 Iter 8.8 eksen sınıflandırma)"
```

---

### Task 3: Saf sınıflandırma — `is_data_quality_alert` + `split_alerts_by_axis`

**Files:**
- Modify: `src/dashboard/transform.py` (importlar + iki fonksiyon)
- Test: `tests/unit/test_dashboard_alerts_transform.py`

**Interfaces:**
- Consumes: `detectors.base.VALIDITY_RULES` (Task 1), `Alert.rule_set` (Task 2).
- Produces:
  - `is_data_quality_alert(alert: Alert) -> bool` — `rule_set` boş/None → False; aksi: `rule_set` kuralları ⊆ `VALIDITY_RULES` → True.
  - `split_alerts_by_axis(alerts: list[Alert]) -> tuple[list[Alert], list[Alert]]` — `(faults, data_quality)`, sıra korunur.

- [ ] **Step 1: Write failing tests** (append to `tests/unit/test_dashboard_alerts_transform.py`)

```python
from dashboard.transform import is_data_quality_alert, split_alerts_by_axis


def _alert_rs(rule_set: str | None, device: str = "d1") -> Alert:
    return Alert(id=1, device_id=device, rule_name="r", sensor="s", severity="high", score=1.0,
                 window_start="a", window_end="b", value=1.0, description="d", created_at="c",
                 status="active", acknowledged_at=None, resolved_at=None, rule_set=rule_set)


def test_is_data_quality_single_validity_rule() -> None:
    assert is_data_quality_alert(_alert_rs("sensor_out_of_range")) is True
    assert is_data_quality_alert(_alert_rs("sensor_frozen")) is True


def test_is_data_quality_predictive_rule() -> None:
    assert is_data_quality_alert(_alert_rs("motor_current_high")) is False


def test_is_data_quality_mixed_fused_is_fault() -> None:
    # Çakışma (kestirimci + validity) → arıza ekseni (en az bir kestirimci kural var).
    assert is_data_quality_alert(_alert_rs("motor_current_high,sensor_out_of_range")) is False


def test_is_data_quality_multi_validity_is_dq() -> None:
    assert is_data_quality_alert(_alert_rs("sensor_frozen,sensor_out_of_range")) is True


def test_is_data_quality_empty_rule_set_is_fault() -> None:
    assert is_data_quality_alert(_alert_rs(None)) is False
    assert is_data_quality_alert(_alert_rs("")) is False


def test_split_alerts_by_axis_partitions_preserving_order() -> None:
    alerts = [_alert_rs("motor_current_high", "d1"), _alert_rs("sensor_out_of_range", "d2"),
              _alert_rs("vibration_elevated", "d3")]
    faults, dq = split_alerts_by_axis(alerts)
    assert [a.device_id for a in faults] == ["d1", "d3"]
    assert [a.device_id for a in dq] == ["d2"]
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_alerts_transform.py -k "data_quality or split" -q -p no:cacheprovider --no-cov`
Expected: FAIL (import error).

- [ ] **Step 3: Implement** (`src/dashboard/transform.py`)

Import ekle (alerts.models importu yanına):
```python
from detectors.base import VALIDITY_RULES
```
Fonksiyonlar (`latest_alert_per_device`'tan sonra, `_ALERT_COLUMNS`'tan önce uygun yer):
```python
def is_data_quality_alert(alert: Alert) -> bool:
    """Uyarı veri-kalitesi ekseninde mi (yalnız validity kurallarından mı oluşuyor)? (Iter 8.8).

    rule_set'teki TÜM kurallar VALIDITY_RULES'taysa True (sensör bütünlüğü); en az bir kestirimci
    kural varsa False (arıza ekseni). rule_set boş/None → False (kestirimci varsay).

    Args:
        alert: Sınıflandırılacak uyarı (rule_set fingerprint'i taşımalı).

    Returns:
        Veri-kalitesi (sensör-sağlığı) ekseninde mi.
    """
    if not alert.rule_set:
        return False
    rules = {r for r in alert.rule_set.split(",") if r}
    return bool(rules) and rules <= VALIDITY_RULES


def split_alerts_by_axis(alerts: list[Alert]) -> tuple[list[Alert], list[Alert]]:
    """Uyarıları (kestirimci_arızalar, veri_kalitesi) olarak ikiye böler; sıra korunur (Iter 8.8).

    Args:
        alerts: Bölünecek uyarılar.

    Returns:
        (faults, data_quality) — sırasıyla kestirimci arıza ve sensör-sağlığı uyarıları.
    """
    faults = [a for a in alerts if not is_data_quality_alert(a)]
    data_quality = [a for a in alerts if is_data_quality_alert(a)]
    return faults, data_quality
```

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_alerts_transform.py -q -p no:cacheprovider --no-cov`
Expected: PASS (6 yeni + mevcut).

- [ ] **Step 5: mypy + ruff + commit**

Run: `.venv/bin/python -m mypy src/dashboard` + `ruff check src/dashboard`
```bash
git add src/dashboard/transform.py tests/unit/test_dashboard_alerts_transform.py
git commit -m "feat(dashboard): split_alerts_by_axis + is_data_quality_alert saf sınıflandırma (Faz 8 Iter 8.8)"
```

---

### Task 4: Dashboard iki panel (`app.py`)

**Files:**
- Modify: `src/dashboard/app.py` (`_render_overview` + yeni `_render_alert_table` helper + import)

**Interfaces:**
- Consumes: `split_alerts_by_axis` (Task 3), mevcut `alerts_to_frame`/`severity_row_style`/`_filter_view`.
- Produces: iki ayrı uyarı paneli (arıza + veri-kalitesi). app.py ince presentation (unit test YOK; full suite import-sağlığı + closure canlı smoke).

- [ ] **Step 1: Import ekle** (`src/dashboard/app.py`, transform importları — `alerts_to_frame, ... latest_alert_per_device` yanına)

```python
    split_alerts_by_axis,
```

- [ ] **Step 2: `_render_overview`'daki tek-tablo bloğunu ikiye böl**

`st.subheader("🚨 Uyarılar")` sonrası mevcut blok:
```python
    visible = _filter_view(alerts, choice or "Cihaz özeti")
    if not visible:
        st.caption("Bu görünümde uyarı yok.")
        return
    frame = alerts_to_frame(visible, now)
    st.dataframe(
        frame.style.apply(severity_row_style, axis=1),
        use_container_width=True,
        hide_index=True,
    )
```
ŞUNUNLA değiştir:
```python
    visible = _filter_view(alerts, choice or "Cihaz özeti")
    faults, data_quality = split_alerts_by_axis(visible)
    _render_alert_table("🚨 Arıza Uyarıları", faults, now, "Açık arıza uyarısı yok.")
    _render_alert_table("🔌 Veri Kalitesi / Sensör Sağlığı", data_quality, now, "Tüm sensörler sağlıklı.")
```

- [ ] **Step 3: `_render_alert_table` helper ekle** (`_render_overview`'dan ÖNCE)

```python
def _render_alert_table(title: str, alerts: list[Alert], now: datetime, empty_msg: str) -> None:
    """Tek bir uyarı eksenini başlık + severity-stilli tablo olarak render eder (Iter 8.8).

    Args:
        title: Panel başlığı.
        alerts: Bu eksenin uyarıları.
        now: Göreli zaman için referans.
        empty_msg: Liste boşsa gösterilecek mesaj.
    """
    st.markdown(f"**{title}**")
    if not alerts:
        st.caption(empty_msg)
        return
    frame = alerts_to_frame(alerts, now)
    st.dataframe(
        frame.style.apply(severity_row_style, axis=1),
        use_container_width=True,
        hide_index=True,
    )
```
(`Alert` ve `datetime` app.py'de zaten import'lu — değilse ekle.)

- [ ] **Step 4: Run full suite + boot smoke**

Run: `.venv/bin/python -m pytest -q -p no:cacheprovider --no-cov`
Expected: tümü yeşil (transform split testleri; app.py import-hatası yok).

Headless boot smoke (Faz 3 deseni — boş DB ile main() veri-guard'ından erken döner, fragment'e ulaşmaz):
Run: `DASHBOARD_DB_PATH=/tmp/empty_iter88.db PYTHONPATH=src .venv/bin/python -c "import dashboard.app"` (import + main() çağrısı no-data dalında çöküyorsa raporla; veri yoksa graceful).
Expected: traceback yok (boş/eksik DB graceful).

- [ ] **Step 5: mypy + ruff + commit**

Run: `.venv/bin/python -m mypy src/dashboard` + `ruff check src/dashboard`
```bash
git add src/dashboard/app.py
git commit -m "feat(dashboard): arıza + veri-kalitesi iki ayrı uyarı paneli (Faz 8 Iter 8.8)"
```

---

### Task 5: `fleet.py` severity rank tek-kaynak cleanup

**Files:**
- Modify: `src/dashboard/fleet.py:15` (dup `_SEVERITY_RANK` → `fusion.SEVERITY_RANK`)
- Test: `tests/unit/test_dashboard_fleet.py` (mevcut, yeşil kalmalı)

**Interfaces:**
- Consumes: `detectors.fusion.SEVERITY_RANK` (`{"critical":3,"high":2,"warning":1,"info":0}`).
- fleet kullanımı `.get(severity, 0)` → davranış aynı (info=0 ek anahtar zararsız).

- [ ] **Step 1: Replace** (`src/dashboard/fleet.py`)

`_SEVERITY_RANK = {"warning": 1, "high": 2, "critical": 3}` satırını SİL; import bloğuna ekle:
```python
from detectors.fusion import SEVERITY_RANK
```
Kullanım satırını güncelle (fleet.py:82 civarı):
`key=lambda a: (_SEVERITY_RANK.get(a.severity, 0), a.created_at)` → `key=lambda a: (SEVERITY_RANK.get(a.severity, 0), a.created_at)`
(`_SEVERITY_RANK`'ın tüm kullanımlarını `SEVERITY_RANK` yap — grep ile teyit: `grep -n _SEVERITY_RANK src/dashboard/fleet.py`.)

- [ ] **Step 2: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_fleet.py -q -p no:cacheprovider --no-cov`
Expected: PASS (davranış değişmedi).

- [ ] **Step 3: mypy + ruff + commit**

Run: `.venv/bin/python -m mypy src/dashboard` + `ruff check src/dashboard`
```bash
git add src/dashboard/fleet.py
git commit -m "refactor(dashboard): fleet severity rank → fusion.SEVERITY_RANK tek-kaynak (Faz 8 Iter 8.8)"
```

---

### Task 6: Closure — canlı smoke (iki panel) + docs/memory + Faz 8 kapanışı

> **Controller-run (TDD task değil).**

- [ ] **Step 1: Tam suite + mypy + ruff (final, geniş kapsam)** — hepsi yeşil.

- [ ] **Step 2: Canlı 6-cihaz demo smoke** (`./scripts/demo_up.sh`)
  - **device_006** (`sensor_out_of_range`) → **"🔌 Veri Kalitesi / Sensör Sağlığı"** panelinde.
  - **device_002/003/004/005** (kestirimci) → **"🚨 Arıza Uyarıları"** panelinde.
  - device_001 temiz → her iki panel boş-durum mesajı.
  - 8.6/8.7 korunur (yaşayan uyarı + deadband). Dashboard açılıyor, çökme yok.
  - Teardown: `./scripts/demo_down.sh` + config `.bak` geri yükle.

- [ ] **Step 3: Docs** — `CLAUDE.md` Mevcut Faz + Faz 8'e Iter 8.8 closure + **Faz 8 Closure** özeti (POC sağlamlaştırma planı tamamlandı; gating + Katman 2/Faz 9+ gerçek-donanım/kapsam dışı).

- [ ] **Step 4: Memory** — `project_active_phase.md`: Iter 8.8 DONE + Faz 8 KAPANDI; sıradaki = gerçek cihaz tahsisi beklenir (kapsam içi iş kalmadı).

- [ ] **Step 5: Final whole-branch review** (salt-okunur reviewer) → fix loop.

- [ ] **Step 6:** Kullanıcı onayıyla PR/merge (push proaktif YAPMA).

---

## Self-Review (yazar kontrolü)

**1. Spec coverage:** §3 VALIDITY_RULES→base → T1. §4 Alert.rule_set → T2. §5 split_alerts_by_axis/is_data_quality_alert → T3. §6 dashboard iki panel → T4. §7 fleet rank dedup → T5. §8 test+smoke → her task TDD + T6. §9 değişmez kontratlar → Global Constraints + hiçbir task Anomaly/fuse/reconciliation/migration'a dokunmaz. ✓ Boşluk yok.

**2. Placeholder scan:** Tüm kod blokları tam; "TBD/handle edge cases" yok. ✓

**3. Type consistency:** `VALIDITY_RULES: frozenset[str]` (T1 base) ↔ transform import (T3) ↔ service import (T1) tutarlı. `Alert.rule_set: str | None` (T2) ↔ `is_data_quality_alert` `alert.rule_set` (T3) tutarlı. `split_alerts_by_axis -> tuple[list[Alert], list[Alert]]` (T3) ↔ app `faults, data_quality = split_alerts_by_axis(visible)` (T4) tutarlı. `SEVERITY_RANK` (fusion, Iter 8.6 public) ↔ fleet import (T5) tutarlı. ✓

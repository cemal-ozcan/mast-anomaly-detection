# Faz 8 Iter 8.4 — Skor Standardizasyonu (Band-Pozisyon) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tüm dedektörlerin `score` alanını tek ortak "band-pozisyon" semantiğine (`clamp01((q−warn)/(trip−warn))`) taşı, füzyonda gösterilen skoru temsilcinin kendi skoru yap, sensör-sağlığı skorunu 1.0 yap.

**Architecture:** Yeni saf `src/detectors/scoring.py` (`band_position_score`) tüm dedektörlerce paylaşılır. Eşik kuralları config'lenen `trip_*` kritik referansını alır (gerçek simülatör çıktısıyla kalibre); istatistik dedektörleri standart çapa kullanır (3σ→6σ, IQR→Tukey 3·IQR). `fuse_anomalies` tek satırda `score=top.score` olur. Şema/migration YOK (`score` zaten float). Gözlem modu korunur.

**Tech Stack:** Python 3.11, pandas/numpy, pytest, mypy strict, ruff. Dedektör motoru (`src/detectors/`).

## Global Constraints

- **Spec (tek hakem):** `docs/specs/2026-06-17-faz8-iter8-4-score-standardization-design.md`. Sapma → önce spec güncellenir.
- **Tip ipuçları zorunlu** (mypy strict). **Docstring zorunlu** (Google stili, Türkçe).
- **Config-driven, hard-coded yok:** `trip_*` değerleri config'ten gelir; istatistik çapaları config'te dokümante varsayılanlı.
- **TDD:** önce başarısız test, sonra minimal implementasyon. **Sık commit.**
- **Test/lint disiplini (her task sonunda):** `.venv/bin/python -m pytest -q` (tam suite) + `.venv/bin/python -m mypy src/detectors tests/unit tests/scenarios` + `ruff check src/detectors tests` (ruff = homebrew PATH, `.venv` değil).
- **Python çağrısı:** her zaman `.venv/bin/python` (sistem python ≠ venv; anaconda 3.13 SQLAlchemy uyumsuz).
- **ATOMİK İNİŞ (spec § 7):** bir kuralın `__init__` zorunlu `trip_*` ekleyen değişikliği + `config/detectors.yaml.example` + `config/detectors.demo.yaml` AYNI task'ta birlikte iner; yoksa `build_detectors` ValueError → detector/demo boot etmez.
- **Kalibre trip değerleri (gerçek sim çıktısıyla ölçüldü, spec § 10):**
  | kural | warn | ölçülen arıza-q | **trip** | arıza band-skoru |
  |---|---|---|---|---|
  | motor_temperature_high | 95 | 124.37°C | **130.0** | 0.84 |
  | motor_current_high | 9.0 | 9.978 A | **11.0** | 0.49 |
  | vibration_elevated | 0.37 | 0.4478 g | **0.50** | 0.60 |
  | hydraulic_pressure_decline | 3.0 | 5.028 bar/dk | **6.0** | 0.68 |
  | motor_voltage_erratic | 1.0 | 3.96 V | **5.0** | 0.74 |
- **İstatistik çapaları:** `sigma_k_critical=6.0` (warn `sigma_k=3.0`), `iqr_multiplier_critical=3.0` (warn `iqr_multiplier=1.5`).

---

## File Structure

| Dosya | Durum | Sorumluluk |
|---|---|---|
| `src/detectors/scoring.py` | YENİ | `band_position_score(q, warn, trip)` saf yardımcı |
| `src/detectors/fusion.py` | 1 satır | `score=max(...)` → `score=top.score` |
| `src/detectors/rules/sensor_out_of_range.py` | edit | `score=1.0` |
| `src/detectors/rules/motor_temperature_high.py` | rework | band-pozisyon + `trip_c` |
| `src/detectors/rules/motor_current_high.py` | rework | band-pozisyon + `trip_a` |
| `src/detectors/rules/vibration_elevated.py` | rework | band-pozisyon + `trip_g` |
| `src/detectors/rules/hydraulic_pressure_decline.py` | rework | band-pozisyon + `trip_slope_bar_per_min` |
| `src/detectors/rules/motor_voltage_erratic.py` | rework | band-pozisyon + `trip_std_v` |
| `src/detectors/statistical/three_sigma.py` | rework | band-pozisyon + `sigma_k_critical` |
| `src/detectors/statistical/iqr.py` | rework | Tukey far-out fence + `iqr_multiplier_critical` |
| `src/detectors/rules/sensor_frozen.py` | yorum | ikili-validity belgelenir (kod değişmez) |
| `config/detectors.yaml.example` + `config/detectors.demo.yaml` | +param | her kuralın `trip_*` + istatistik çapaları |
| `tests/unit/detectors/test_scoring.py` | YENİ | helper birim testleri |
| ilgili mevcut testler | güncelle | band-pozisyon + 2 semantik inversiyon (fusion, iqr) |
| `docs/DEMO.md` | güncelle | skor anlamı (band-pozisyon) notu |

---

## Task 1: `band_position_score` saf yardımcı

**Files:**
- Create: `src/detectors/scoring.py`
- Test: `tests/unit/detectors/test_scoring.py`

**Interfaces:**
- Produces: `band_position_score(q: float, warn: float, trip: float) -> float` — `q`'nun `warn→trip` bandındaki konumu `[0,1]`'e clamp; `trip <= warn` → `ValueError`.

- [ ] **Step 1: Başarısız testi yaz**

```python
# tests/unit/detectors/test_scoring.py
"""detectors.scoring.band_position_score birim testleri (Faz 8 Iter 8.4, spec § 3)."""
from __future__ import annotations

import pytest

from detectors.scoring import band_position_score


def test_at_warn_is_zero() -> None:
    assert band_position_score(95.0, warn=95.0, trip=130.0) == 0.0


def test_at_trip_is_one() -> None:
    assert band_position_score(130.0, warn=95.0, trip=130.0) == 1.0


def test_midpoint_is_half() -> None:
    assert band_position_score(112.5, warn=95.0, trip=130.0) == pytest.approx(0.5)


def test_below_warn_clamps_to_zero() -> None:
    assert band_position_score(90.0, warn=95.0, trip=130.0) == 0.0


def test_above_trip_clamps_to_one() -> None:
    assert band_position_score(200.0, warn=95.0, trip=130.0) == 1.0


def test_trip_not_greater_than_warn_raises() -> None:
    with pytest.raises(ValueError, match="trip"):
        band_position_score(5.0, warn=10.0, trip=10.0)
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_scoring.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.scoring'`

- [ ] **Step 3: Minimal implementasyon**

```python
# src/detectors/scoring.py
"""Band-pozisyon skoru: dedektörler arası ortak, karşılaştırılabilir [0,1] şiddet (Faz 8 Iter 8.4).

Anlam her dedektörde aynı: 0 = alarm (warn) sınırını yeni geçti, 1 = kritik (trip) seviyesi.
ISO 20816 zone mantığı (alarm=B/C, trip=C/D). Saf leaf — yalnız stdlib.
"""
from __future__ import annotations


def band_position_score(q: float, warn: float, trip: float) -> float:
    """`q`'nun `warn`→`trip` bandındaki konumu, `[0, 1]`'e clamp.

    Args:
        q: Ölçülen büyüklük (sensör değeri, sapma veya mesafe — non-negatif uzayda).
        warn: Alarm (tetik) sınırı → skor 0.
        trip: Kritik referans → skor 1.

    Returns:
        `(q - warn) / (trip - warn)`, `[0, 1]`'e clamp.

    Raises:
        ValueError: `trip <= warn` ise (band tanımsız).
    """
    if trip <= warn:
        raise ValueError(f"band_position_score: trip ({trip}) > warn ({warn}) olmalı")
    return max(0.0, min(1.0, (q - warn) / (trip - warn)))
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_scoring.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Lint + commit**

Run: `.venv/bin/python -m mypy src/detectors/scoring.py tests/unit/detectors/test_scoring.py && ruff check src/detectors/scoring.py tests/unit/detectors/test_scoring.py`
Expected: temiz

```bash
git add src/detectors/scoring.py tests/unit/detectors/test_scoring.py
git commit -m "feat(detectors): band_position_score saf yardımcı (Faz 8 Iter 8.4 spec § 3)"
```

---

## Task 2: Füzyon dürüstlüğü — `score=top.score`

**Files:**
- Modify: `src/detectors/fusion.py:44`
- Test: `tests/unit/detectors/test_fusion.py` (2 semantik inversiyon)

**Interfaces:**
- Consumes: yok (mevcut `_rank`, `Anomaly`).
- Produces: `fuse_anomalies` davranışı — `fused(N).score == top.score` (en-kötü-kazanır temsilcinin kendi skoru).

- [ ] **Step 1: Mevcut testleri yeni davranışa İNVERT et (eski hatalı `max` davranışını kodluyorlardı)**

`tests/unit/detectors/test_fusion.py` içinde:

`test_multiple_fuses_into_representative` — şu satırı:
```python
    assert fused.score == 0.9                # max skor (a2)
```
şununla DEĞİŞTİR (temsilci a1 = severity high, score 0.4):
```python
    assert fused.score == 0.4                # temsilcinin (a1, en yüksek severity) kendi skoru
```

`test_top_chosen_by_severity_then_score` — şu satırı:
```python
    assert fused.score == 1.0                     # ama skor yine max (warn_high)
```
şununla DEĞİŞTİR (temsilci crit_low = critical, score 0.1):
```python
    assert fused.score == 0.1                     # temsilcinin (crit_low, critical) kendi skoru
```

Ayrıca `test_multiple_fuses_into_representative` docstring'indeki "skor=max" ifadesini "skor=temsilcininki" yap.

- [ ] **Step 2: Testin (henüz değişmemiş kod ile) başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_fusion.py -q`
Expected: FAIL — `assert 0.9 == 0.4` (kod hâlâ max kullanıyor)

- [ ] **Step 3: `fusion.py`'da tek satırı düzelt**

`src/detectors/fusion.py` içinde:
```python
        score=max(a.score for a in anomalies),
```
satırını şununla değiştir:
```python
        score=top.score,
```
Ve `fuse_anomalies` docstring'indeki "score = max" ifadesini "score = temsilcinin (top) kendi skoru — gösterilen tüm alanlar tek anomaliye ait, tutarlı (Iter 8.4)" yap.

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_fusion.py -q`
Expected: PASS

- [ ] **Step 5: Lint + commit**

Run: `.venv/bin/python -m mypy src/detectors/fusion.py tests/unit/detectors/test_fusion.py && ruff check src/detectors/fusion.py tests/unit/detectors/test_fusion.py`

```bash
git add src/detectors/fusion.py tests/unit/detectors/test_fusion.py
git commit -m "fix(detectors): füzyonda gösterilen skor temsilcinin kendisi (ödünç max kalktı, Faz 8 Iter 8.4 spec § 4)"
```

---

## Task 3: Sensör-sağlığı skoru — `sensor_out_of_range` = 1.0

**Files:**
- Modify: `src/detectors/rules/sensor_out_of_range.py:51-53`
- Test: `tests/unit/detectors/test_sensor_out_of_range.py`

**Interfaces:**
- Produces: `SensorOutOfRange.detect(...)` anomalilerinin `score == 1.0` (ikili validity).

- [ ] **Step 1: Başarısız testi ekle**

`tests/unit/detectors/test_sensor_out_of_range.py` içine yeni test ekle:
```python
def test_score_is_one_binary_validity() -> None:
    """Sensör-sağlığı = ikili 'veri geçersiz' → skor sabit 1.0 (band-pozisyon değil, Iter 8.4)."""
    import pandas as pd

    window = pd.DataFrame(
        [
            {"device_id": "d1", "timestamp": "2026-05-30T00:00:00.000Z",
             "sensor": "mast_position", "state": "raising", "value": -500.0},
        ]
    )
    anomalies = SensorOutOfRange(bounds={"mast_position": [-50.0, 12000.0]}).detect(window)
    assert len(anomalies) == 1
    assert anomalies[0].score == 1.0
```

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_sensor_out_of_range.py::test_score_is_one_binary_validity -q`
Expected: FAIL — `assert 0.0373... == 1.0` (margin'li eski skor)

- [ ] **Step 3: `sensor_out_of_range.py`'da skoru sabitle**

`src/detectors/rules/sensor_out_of_range.py` `detect` içinde, şu bloğu:
```python
            row = sub.iloc[worst]
            value = float(row["value"])
            margin = hi - lo
            score = min(1.0, float(excess[worst]) / margin) if margin > 0 else 1.0
```
şununla değiştir (sınır-içi/dışı kararı `excess` ile korunur; yalnız skor ikili sabit):
```python
            row = sub.iloc[worst]
            value = float(row["value"])
            # Sensör-sağlığı = ikili "veri geçersiz" → skor 1.0 (band-pozisyon değil, Iter 8.4 spec § 5).
            score = 1.0
```
Modül docstring'ine bir satır ekle: "Skor ikili validity (1.0); band-pozisyon değil — bkz. spec § 5."

- [ ] **Step 4: Geçtiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_sensor_out_of_range.py -q`
Expected: PASS (mevcut `0.0 < a.score <= 1.0` testi de 1.0 ile geçer)

- [ ] **Step 5: Lint + commit**

Run: `.venv/bin/python -m mypy src/detectors/rules/sensor_out_of_range.py tests/unit/detectors/test_sensor_out_of_range.py && ruff check src/detectors/rules/sensor_out_of_range.py tests/unit/detectors/test_sensor_out_of_range.py`

```bash
git add src/detectors/rules/sensor_out_of_range.py tests/unit/detectors/test_sensor_out_of_range.py
git commit -m "fix(detectors): sensor_out_of_range skoru ikili 1.0 (Faz 8 Iter 8.4 spec § 5)"
```

---

## Task 4: `motor_temperature_high` band-pozisyon + `trip_c`

**Files:**
- Modify: `src/detectors/rules/motor_temperature_high.py`
- Modify: `config/detectors.yaml.example` + `config/detectors.demo.yaml`
- Test: `tests/unit/detectors/test_motor_temperature_high.py`

**Interfaces:**
- Consumes: `band_position_score` (Task 1).
- Produces: `MotorTemperatureHigh(critical_threshold_c: float, trip_c: float, severity=...)`; `trip_c <= critical_threshold_c` → `ValueError`. score = `band_position_score(peak, critical_threshold_c, trip_c)`.

- [ ] **Step 1: Başarısız testleri ekle**

`tests/unit/detectors/test_motor_temperature_high.py` içine:
```python
def test_trip_not_greater_than_warn_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        MotorTemperatureHigh(critical_threshold_c=95.0, trip_c=95.0)


def test_score_is_band_position() -> None:
    """peak=112.5, warn=95, trip=130 → band 0.5."""
    import pandas as pd
    window = pd.DataFrame(
        [{"device_id": "d1", "timestamp": "2026-05-30T00:00:00.000Z",
          "sensor": "motor_temperature", "state": "holding", "value": 112.5}]
    )
    a = MotorTemperatureHigh(critical_threshold_c=95.0, trip_c=130.0).detect(window)
    assert a[0].score == 0.5
```
Mevcut testlerde `MotorTemperatureHigh(critical_threshold_c=...)` çağrılarına `trip_c=130.0` ekle (örn. `MotorTemperatureHigh(critical_threshold_c=95.0, trip_c=130.0)`).

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_temperature_high.py -q`
Expected: FAIL — `__init__` `trip_c` kabul etmiyor

- [ ] **Step 3: Kuralı reworkle**

`src/detectors/rules/motor_temperature_high.py`:
- import ekle: `from detectors.scoring import band_position_score`
- `__init__` imzasını `critical_threshold_c: float, trip_c: float, severity: str = "critical"` yap; gövdeye:
```python
        if trip_c <= critical_threshold_c:
            raise ValueError(
                f"MotorTemperatureHigh: trip_c ({trip_c}) > critical_threshold_c "
                f"({critical_threshold_c}) olmalı"
            )
        self._trip_c = trip_c
```
- `detect` içinde skor satırını:
```python
        score = min(1.0, (peak - self._threshold) / self._threshold)
```
şununla değiştir:
```python
        score = band_position_score(peak, self._threshold, self._trip_c)
```

- [ ] **Step 4: Config'leri güncelle (ATOMİK — aynı commit)**

`config/detectors.yaml.example` ve `config/detectors.demo.yaml` her ikisinde, `motor_temperature_high` params bloğuna `trip_c` ekle:
```yaml
      params:
        critical_threshold_c: 95.0
        trip_c: 130.0
```

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_temperature_high.py tests/unit/detectors/test_config.py -q`
Expected: PASS
Run: `.venv/bin/python -m pytest -q` (tam suite — config-load + imza testleri kırılmadı)
Expected: PASS (1 skipped)
Run: `.venv/bin/python -m mypy src/detectors tests/unit && ruff check src/detectors tests`

- [ ] **Step 6: Commit**

```bash
git add src/detectors/rules/motor_temperature_high.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/detectors/test_motor_temperature_high.py
git commit -m "feat(detectors): motor_temperature_high band-pozisyon skoru + trip_c=130 (Faz 8 Iter 8.4)"
```

---

## Task 5: `motor_current_high` band-pozisyon + `trip_a`

**Files:**
- Modify: `src/detectors/rules/motor_current_high.py`
- Modify: `config/detectors.yaml.example` + `config/detectors.demo.yaml`
- Test: `tests/unit/detectors/test_motor_current_high.py`

**Interfaces:**
- Consumes: `band_position_score`.
- Produces: `MotorCurrentHigh(state, threshold_a, min_samples, trip_a, severity=...)`; `trip_a <= threshold_a` → `ValueError`. score = `band_position_score(mean_a, threshold_a, trip_a)`.

- [ ] **Step 1: Başarısız test ekle**

`tests/unit/detectors/test_motor_current_high.py`:
```python
def test_trip_not_greater_than_warn_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, trip_a=9.0)
```
Mevcut `MotorCurrentHigh(...)` çağrılarına `trip_a=11.0` ekle.

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_current_high.py -q`
Expected: FAIL — `__init__` `trip_a` kabul etmiyor

- [ ] **Step 3: Rework**

`src/detectors/rules/motor_current_high.py`:
- `from detectors.scoring import band_position_score`
- `__init__`'e `trip_a: float` (severity'den önce); gövdeye guard:
```python
        if trip_a <= threshold_a:
            raise ValueError(f"MotorCurrentHigh: trip_a ({trip_a}) > threshold_a ({threshold_a}) olmalı")
        self._trip_a = trip_a
```
- skor satırı `min(1.0, (mean_a - self._threshold) / self._threshold)` → `band_position_score(mean_a, self._threshold, self._trip_a)`

- [ ] **Step 4: Config (ATOMİK)**

`config/detectors.yaml.example` + `config/detectors.demo.yaml`, `motor_current_high` params'a `trip_a: 11.0` ekle.

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src/detectors tests/unit && ruff check src/detectors tests`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/detectors/rules/motor_current_high.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/detectors/test_motor_current_high.py
git commit -m "feat(detectors): motor_current_high band-pozisyon skoru + trip_a=11 (Faz 8 Iter 8.4)"
```

---

## Task 6: `vibration_elevated` band-pozisyon + `trip_g`

**Files:**
- Modify: `src/detectors/rules/vibration_elevated.py`
- Modify: `config/detectors.yaml.example` + `config/detectors.demo.yaml`
- Test: `tests/unit/detectors/test_vibration_elevated.py`

**Interfaces:**
- Produces: `VibrationElevated(state, threshold_g, min_samples, trip_g, severity=...)`; `trip_g <= threshold_g` → `ValueError`. score = `band_position_score(mean_g, threshold_g, trip_g)`.

- [ ] **Step 1: Başarısız test ekle**

`tests/unit/detectors/test_vibration_elevated.py`:
```python
def test_trip_not_greater_than_warn_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        VibrationElevated(state="raising", threshold_g=0.37, min_samples=10, trip_g=0.37)
```
Mevcut `VibrationElevated(...)` çağrılarına `trip_g=0.50` ekle.

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_vibration_elevated.py -q`
Expected: FAIL

- [ ] **Step 3: Rework**

`src/detectors/rules/vibration_elevated.py`:
- `from detectors.scoring import band_position_score`
- `__init__`'e `trip_g: float`; guard:
```python
        if trip_g <= threshold_g:
            raise ValueError(f"VibrationElevated: trip_g ({trip_g}) > threshold_g ({threshold_g}) olmalı")
        self._trip_g = trip_g
```
- skor `min(1.0, (mean_g - self._threshold) / self._threshold)` → `band_position_score(mean_g, self._threshold, self._trip_g)`

- [ ] **Step 4: Config (ATOMİK)**

`config/detectors.yaml.example` + `config/detectors.demo.yaml`, `vibration_elevated` params'a `trip_g: 0.50` ekle.

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src/detectors tests/unit && ruff check src/detectors tests`

- [ ] **Step 6: Commit**

```bash
git add src/detectors/rules/vibration_elevated.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/detectors/test_vibration_elevated.py
git commit -m "feat(detectors): vibration_elevated band-pozisyon skoru + trip_g=0.50 (Faz 8 Iter 8.4)"
```

---

## Task 7: `hydraulic_pressure_decline` band-pozisyon + `trip_slope_bar_per_min`

**Files:**
- Modify: `src/detectors/rules/hydraulic_pressure_decline.py`
- Modify: `config/detectors.yaml.example` + `config/detectors.demo.yaml`
- Test: `tests/unit/detectors/test_hydraulic_pressure_decline.py`

**Interfaces:**
- Produces: `HydraulicPressureDecline(state, slope_threshold_bar_per_min, min_samples, trip_slope_bar_per_min, severity=...)`; `trip_slope_bar_per_min <= slope_threshold_bar_per_min` → `ValueError`. score = `band_position_score(-slope_per_min, slope_threshold_bar_per_min, trip_slope_bar_per_min)` (her ikisi de POZİTİF büyüklük).

- [ ] **Step 1: Başarısız test ekle**

`tests/unit/detectors/test_hydraulic_pressure_decline.py`:
```python
def test_trip_not_greater_than_warn_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        HydraulicPressureDecline(
            state="holding", slope_threshold_bar_per_min=3.0, min_samples=60, trip_slope_bar_per_min=3.0
        )
```
Mevcut `HydraulicPressureDecline(...)` çağrılarına `trip_slope_bar_per_min=6.0` ekle.

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_hydraulic_pressure_decline.py -q`
Expected: FAIL

- [ ] **Step 3: Rework**

`src/detectors/rules/hydraulic_pressure_decline.py`:
- `from detectors.scoring import band_position_score`
- `__init__`'e `trip_slope_bar_per_min: float`; guard:
```python
        if trip_slope_bar_per_min <= slope_threshold_bar_per_min:
            raise ValueError(
                f"HydraulicPressureDecline: trip_slope_bar_per_min ({trip_slope_bar_per_min}) > "
                f"slope_threshold_bar_per_min ({slope_threshold_bar_per_min}) olmalı"
            )
        self._trip = trip_slope_bar_per_min
```
- skor `min(1.0, (-slope_per_min) / (self._threshold * 4.0))` → `band_position_score(-slope_per_min, self._threshold, self._trip)`
  (NOT: `slope_per_min` negatif; `-slope_per_min` pozitif kaçak hızı büyüklüğü; warn=`self._threshold` pozitif. Spec § 3 "mesafe/büyüklük uzayı".)

- [ ] **Step 4: Config (ATOMİK)**

`config/detectors.yaml.example` + `config/detectors.demo.yaml`, `hydraulic_pressure_decline` params'a `trip_slope_bar_per_min: 6.0` ekle.

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src/detectors tests/unit && ruff check src/detectors tests`

- [ ] **Step 6: Commit**

```bash
git add src/detectors/rules/hydraulic_pressure_decline.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/detectors/test_hydraulic_pressure_decline.py
git commit -m "feat(detectors): hydraulic_pressure_decline band-pozisyon skoru + trip=6.0 bar/dk (Faz 8 Iter 8.4)"
```

---

## Task 8: `motor_voltage_erratic` band-pozisyon + `trip_std_v`

**Files:**
- Modify: `src/detectors/rules/motor_voltage_erratic.py`
- Modify: `config/detectors.yaml.example` + `config/detectors.demo.yaml`
- Test: `tests/unit/detectors/test_motor_voltage_erratic.py`

**Interfaces:**
- Produces: `MotorVoltageErratic(std_threshold_v, min_samples, trip_std_v, severity=...)`; `trip_std_v <= std_threshold_v` → `ValueError`. score = `band_position_score(std_v, std_threshold_v, trip_std_v)`.

- [ ] **Step 1: Başarısız test ekle**

`tests/unit/detectors/test_motor_voltage_erratic.py`:
```python
def test_trip_not_greater_than_warn_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        MotorVoltageErratic(std_threshold_v=1.0, min_samples=10, trip_std_v=1.0)
```
Mevcut `MotorVoltageErratic(...)` çağrılarına `trip_std_v=5.0` ekle.

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_voltage_erratic.py -q`
Expected: FAIL

- [ ] **Step 3: Rework**

`src/detectors/rules/motor_voltage_erratic.py`:
- `from detectors.scoring import band_position_score`
- `__init__`'e `trip_std_v: float`; guard:
```python
        if trip_std_v <= std_threshold_v:
            raise ValueError(f"MotorVoltageErratic: trip_std_v ({trip_std_v}) > std_threshold_v ({std_threshold_v}) olmalı")
        self._trip = trip_std_v
```
- skor `min(1.0, (std_v - self._threshold) / (self._threshold * 5.0))` → `band_position_score(std_v, self._threshold, self._trip)`

- [ ] **Step 4: Config (ATOMİK)**

`config/detectors.yaml.example` + `config/detectors.demo.yaml`, `motor_voltage_erratic` params'a `trip_std_v: 5.0` ekle.

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src/detectors tests/unit && ruff check src/detectors tests`

- [ ] **Step 6: Commit**

```bash
git add src/detectors/rules/motor_voltage_erratic.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/detectors/test_motor_voltage_erratic.py
git commit -m "feat(detectors): motor_voltage_erratic band-pozisyon skoru + trip_std_v=5.0 (Faz 8 Iter 8.4)"
```

---

## Task 9: `three_sigma` band-pozisyon + `sigma_k_critical`

**Files:**
- Modify: `src/detectors/statistical/three_sigma.py`
- Modify: `config/detectors.yaml.example` + `config/detectors.demo.yaml`
- Test: `tests/unit/detectors/statistical/test_three_sigma.py`

**Interfaces:**
- Consumes: `band_position_score`.
- Produces: `ThreeSigma(... sigma_k=3.0, sigma_k_critical=6.0, ...)`; `sigma_k_critical <= sigma_k` → `ValueError`. score = `band_position_score(deviation, sigma_k*sigma, sigma_k_critical*sigma)` (sapma/büyüklük uzayı; çift-taraf `deviation` zaten non-negatif).

- [ ] **Step 1: Başarısız test ekle**

`tests/unit/detectors/statistical/test_three_sigma.py`:
```python
def test_sigma_k_critical_not_greater_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        ThreeSigma(current_window_s=60, sigma_k=6.0, sigma_k_critical=6.0)
```
(Mevcut `ThreeSigma(...)` çağrıları `sigma_k_critical` varsayılanı (6.0) ile çalışmaya devam eder — parametre opsiyonel.)

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/statistical/test_three_sigma.py -q`
Expected: FAIL — `__init__` `sigma_k_critical` kabul etmiyor

- [ ] **Step 3: Rework**

`src/detectors/statistical/three_sigma.py`:
- `from detectors.scoring import band_position_score`
- `__init__`'e `sigma_k_critical: float = 6.0` (sigma_k'dan sonra); guard:
```python
        if sigma_k_critical <= sigma_k:
            raise ValueError(f"ThreeSigma: sigma_k_critical ({sigma_k_critical}) > sigma_k ({sigma_k}) olmalı")
        self._sigma_k_critical = sigma_k_critical
```
- skor satırı `min(1.0, (deviation - fence) / fence)` → `band_position_score(deviation, fence, self._sigma_k_critical * sigma)`
  (mevcut `fence = self._sigma_k * sigma`; `warn=fence`, `trip=sigma_k_critical*sigma`. `band_position_score` guard `trip>warn` → `sigma_k_critical>sigma_k` zaten doğrulandı.)

- [ ] **Step 4: Config (ATOMİK)**

`config/detectors.yaml.example` + `config/detectors.demo.yaml`, `three_sigma` params'a `sigma_k_critical: 6.0` ekle:
- example: `params: {sigma_k: 3.0, sigma_k_critical: 6.0, min_baseline: 30, min_current: 5}`
- demo: `params: {sigma_k: 3.0, sigma_k_critical: 6.0, min_baseline: 20, min_current: 5, sensors: [motor_current, vibration, hydraulic_pressure]}`

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src/detectors tests/unit tests/scenarios && ruff check src/detectors tests`

- [ ] **Step 6: Commit**

```bash
git add src/detectors/statistical/three_sigma.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/detectors/statistical/test_three_sigma.py
git commit -m "feat(detectors): three_sigma band-pozisyon skoru + sigma_k_critical=6 (Faz 8 Iter 8.4)"
```

---

## Task 10: `iqr` Tukey far-out fence + `iqr_multiplier_critical`

**Files:**
- Modify: `src/detectors/statistical/iqr.py`
- Modify: `config/detectors.yaml.example` + `config/detectors.demo.yaml`
- Test: `tests/unit/detectors/statistical/test_iqr.py` (semantik inversiyon)

**Interfaces:**
- Consumes: `band_position_score`.
- Produces: `IQR(... iqr_multiplier=1.5, iqr_multiplier_critical=3.0, ...)`; `iqr_multiplier_critical <= iqr_multiplier` → `ValueError`. score = `band_position_score(distance, 0.0, (iqr_multiplier_critical - iqr_multiplier) * iqr)` = `distance/((crit-mult)*IQR)` (`distance` = iç-fence dışı non-negatif mesafe, mevcut).

- [ ] **Step 1: Testleri güncelle (semantik inversiyon + guard)**

`tests/unit/detectors/statistical/test_iqr.py`:
- `test_score_proportional_to_distance_beyond_fence`: docstring'i "score = distance/((far−1.5)·IQR) (Tukey far-out fence, Iter 8.4)" yap; satırı:
```python
    # baseline Q1=0.4 Q3=0.6 IQR=0.2 upper=0.9; cur medyan 0.95 → distance 0.05 → score 0.25
    ...
    assert abs(anomalies[0].score - 0.25) < 0.01
```
şununla değiştir (yeni payda `(3.0−1.5)·0.2 = 0.3` → `0.05/0.3 ≈ 0.1667`):
```python
    # baseline Q1=0.4 Q3=0.6 IQR=0.2; cur medyan 0.95 → distance 0.05; far-out span (3-1.5)*0.2=0.3 → 0.1667
    ...
    assert abs(anomalies[0].score - 0.1667) < 0.01
```
- Yeni guard testi ekle:
```python
def test_iqr_multiplier_critical_not_greater_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        IQR(current_window_s=60, iqr_multiplier=3.0, iqr_multiplier_critical=3.0)
```

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/statistical/test_iqr.py -q`
Expected: FAIL — `assert 0.25 ≈ 0.1667` (kod eski payda) + `__init__` `iqr_multiplier_critical` yok

- [ ] **Step 3: Rework**

`src/detectors/statistical/iqr.py`:
- `from detectors.scoring import band_position_score`
- `__init__`'e `iqr_multiplier_critical: float = 3.0` (iqr_multiplier'dan sonra); guard:
```python
        if iqr_multiplier_critical <= iqr_multiplier:
            raise ValueError(
                f"IQR: iqr_multiplier_critical ({iqr_multiplier_critical}) > "
                f"iqr_multiplier ({iqr_multiplier}) olmalı"
            )
        self._iqr_multiplier_critical = iqr_multiplier_critical
```
- skor satırı `min(1.0, distance / iqr)` → 
```python
            span = (self._iqr_multiplier_critical - self._iqr_multiplier) * iqr
            score = band_position_score(distance, 0.0, span)
```
  (`distance` = iç-fence dışı non-negatif mesafe; `warn=0`, `trip=span`; `span>0` çünkü `iqr>EPSILON` ve crit>mult.)

- [ ] **Step 4: Config (ATOMİK)**

`config/detectors.yaml.example` + `config/detectors.demo.yaml`, `iqr` params'a `iqr_multiplier_critical: 3.0` ekle:
- example: `params: {iqr_multiplier: 1.5, iqr_multiplier_critical: 3.0, min_baseline: 30, min_current: 5}`
- demo: `params: {iqr_multiplier: 1.5, iqr_multiplier_critical: 3.0, min_baseline: 20, min_current: 5, sensors: [motor_current, vibration, hydraulic_pressure]}`

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src/detectors tests/unit tests/scenarios && ruff check src/detectors tests`
Expected: PASS (360+ test; imza/overlap testleri yeşil)

- [ ] **Step 6: Commit**

```bash
git add src/detectors/statistical/iqr.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/detectors/statistical/test_iqr.py
git commit -m "feat(detectors): iqr Tukey far-out fence band-pozisyon skoru + critical=3.0 (Faz 8 Iter 8.4)"
```

---

## Task 11: Kapanış — `sensor_frozen` doc + DEMO.md + canlı smoke (CONTROLLER)

> Bu task controller (sen) tarafından yürütülür: doküman + manuel canlı smoke + closure.

**Files:**
- Modify: `src/detectors/rules/sensor_frozen.py` (yalnız yorum)
- Modify: `docs/DEMO.md`

- [ ] **Step 1: `sensor_frozen` ikili-validity yorumu**

`src/detectors/rules/sensor_frozen.py` modül/sınıf docstring'ine bir satır ekle:
"Skor ikili validity (sabit 1.0) — `sensor_out_of_range` ile aynı veri-kalitesi sınıfı (Iter 8.4 spec § 5)." (Kod zaten `score=1.0`; değişmez.)

- [ ] **Step 2: `docs/DEMO.md` skor anlamı notu**

`docs/DEMO.md`'ye kısa bir "Skor anlamı (Iter 8.4)" notu ekle: "Tüm dedektörlerde `score` = band-pozisyon: 0 = alarm sınırını yeni geçti, 1 = kritik (trip). Sensör-sağlığı (out_of_range/frozen) = 1.0 (ikili 'veri geçersiz'). Füzyonda gösterilen skor temsilci uyarınınkidir."

- [ ] **Step 3: Tam suite + mypy + ruff (son kez)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (1 skipped)
Run: `.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/dashboard tests/unit tests/integration tests/scenarios`
Run: `ruff check src tests`
Expected: temiz

- [ ] **Step 4: Canlı demo smoke (6 cihaz)**

Run: `./scripts/demo_up.sh` (mosquitto + 5 süreç + seed). ~3-4 dk bekle, sonra:
Run: `sqlite3 data/telemetry.db "SELECT device_id, rule_name, severity, ROUND(score,3) FROM anomalies ORDER BY created_at DESC LIMIT 20;"`
Beklenen (spec § 11): 001 temiz 0 uyarı; her arıza doğru kural + **makul band-pozisyon skoru**
(temp ~0.84, current/vibration/hydraulic/voltage ~0.5-0.74; istatistik overlap'lar **1.0'a satüre** olabilir — beklenen; out_of_range/donma 1.0); füzyon skoru temsilciye ait.
Run: `./scripts/demo_down.sh` (temiz teardown).

- [ ] **Step 5: Closure commit (CLAUDE.md + ROADMAP + memory)**

CLAUDE.md "Mevcut Faz" + ROADMAP Iter 8.4 DONE + canlı smoke sonucu; memory `project_active_phase.md` güncelle (Iter 8.4 ✅, sıradaki 8.5/8.6).
```bash
git add -A
git commit -m "docs(faz8): Iter 8.4 closure — skor standardizasyonu DONE + canlı smoke sonucu"
```

---

## Self-Review

**1. Spec coverage:**
- A (band-pozisyon) → Task 1 (helper) + Task 4-8 (eşik kuralları) + Task 9-10 (istatistik). ✅
- B (füzyon top.score) → Task 2. ✅
- C (sensör-sağlığı 1.0) → Task 3 (out_of_range) + Task 11 (frozen doc). ✅
- Spec § 7 atomik iniş → her kural task'ı `__init__` + iki YAML birlikte (Step 4 her birinde). ✅
- Spec § 7 istatistik guard config'lenmiş çarpana karşı → Task 9 (`sigma_k_critical>sigma_k`) + Task 10 (`iqr_multiplier_critical>iqr_multiplier`). ✅
- Spec § 6 test inversiyonları → Task 2 (test_fusion) + Task 10 (test_iqr) açıkça. ✅
- Spec § 10 kalibrasyon → Global Constraints tablosu (ölçülen trip'ler). ✅
- Spec § 11 canlı smoke + satürasyon beklentisi → Task 11 Step 4. ✅

**2. Placeholder taraması:** Tüm kod blokları gerçek; trip değerleri ölçülmüş sabitler; "follow pattern" yok. ✅

**3. Tip tutarlılığı:** `band_position_score(q, warn, trip)` imzası Task 1'de tanımlı, Task 4-10'da aynı isim/sıra. `trip_*` param adları her task'ta tutarlı. ✅

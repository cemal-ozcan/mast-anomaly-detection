# Faz 4 — Iterasyon 4.2: Kural Seti + Config + A/B/C İmza Testleri Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Iter 4.1'in tek-kural iskeletini ≥5 kurallık tam sete (eşik/süre/türev/oran/varyans) genişletmek, kuralları `config/detectors.yaml`'dan parametrize etmek (config loader + `build_detectors`), eşikleri simülatör çıktısına kalibre etmek ve A/B/C arıza senaryolarını dedektörlerle yakalayan imza testleri yazmak.

**Architecture:** 5 yeni kural sınıfı (`src/detectors/rules/`), her biri Iter 4.1 `MotorTemperatureHigh` desenini izler (self-contained `Detector` alt sınıfı, params constructor-DI). `src/detectors/config.py` `detectors.yaml`'ı `DetectorConfig`/`RuleConfig`'e parse eder + `build_detectors` `RULE_REGISTRY`'den config-driven dedektör listesi kurar (`severity` + `params` → constructor). `service.run()` artık dedektörleri hard-code etmez, config'ten kurar. İmza testleri Faz 1 engine harness'ını (CountingClock + mock publisher) yeniden kullanır: senaryo fixture'ını koştur → uzun-format pencere kur → dedektörü çalıştır → arıza penceresinde tetikleniyor, temiz pencerede tetiklenmiyor (FP yok).

**Tech Stack:** Python 3.11, pandas, numpy (slope için), SQLAlchemy, loguru, pytest, scipy (mevcut — imza testlerinde gerekmez, eşik-tabanlı assert). Yeni bağımlılık YOK (numpy zaten dolaylı dep; explicit kullanım için requirements'ta varlığı Task 3'te doğrulanır).

---

## Kalibrasyon Ölçümleri (gerçek simülatör çıktısı — eşiklerin gerekçesi)

Bu eşikler **tahmin değil**; engine harness'ıyla (fixture device config'leri, seed 42, 400 iterasyon) ölçülen clean-vs-fault dağılımlarından seçildi. Sensör `compute()` state-bağımlı ölçek uygular (örn. motor_current RAISING=8.0A, HOLDING=0.5A — `src/simulator/sensors/`), bu yüzden eşikler **fiziksel per-state ölçeğe** kalibre:

| Sinyal (state) | Clean | Fault (senaryo) | Seçilen eşik | Kural tipi |
|---|---|---|---|---|
| motor_current RAISING mean | mean 8.00, max 8.33 | mean 9.98 (MechanicalWear) | **> 9.0 A** (pencere ort., ≥10 örnek) | eşik+süre |
| vibration RAISING mean | mean 0.301, max 0.323 | mean 0.449 (MechanicalWear) | **> 0.37 g** (pencere ort., ≥10 örnek) | oran |
| hydraulic_pressure HOLDING slope | −0.16 bar/dk | −5.16 bar/dk (HydraulicLeak) | **< −1.5 bar/dk** (≥10 örnek) | türev |
| motor_voltage window std | std 0.19, max-rolling 0.25 | std 3.98 (ElectricalFault) | **> 1.0 V** (≥10 örnek) | varyans |
| motor_temperature peak | ~25–40°C (normalde 80'e ulaşmaz) | — (simülatör F üretmez) | **> 80 °C** (Iter 4.1) | eşik (universal) |
| sensor_frozen (donmuş) | gürültülü → asla donmaz | — (simülatör üretmez) | son N örnek aralığı ≤ ε | süre (universal) |

**Neden pencere-ortalaması (motor_current/vibration):** tek-örnek eşiğinde clean-fault aralığı çok dar (vibration clean max 0.323 vs fault min 0.331 → ~0.008g; gürültüyle tek örnek FP riski). Pencere ortalaması (≥10 örnek) ayrımı sağlamlaştırır (clean ort. çok stabil). **Slope/std** zaten temiz ayrılır.

**FP güvencesi:** clean fixture (senaryosuz, tüm state'ler) üzerinde **hiçbir kural tetiklenmez** — bu Task 9 imza testinde doğrulanır (kabul kriteri 4'ün Iter 4.2 ayağı; tam FP-oranı Iter 4.3).

---

## Spec Hizalama / Tasarım Kararları (uygulamadan önce oku)

1. **State string'leri küçük harf.** Telemetri `state` kolonu küçük-harf string tutar (`DeviceState` StrEnum value'ları: `"idle"/"raising"/"holding"/"lowering"`). Kurallar `window["state"] == self._state` ile karşılaştırır; config `state` değerleri küçük harf yazılır.
2. **Config-driven `severity`.** Spec § 5 `Anomaly.severity` config-driven. Her kural `__init__` `severity: str` (default'lu) alır; `build_detectors` config'teki `severity`'yi geçer. Iter 4.1 `MotorTemperatureHigh`'a geriye-uyumlu `severity` eklenir (Task 6).
3. **`RULE_REGISTRY` tipi `Callable[..., Detector]`.** Kurallar farklı `__init__` imzalarına sahip; generic `cls(severity=..., **params)` çağrısının mypy-strict geçmesi için registry `dict[str, Callable[..., Detector]]` olarak tiplenir (sınıflar bu tipi sağlar). Iter 4.1'de `dict[str, type[Detector]]`'di — Task 1 bunu değiştirir.
4. **db_path paylaşımı korunur.** `detectors.yaml` `poll_interval_s` + `window_s` + `rules` taşır; `db_path` hâlâ `ingestion.yaml`'dan (paylaşılan telemetry.db). `run(ingestion_config_path, detectors_config_path)`.
5. **İmza testi penceresi.** Publisher `timestamp` üretmez (publish anında kendi üretir) → harness collected reading'lere **per-sensör monoton 1sn timestamp** atar (slope bar/dk doğru çıksın). Tek-HOLDING-epizodu için hydraulic testinde `max_iterations` ayarlanır (aşağıda).
6. **YAGNI:** fusion YOK (Iter 4.3), dashboard paneli YOK (Iter 4.3), istatistik/ML YOK (Faz 5/6). Sadece kurallar + config + imza testleri.

**Test/lint komutu (her task sonunda; `.venv/bin/python` kullan — sistem `python` yanlış yorumlayıcı olabilir):**
```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios
```

---

## Dosya Yapısı

**Oluşturulacak:**
- `src/detectors/rules/motor_current_high.py` — `MotorCurrentHigh`
- `src/detectors/rules/vibration_elevated.py` — `VibrationElevated`
- `src/detectors/rules/hydraulic_pressure_decline.py` — `HydraulicPressureDecline`
- `src/detectors/rules/motor_voltage_erratic.py` — `MotorVoltageErratic`
- `src/detectors/rules/sensor_frozen.py` — `SensorFrozen`
- `src/detectors/config.py` — `RuleConfig`/`DetectorConfig` + `load_detector_config` + `build_detectors`
- `config/detectors.yaml.example` — **REWRITE** (mevcut scaffold farklı şekilde)
- `tests/unit/detectors/test_motor_current_high.py`
- `tests/unit/detectors/test_vibration_elevated.py`
- `tests/unit/detectors/test_hydraulic_pressure_decline.py`
- `tests/unit/detectors/test_motor_voltage_erratic.py`
- `tests/unit/detectors/test_sensor_frozen.py`
- `tests/unit/detectors/test_config.py` — config loader + build_detectors
- `tests/fixtures/devices_clean_baseline.yaml` — senaryosuz, tüm state'li clean fixture
- `tests/scenarios/test_rule_signatures.py` — A/B/C + clean imza testleri

**Değiştirilecek:**
- `src/detectors/rules/__init__.py` — `RULE_REGISTRY` 1→6 entry + tip `Callable[..., Detector]`
- `src/detectors/rules/motor_temperature_high.py` — `severity` param (geriye-uyumlu)
- `src/detectors/service.py` — `run()` config-driven dedektör kurulumu
- `tests/scenarios/conftest.py` — `build_detector_window()` harness helper

---

## Task 1: MotorCurrentHigh kuralı (eşik+süre, A) + registry tip değişikliği

**Files:**
- Create: `src/detectors/rules/motor_current_high.py`
- Modify: `src/detectors/rules/__init__.py`
- Test: `tests/unit/detectors/test_motor_current_high.py`

- [ ] **Step 1: Failing test** — `tests/unit/detectors/test_motor_current_high.py`

```python
"""MotorCurrentHigh birim testi (Faz 4 Iter 4.2, spec § 6 — A, eşik+süre)."""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly
from detectors.rules.motor_current_high import MotorCurrentHigh


def _window(values: list[float], state: str = "raising", sensor: str = "motor_current") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:00:{i:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": [state] * len(values),
            "value": values,
        }
    )


def test_triggers_when_raising_mean_above_threshold() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10)
    window = _window([10.0] * 12)  # RAISING ort. 10.0 > 9.0, 12 ≥ 10 örnek
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert isinstance(a, Anomaly)
    assert a.rule_name == "motor_current_high"
    assert a.sensor == "motor_current"
    assert a.device_id == "device_001"
    assert a.value == 10.0  # pencere ortalaması
    assert a.severity == "warning"  # default
    assert 0.0 <= a.score <= 1.0


def test_severity_is_configurable() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10, severity="high")
    assert rule.detect(_window([10.0] * 12))[0].severity == "high"


def test_no_trigger_when_mean_below_threshold() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10)
    assert rule.detect(_window([8.0] * 12)) == []  # clean RAISING ~8.0


def test_no_trigger_when_too_few_samples() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10)
    assert rule.detect(_window([10.0] * 5)) == []  # 5 < 10, süre koşulu sağlanmaz


def test_ignores_other_states_and_sensors() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10)
    assert rule.detect(_window([10.0] * 12, state="holding")) == []
    assert rule.detect(_window([10.0] * 12, sensor="vibration")) == []


def test_empty_window_returns_empty() -> None:
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_current_high.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.rules.motor_current_high'`

- [ ] **Step 3: Implement** — `src/detectors/rules/motor_current_high.py`

```python
"""MotorCurrentHigh: belirli state'te motor akımı pencere-ortalaması eşiği aşarsa anomali.

Spec § 6 (A, eşik+süre). Aktif state (raising) içinde motor_current'in pencere
ortalaması `threshold_a`'yı aşar VE en az `min_samples` örnek varsa (sürekli yük —
"süre" boyutu) tetikler. Eşik simülatör çıktısına kalibre: clean RAISING ort. ~8.0A,
MechanicalWear ~10.0A → 9.0A ayırma noktası.
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector

SENSOR = "motor_current"


class MotorCurrentHigh(Detector):
    """RAISING (config'lenebilir state) motor_current pencere-ortalaması eşiği aşarsa tetikler."""

    def __init__(
        self,
        state: str,
        threshold_a: float,
        min_samples: int,
        severity: str = "warning",
    ) -> None:
        """Args: state — aktif state ("raising"); threshold_a — akım eşiği (A);
        min_samples — minimum örnek (süre koşulu); severity — anomali şiddeti."""
        self._state = state
        self._threshold = threshold_a
        self._min_samples = min_samples
        self._severity = severity

    @property
    def name(self) -> str:
        return "motor_current_high"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[(window["sensor"] == SENSOR) & (window["state"] == self._state)]
        if len(rows) < self._min_samples:
            return []
        mean_a = float(rows["value"].mean())
        if mean_a <= self._threshold:
            return []
        score = min(1.0, (mean_a - self._threshold) / self._threshold)
        return [
            Anomaly(
                device_id=str(rows["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=str(rows["timestamp"].min()),
                window_end=str(rows["timestamp"].max()),
                value=mean_a,
                description=(
                    f"motor_current {self._state} ortalaması {mean_a:.2f}A "
                    f"eşik {self._threshold:.2f}A üstünde"
                ),
            )
        ]
```

- [ ] **Step 4: Registry'ye ekle + tip değiştir** — `src/detectors/rules/__init__.py` (TÜM dosyayı bununla değiştir)

```python
"""Kural registry: ad → Detector factory (Faz 4). build_detectors config-driven kurar."""
from __future__ import annotations

from collections.abc import Callable

from detectors.base import Detector
from detectors.rules.motor_current_high import MotorCurrentHigh
from detectors.rules.motor_temperature_high import MotorTemperatureHigh

# Callable[..., Detector]: kurallar farklı __init__ imzalı; build_detectors generic
# cls(severity=..., **params) çağırır → tip imza-agnostik olmalı (mypy-strict).
RULE_REGISTRY: dict[str, Callable[..., Detector]] = {
    "motor_temperature_high": MotorTemperatureHigh,
    "motor_current_high": MotorCurrentHigh,
}
```

- [ ] **Step 5: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_current_high.py -q`
Expected: PASS (6 passed)

- [ ] **Step 6: Lint**

Run: `.venv/bin/python -m mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors`
Expected: temiz

- [ ] **Step 7: Commit**

```bash
git add src/detectors/rules/motor_current_high.py src/detectors/rules/__init__.py tests/unit/detectors/test_motor_current_high.py
git commit -m "feat(detectors): MotorCurrentHigh kuralı + registry Callable tipi (Faz 4 Iter 4.2)"
```

---

## Task 2: VibrationElevated kuralı (oran, A)

**Files:**
- Create: `src/detectors/rules/vibration_elevated.py`
- Modify: `src/detectors/rules/__init__.py`
- Test: `tests/unit/detectors/test_vibration_elevated.py`

- [ ] **Step 1: Failing test** — `tests/unit/detectors/test_vibration_elevated.py`

```python
"""VibrationElevated birim testi (Faz 4 Iter 4.2, spec § 6 — A, oran)."""
from __future__ import annotations

import pandas as pd

from detectors.rules.vibration_elevated import VibrationElevated


def _window(values: list[float], state: str = "raising", sensor: str = "vibration") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:00:{i:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": [state] * len(values),
            "value": values,
        }
    )


def test_triggers_when_raising_mean_above_threshold() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10)
    anomalies = rule.detect(_window([0.45] * 12))  # MechanicalWear ~0.45
    assert len(anomalies) == 1
    assert anomalies[0].rule_name == "vibration_elevated"
    assert anomalies[0].sensor == "vibration"
    assert anomalies[0].value == 0.45
    assert anomalies[0].severity == "warning"


def test_no_trigger_when_below_threshold() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10)
    assert rule.detect(_window([0.30] * 12)) == []  # clean RAISING ~0.30


def test_no_trigger_too_few_samples() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10)
    assert rule.detect(_window([0.45] * 5)) == []


def test_ignores_other_states() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10)
    assert rule.detect(_window([0.45] * 12, state="holding")) == []


def test_empty_window_returns_empty() -> None:
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_vibration_elevated.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement** — `src/detectors/rules/vibration_elevated.py`

```python
"""VibrationElevated: belirli state'te titreşim pencere-ortalaması eşiği aşarsa anomali.

Spec § 6 (A, oran). Aktif state (raising) içinde vibration pencere ortalaması
`threshold_g`'yi aşar VE ≥ `min_samples` örnek varsa tetikler. Eşik state-baseline'a
relatif (clean RAISING ~0.30g, MechanicalWear ~0.45g → 0.37g ayırma; tek-örnek tepe
yerine ortalama, gürültü FP'sine karşı sağlam).
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector

SENSOR = "vibration"


class VibrationElevated(Detector):
    """RAISING (config'lenebilir) titreşim pencere-ortalaması eşiği aşarsa tetikler."""

    def __init__(
        self,
        state: str,
        threshold_g: float,
        min_samples: int,
        severity: str = "warning",
    ) -> None:
        """Args: state — aktif state; threshold_g — titreşim eşiği (g);
        min_samples — minimum örnek; severity — anomali şiddeti."""
        self._state = state
        self._threshold = threshold_g
        self._min_samples = min_samples
        self._severity = severity

    @property
    def name(self) -> str:
        return "vibration_elevated"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[(window["sensor"] == SENSOR) & (window["state"] == self._state)]
        if len(rows) < self._min_samples:
            return []
        mean_g = float(rows["value"].mean())
        if mean_g <= self._threshold:
            return []
        score = min(1.0, (mean_g - self._threshold) / self._threshold)
        return [
            Anomaly(
                device_id=str(rows["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=str(rows["timestamp"].min()),
                window_end=str(rows["timestamp"].max()),
                value=mean_g,
                description=(
                    f"vibration {self._state} ortalaması {mean_g:.3f}g "
                    f"eşik {self._threshold:.3f}g üstünde"
                ),
            )
        ]
```

- [ ] **Step 4: Registry'ye ekle** — `src/detectors/rules/__init__.py`

Add import `from detectors.rules.vibration_elevated import VibrationElevated` (alfabetik sıraya uy; ruff `--fix` ile düzelt) ve `RULE_REGISTRY`'ye satır:
```python
    "vibration_elevated": VibrationElevated,
```

- [ ] **Step 5: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_vibration_elevated.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Lint**

Run: `.venv/bin/python -m mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors`
Expected: temiz

- [ ] **Step 7: Commit**

```bash
git add src/detectors/rules/vibration_elevated.py src/detectors/rules/__init__.py tests/unit/detectors/test_vibration_elevated.py
git commit -m "feat(detectors): VibrationElevated kuralı (Faz 4 Iter 4.2)"
```

---

## Task 3: HydraulicPressureDecline kuralı (türev, B)

**Files:**
- Create: `src/detectors/rules/hydraulic_pressure_decline.py`
- Modify: `src/detectors/rules/__init__.py`
- Test: `tests/unit/detectors/test_hydraulic_pressure_decline.py`

- [ ] **Step 1: numpy bağımlılığını doğrula**

Run: `.venv/bin/python -c "import numpy; print(numpy.__version__)"`
Expected: bir sürüm yazdırır (numpy pandas ile gelir). Eğer `requirements.txt`'te explicit `numpy` yoksa ekle (pandas zaten çeker ama explicit kullanım için açık dep iyi):
Run: `grep -i numpy requirements.txt || echo "numpy>=1.26" >> requirements.txt`

- [ ] **Step 2: Failing test** — `tests/unit/detectors/test_hydraulic_pressure_decline.py`

```python
"""HydraulicPressureDecline birim testi (Faz 4 Iter 4.2, spec § 6 — B, türev)."""
from __future__ import annotations

import pandas as pd

from detectors.rules.hydraulic_pressure_decline import HydraulicPressureDecline


def _window(
    values: list[float],
    state: str = "holding",
    sensor: str = "hydraulic_pressure",
) -> pd.DataFrame:
    """1Hz timestamp'lerle pencere kurar (slope bar/dk için zaman ekseni gerekli)."""
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:{i // 60:02d}:{i % 60:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": [state] * len(values),
            "value": values,
        }
    )


def test_triggers_on_declining_pressure() -> None:
    # 80'den dakikada ~5 bar düşüş: 120 sn boyunca 80 → 70 (slope -5/dk).
    values = [80.0 - 5.0 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    anomalies = rule.detect(_window(values))
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_name == "hydraulic_pressure_decline"
    assert a.sensor == "hydraulic_pressure"
    assert a.value < -1.5  # slope bar/dk, negatif
    assert a.severity == "warning"


def test_no_trigger_on_flat_pressure() -> None:
    values = [80.0, 80.1, 79.9, 80.0, 80.2, 79.8, 80.0, 80.1, 79.9, 80.0, 80.0, 80.1]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    assert rule.detect(_window(values)) == []  # slope ~0 > -1.5


def test_no_trigger_on_mild_decline_above_threshold() -> None:
    # Dakikada 1 bar düşüş (slope -1.0) > -1.5 eşiği → tetiklemez.
    values = [80.0 - 1.0 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    assert rule.detect(_window(values)) == []


def test_no_trigger_too_few_samples() -> None:
    values = [80.0 - 5.0 * (i / 60.0) for i in range(5)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    assert rule.detect(_window(values)) == []


def test_ignores_other_states() -> None:
    values = [80.0 - 5.0 * (i / 60.0) for i in range(120)]
    rule = HydraulicPressureDecline(state="holding", slope_threshold_bar_per_min=1.5, min_samples=10)
    assert rule.detect(_window(values, state="raising")) == []
```

- [ ] **Step 3: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_hydraulic_pressure_decline.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement** — `src/detectors/rules/hydraulic_pressure_decline.py`

```python
"""HydraulicPressureDecline: HOLDING'de basınç eğimi (slope) negatif eşiği aşarsa anomali.

Spec § 6 (B, türev). HOLDING içinde hydraulic_pressure'ın zaman-eğimi (en küçük kareler
doğru uydurma, bar/dakika) `-slope_threshold_bar_per_min`'in altındaysa (daha dik düşüş)
ve ≥ `min_samples` örnek varsa tetikler. Kalibre: clean HOLDING slope ~-0.16 bar/dk,
HydraulicLeak ~-5.16 bar/dk → -1.5 ayırma. Pencere poll'da ≤ tek HOLDING epizodu olur
(window_s=60 < holding süresi) → epizod-içi tek eğim.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from detectors.base import Anomaly, Detector

SENSOR = "hydraulic_pressure"


class HydraulicPressureDecline(Detector):
    """HOLDING (config'lenebilir) basınç eğimi negatif eşiği aşarsa tetikler."""

    def __init__(
        self,
        state: str,
        slope_threshold_bar_per_min: float,
        min_samples: int,
        severity: str = "warning",
    ) -> None:
        """Args: state — aktif state ("holding"); slope_threshold_bar_per_min — pozitif
        eşik (slope < -bu değer → anomali); min_samples — eğim için min örnek; severity."""
        self._state = state
        self._threshold = slope_threshold_bar_per_min
        self._min_samples = min_samples
        self._severity = severity

    @property
    def name(self) -> str:
        return "hydraulic_pressure_decline"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[(window["sensor"] == SENSOR) & (window["state"] == self._state)]
        if len(rows) < self._min_samples:
            return []
        rows = rows.sort_values("timestamp")
        t = pd.to_datetime(rows["timestamp"], format="ISO8601", utc=True)
        x = (t - t.iloc[0]).dt.total_seconds().to_numpy()
        if x[-1] == x[0]:  # sıfır zaman aralığı (tüm örnekler aynı an) → eğim tanımsız
            return []
        y = rows["value"].to_numpy()
        slope_per_min = float(np.polyfit(x, y, 1)[0]) * 60.0
        if slope_per_min >= -self._threshold:
            return []
        score = min(1.0, (-slope_per_min) / (self._threshold * 4.0))
        return [
            Anomaly(
                device_id=str(rows["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=str(rows["timestamp"].min()),
                window_end=str(rows["timestamp"].max()),
                value=slope_per_min,
                description=(
                    f"hydraulic_pressure {self._state} eğimi {slope_per_min:.2f} bar/dk "
                    f"(eşik -{self._threshold:.2f})"
                ),
            )
        ]
```

- [ ] **Step 5: Registry'ye ekle** — `src/detectors/rules/__init__.py`

Import `from detectors.rules.hydraulic_pressure_decline import HydraulicPressureDecline` + `RULE_REGISTRY`'ye:
```python
    "hydraulic_pressure_decline": HydraulicPressureDecline,
```

- [ ] **Step 6: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_hydraulic_pressure_decline.py -q`
Expected: PASS (5 passed)

- [ ] **Step 7: Lint**

Run: `.venv/bin/python -m mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors`
Expected: temiz. (numpy 1.26.4 `py.typed` ile gelir → mypy-strict override GEREKMEZ; plan-review ile doğrulandı.)

- [ ] **Step 8: Commit**

```bash
git add src/detectors/rules/hydraulic_pressure_decline.py src/detectors/rules/__init__.py tests/unit/detectors/test_hydraulic_pressure_decline.py requirements.txt
git commit -m "feat(detectors): HydraulicPressureDecline kuralı (slope, Faz 4 Iter 4.2)"
```

---

## Task 4: MotorVoltageErratic kuralı (varyans, C)

**Files:**
- Create: `src/detectors/rules/motor_voltage_erratic.py`
- Modify: `src/detectors/rules/__init__.py`
- Test: `tests/unit/detectors/test_motor_voltage_erratic.py`

- [ ] **Step 1: Failing test** — `tests/unit/detectors/test_motor_voltage_erratic.py`

```python
"""MotorVoltageErratic birim testi (Faz 4 Iter 4.2, spec § 6 — C, varyans)."""
from __future__ import annotations

import pandas as pd

from detectors.rules.motor_voltage_erratic import MotorVoltageErratic


def _window(values: list[float], sensor: str = "motor_voltage") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:00:{i:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": ["holding"] * len(values),
            "value": values,
        }
    )


def test_triggers_on_high_variance() -> None:
    # ElectricalFault: spike'lar + jitter → yüksek std. 24 etrafında ±20 salınım.
    values = [24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    anomalies = rule.detect(_window(values))
    assert len(anomalies) == 1
    assert anomalies[0].rule_name == "motor_voltage_erratic"
    assert anomalies[0].sensor == "motor_voltage"
    assert anomalies[0].value > 1.0  # std
    assert anomalies[0].severity == "warning"


def test_no_trigger_on_stable_voltage() -> None:
    # Clean: 24V ± 0.2 gürültü → std ~0.2 < 1.0.
    values = [24.0, 24.2, 23.8, 24.1, 23.9, 24.0, 24.2, 23.8, 24.1, 23.9, 24.0, 24.1]
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert rule.detect(_window(values)) == []


def test_no_trigger_too_few_samples() -> None:
    values = [24.0, 4.0, 44.0, 24.0, -3.0]
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert rule.detect(_window(values)) == []


def test_ignores_other_sensors() -> None:
    values = [24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert rule.detect(_window(values, sensor="motor_current")) == []


def test_empty_window_returns_empty() -> None:
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_voltage_erratic.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement** — `src/detectors/rules/motor_voltage_erratic.py`

```python
"""MotorVoltageErratic: motor_voltage pencere standart sapması eşiği aşarsa anomali.

Spec § 6 (C, varyans). State-agnostik (ElectricalFault tüm state'lerde aktif).
Pencere içindeki motor_voltage örneklerinin std'si `std_threshold_v`'yi aşar VE
≥ `min_samples` örnek varsa tetikler. Kalibre: clean std ~0.2V, ElectricalFault
~4.0V → 1.0V ayırma (geniş marj).
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector

SENSOR = "motor_voltage"


class MotorVoltageErratic(Detector):
    """motor_voltage pencere std'si eşiği aşarsa tetikler (state filtresi YOK)."""

    def __init__(
        self,
        std_threshold_v: float,
        min_samples: int,
        severity: str = "warning",
    ) -> None:
        """Args: std_threshold_v — std eşiği (V); min_samples — min örnek; severity."""
        self._threshold = std_threshold_v
        self._min_samples = min_samples
        self._severity = severity

    @property
    def name(self) -> str:
        return "motor_voltage_erratic"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[window["sensor"] == SENSOR]
        if len(rows) < self._min_samples:
            return []
        std_v = float(rows["value"].std())  # pandas ddof=1
        if std_v <= self._threshold:
            return []
        score = min(1.0, (std_v - self._threshold) / (self._threshold * 5.0))
        return [
            Anomaly(
                device_id=str(rows["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=SENSOR,
                severity=self._severity,
                score=score,
                window_start=str(rows["timestamp"].min()),
                window_end=str(rows["timestamp"].max()),
                value=std_v,
                description=f"motor_voltage std {std_v:.2f}V eşik {self._threshold:.2f}V üstünde",
            )
        ]
```

- [ ] **Step 4: Registry'ye ekle** — `src/detectors/rules/__init__.py`

Import `from detectors.rules.motor_voltage_erratic import MotorVoltageErratic` + `RULE_REGISTRY`'ye:
```python
    "motor_voltage_erratic": MotorVoltageErratic,
```

- [ ] **Step 5: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_voltage_erratic.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Lint + Commit**

```bash
.venv/bin/python -m mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors
git add src/detectors/rules/motor_voltage_erratic.py src/detectors/rules/__init__.py tests/unit/detectors/test_motor_voltage_erratic.py
git commit -m "feat(detectors): MotorVoltageErratic kuralı (varyans, Faz 4 Iter 4.2)"
```

---

## Task 5: SensorFrozen kuralı (süre, E-universal)

**Files:**
- Create: `src/detectors/rules/sensor_frozen.py`
- Modify: `src/detectors/rules/__init__.py`
- Test: `tests/unit/detectors/test_sensor_frozen.py`

- [ ] **Step 1: Failing test** — `tests/unit/detectors/test_sensor_frozen.py`

```python
"""SensorFrozen birim testi (Faz 4 Iter 4.2, spec § 6 — E universal, süre).

Simülatör donmuş sensör üretmez → yalnız sentetik birim test ile doğrulanır.
"""
from __future__ import annotations

import pandas as pd

from detectors.rules.sensor_frozen import SensorFrozen


def _window(values: list[float], sensor: str = "motor_voltage") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:00:{i:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": ["holding"] * len(values),
            "value": values,
        }
    )


def test_triggers_when_value_frozen() -> None:
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    anomalies = rule.detect(_window([24.0] * 20))  # son 20 örnek aynı → donmuş
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_name == "sensor_frozen"
    assert a.sensor == "motor_voltage"
    assert a.value == 24.0  # donmuş değer
    assert a.severity == "warning"


def test_no_trigger_when_varying() -> None:
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    values = [24.0 + (i % 2) * 0.2 for i in range(20)]  # gürültülü → aralık 0.2 > ε
    assert rule.detect(_window(values)) == []


def test_uses_only_last_min_samples() -> None:
    # İlk örnekler değişken ama SON 20 sabit → donmuş (kayan pencere kuyruğu).
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    values = [20.0, 21.0, 22.0] + [24.0] * 20
    assert len(rule.detect(_window(values))) == 1


def test_no_trigger_too_few_samples() -> None:
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    assert rule.detect(_window([24.0] * 10)) == []


def test_ignores_other_sensors() -> None:
    rule = SensorFrozen(sensor="motor_voltage", min_samples=20, epsilon=0.01)
    assert rule.detect(_window([24.0] * 20, sensor="motor_current")) == []
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_sensor_frozen.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement** — `src/detectors/rules/sensor_frozen.py`

```python
"""SensorFrozen: bir sensör son N örnekte (neredeyse) sabit kalırsa donmuş-sensör anomalisi.

Spec § 6 (E universal, süre). Konfigüre edilen sensörün en yeni `min_samples` örneğinin
değer aralığı (max - min) `epsilon`'u aşmıyorsa "donmuş" kabul edilir. Simülatör donmuş
sensör üretmediğinden (her sensör gauss gürültülü) yalnız birim test ile doğrulanır;
gerçek gürültülü veride asla tetiklenmez (FP güvenli).
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector


class SensorFrozen(Detector):
    """Konfigüre edilen sensör son `min_samples` örnekte sabitse tetikler."""

    def __init__(
        self,
        sensor: str,
        min_samples: int,
        epsilon: float,
        severity: str = "warning",
    ) -> None:
        """Args: sensor — izlenen sensör adı; min_samples — kuyruk penceresi boyutu;
        epsilon — "sabit" toleransı (max-min ≤ ε → donmuş); severity."""
        self._sensor = sensor
        self._min_samples = min_samples
        self._epsilon = epsilon
        self._severity = severity

    @property
    def name(self) -> str:
        return "sensor_frozen"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        rows = window[window["sensor"] == self._sensor]
        if len(rows) < self._min_samples:
            return []
        recent = rows.sort_values("timestamp").tail(self._min_samples)
        spread = float(recent["value"].max() - recent["value"].min())
        if spread > self._epsilon:
            return []
        frozen_value = float(recent["value"].iloc[-1])
        return [
            Anomaly(
                device_id=str(recent["device_id"].iloc[0]),
                rule_name=self.name,
                sensor=self._sensor,
                severity=self._severity,
                score=1.0,
                window_start=str(recent["timestamp"].min()),
                window_end=str(recent["timestamp"].max()),
                value=frozen_value,
                description=(
                    f"{self._sensor} son {self._min_samples} örnekte donmuş "
                    f"(aralık {spread:.4f} ≤ {self._epsilon})"
                ),
            )
        ]
```

- [ ] **Step 4: Registry'ye ekle** — `src/detectors/rules/__init__.py`

Import `from detectors.rules.sensor_frozen import SensorFrozen` + `RULE_REGISTRY`'ye:
```python
    "sensor_frozen": SensorFrozen,
```

- [ ] **Step 5: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_sensor_frozen.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Lint + Commit**

```bash
.venv/bin/python -m mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors
git add src/detectors/rules/sensor_frozen.py src/detectors/rules/__init__.py tests/unit/detectors/test_sensor_frozen.py
git commit -m "feat(detectors): SensorFrozen kuralı (süre/universal, Faz 4 Iter 4.2)"
```

---

## Task 6: MotorTemperatureHigh'a config-driven severity (geriye-uyumlu)

**Files:**
- Modify: `src/detectors/rules/motor_temperature_high.py`
- Test: `tests/unit/detectors/test_motor_temperature_high.py` (mevcut — bir test ekle)

- [ ] **Step 1: Mevcut testi oku ve yeni test ekle**

`tests/unit/detectors/test_motor_temperature_high.py` sonuna ekle (mevcut testler `severity == "critical"` default'unu zaten doğruluyor; bu yeni test config-driven severity'yi doğrular):
```python
def test_severity_is_configurable() -> None:
    """severity constructor ile override edilebilir (config-driven, spec § 5)."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0, severity="warning")
    window = pd.DataFrame(
        {
            "device_id": ["device_001"],
            "timestamp": ["2026-05-30T00:00:00.000Z"],
            "sensor": ["motor_temperature"],
            "state": ["holding"],
            "value": [95.0],
        }
    )
    assert rule.detect(window)[0].severity == "warning"
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_temperature_high.py::test_severity_is_configurable -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'severity'`

- [ ] **Step 3: `MotorTemperatureHigh`'a severity param ekle**

`src/detectors/rules/motor_temperature_high.py` — `__init__` ve `detect`'i güncelle (geriye-uyumlu default `"critical"`):

`__init__` değiştir:
```python
    def __init__(self, critical_threshold_c: float, severity: str = "critical") -> None:
        """Args: critical_threshold_c — kritik sıcaklık eşiği (°C). value > eşik → anomali.
        severity — anomali şiddeti (config-driven, default critical)."""
        self._threshold = critical_threshold_c
        self._severity = severity
```

`detect` içindeki `severity="critical",` satırını değiştir:
```python
                severity=self._severity,
```

- [ ] **Step 4: Run, confirm PASS (yeni + mevcut testler)**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_motor_temperature_high.py -q`
Expected: PASS (7 passed — 6 mevcut + 1 yeni; mevcut testler default critical ile geçer)

- [ ] **Step 5: Lint + Commit**

```bash
.venv/bin/python -m mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors
git add src/detectors/rules/motor_temperature_high.py tests/unit/detectors/test_motor_temperature_high.py
git commit -m "feat(detectors): MotorTemperatureHigh config-driven severity (Faz 4 Iter 4.2)"
```

---

## Task 7: Detector config loader + build_detectors + detectors.yaml.example

**Files:**
- Create: `src/detectors/config.py`
- Modify: `config/detectors.yaml.example` (REWRITE)
- Test: `tests/unit/detectors/test_config.py`

- [ ] **Step 1: detectors.yaml.example REWRITE** — `config/detectors.yaml.example` (TÜM içeriği değiştir)

```yaml
# Kural tabanlı dedektör yapılandırması (Faz 4 Iter 4.2).
# Gerçek config/detectors.yaml dosyasını bu örnekten oluşturun.
# Eşikler simülatör çıktısına KALİBRE edilmiştir (per-state fiziksel ölçek).
detectors:
  poll_interval_s: 5.0
  window_s: 60
  rules:
    - name: motor_temperature_high
      enabled: true
      severity: critical
      params:
        critical_threshold_c: 80.0

    - name: motor_current_high
      enabled: true
      severity: high
      params:
        state: raising
        threshold_a: 9.0
        min_samples: 10

    - name: vibration_elevated
      enabled: true
      severity: warning
      params:
        state: raising
        threshold_g: 0.37
        min_samples: 10

    - name: hydraulic_pressure_decline
      enabled: true
      severity: warning
      params:
        state: holding
        slope_threshold_bar_per_min: 1.5
        min_samples: 10

    - name: motor_voltage_erratic
      enabled: true
      severity: warning
      params:
        std_threshold_v: 1.0
        min_samples: 10

    - name: sensor_frozen
      enabled: true
      severity: warning
      params:
        sensor: motor_voltage
        min_samples: 20
        epsilon: 0.01
```

- [ ] **Step 2: Failing test** — `tests/unit/detectors/test_config.py`

```python
"""detectors.config: YAML loader + build_detectors (Faz 4 Iter 4.2, spec § 3/§ 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from detectors.config import (
    DetectorConfig,
    RuleConfig,
    build_detectors,
    load_detector_config,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


_VALID = """
detectors:
  poll_interval_s: 5.0
  window_s: 60
  rules:
    - name: motor_temperature_high
      enabled: true
      severity: critical
      params:
        critical_threshold_c: 80.0
    - name: motor_current_high
      enabled: false
      severity: high
      params:
        state: raising
        threshold_a: 9.0
        min_samples: 10
"""


def test_load_parses_detectors_block(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID))
    assert isinstance(cfg, DetectorConfig)
    assert cfg.poll_interval_s == 5.0
    assert cfg.window_s == 60
    assert len(cfg.rules) == 2
    assert cfg.rules[0] == RuleConfig(
        name="motor_temperature_high", severity="critical", enabled=True,
        params={"critical_threshold_c": 80.0},
    )
    assert cfg.rules[1].enabled is False


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_detector_config(tmp_path / "yok.yaml")


def test_load_missing_key_raises_valueerror(tmp_path: Path) -> None:
    bad = "detectors:\n  window_s: 60\n  rules: []\n"  # poll_interval_s yok
    with pytest.raises(ValueError):
        load_detector_config(_write(tmp_path / "bad.yaml", bad))


def test_build_detectors_skips_disabled(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID))
    detectors = build_detectors(cfg)
    # motor_current_high enabled:false → sadece motor_temperature_high kurulur.
    assert [d.name for d in detectors] == ["motor_temperature_high"]


def test_build_detectors_constructs_with_params_and_severity(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID.replace("enabled: false", "enabled: true")))
    detectors = build_detectors(cfg)
    names = {d.name for d in detectors}
    assert names == {"motor_temperature_high", "motor_current_high"}


def test_build_detectors_unknown_rule_raises(tmp_path: Path) -> None:
    bad = (
        "detectors:\n  poll_interval_s: 5.0\n  window_s: 60\n  rules:\n"
        "    - name: nonexistent_rule\n      enabled: true\n      severity: warning\n      params: {}\n"
    )
    cfg = load_detector_config(_write(tmp_path / "bad.yaml", bad))
    with pytest.raises(ValueError, match="bilinmeyen kural"):
        build_detectors(cfg)


def test_build_detectors_bad_params_raises(tmp_path: Path) -> None:
    bad = (
        "detectors:\n  poll_interval_s: 5.0\n  window_s: 60\n  rules:\n"
        "    - name: motor_current_high\n      enabled: true\n      severity: high\n"
        "      params:\n        wrong_param: 1\n"
    )
    cfg = load_detector_config(_write(tmp_path / "bad.yaml", bad))
    with pytest.raises(ValueError, match="parametre"):
        build_detectors(cfg)


def test_example_file_loads_and_builds_all_six() -> None:
    """config/detectors.yaml.example geçerli ve 6 kuralı kurar (kalibrasyon dosyası canlı)."""
    cfg = load_detector_config(Path("config/detectors.yaml.example"))
    detectors = build_detectors(cfg)
    assert {d.name for d in detectors} == {
        "motor_temperature_high",
        "motor_current_high",
        "vibration_elevated",
        "hydraulic_pressure_decline",
        "motor_voltage_erratic",
        "sensor_frozen",
    }
```

- [ ] **Step 3: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.config'`

- [ ] **Step 4: Implement** — `src/detectors/config.py`

```python
"""detectors.yaml loader + config-driven dedektör kurulumu (Faz 4 Iter 4.2, spec § 3/§ 4).

ingestion.config deseni: dataclass'lar + YAML loader (FileNotFoundError/ValueError).
build_detectors RULE_REGISTRY'den her aktif kuralı `severity` + `params` ile kurar.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from detectors.base import Detector
from detectors.rules import RULE_REGISTRY


@dataclass(frozen=True)
class RuleConfig:
    """detectors.yaml'daki tek kural girişi."""

    name: str
    severity: str
    enabled: bool
    params: dict[str, Any]


@dataclass(frozen=True)
class DetectorConfig:
    """detectors.yaml `detectors` bloğu."""

    poll_interval_s: float
    window_s: int
    rules: tuple[RuleConfig, ...]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"detectors.yaml dosyası bulunamadı: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"detectors config geçersiz ({path}): YAML parse hatası: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(
            f"detectors config geçersiz ({path}): kök sözlük olmalı, "
            f"alınan {type(data).__name__}"
        )
    return data


def load_detector_config(path: Path) -> DetectorConfig:
    """detectors.yaml dosyasından DetectorConfig döndürür.

    Args:
        path: detectors.yaml yolu.

    Returns:
        DetectorConfig.

    Raises:
        FileNotFoundError: Dosya yoksa.
        ValueError: YAML bozuksa veya şema geçersizse.
    """
    data = _read_yaml(path)
    try:
        det = data["detectors"]
        rules = tuple(
            RuleConfig(
                name=str(r["name"]),
                severity=str(r.get("severity", "warning")),
                enabled=bool(r.get("enabled", True)),
                params=dict(r.get("params") or {}),
            )
            for r in det["rules"]
        )
        return DetectorConfig(
            poll_interval_s=float(det["poll_interval_s"]),
            window_s=int(det["window_s"]),
            rules=rules,
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"detectors config geçersiz ({path}): {e}") from e


def build_detectors(config: DetectorConfig) -> list[Detector]:
    """Config'ten aktif (enabled) kuralları RULE_REGISTRY üzerinden kurar.

    Her kural `RULE_REGISTRY[name](severity=..., **params)` ile inşa edilir.

    Args:
        config: DetectorConfig.

    Returns:
        Kurulu Detector listesi (config sırasını korur, disabled atlanır).

    Raises:
        ValueError: Bilinmeyen kural adı veya geçersiz params.
    """
    detectors: list[Detector] = []
    for rc in config.rules:
        if not rc.enabled:
            continue
        factory = RULE_REGISTRY.get(rc.name)
        if factory is None:
            raise ValueError(f"detectors config: bilinmeyen kural '{rc.name}' (registry'de yok)")
        try:
            detectors.append(factory(severity=rc.severity, **rc.params))
        except TypeError as e:
            raise ValueError(
                f"detectors config: kural '{rc.name}' parametre hatası: {e}"
            ) from e
    return detectors
```

- [ ] **Step 5: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_config.py -q`
Expected: PASS (8 passed)

- [ ] **Step 6: Lint + Commit**

```bash
.venv/bin/python -m mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors
git add src/detectors/config.py config/detectors.yaml.example tests/unit/detectors/test_config.py
git commit -m "feat(detectors): detectors.yaml loader + build_detectors + kalibre örnek config (Faz 4 Iter 4.2)"
```

---

## Task 8: service.run() config-driven dedektör kurulumu

**Files:**
- Modify: `src/detectors/service.py`
- Test: `tests/integration/test_detector_config_driven.py`

- [ ] **Step 1: Failing test** — `tests/integration/test_detector_config_driven.py`

Bu dosyada İKİ test var: (a) `test_run_signature_is_config_driven` — `run()`'ın yeni config-driven imzasını doğrular ve Step 3'ten ÖNCE GERÇEKTEN FAIL eder (eski `run()` `poll_interval_s`/`window_s`/`motor_temp_threshold_c` taşır); bu, refactor'u süren kırmızı testtir. (b) `test_config_driven_detectors_persist_anomalies` — config→build→detect→persist zincirini doğrular (destekleyici integration; `run()`'ı çağırmaz çünkü poll loop pragma-no-cover).

```python
"""Integration: detectors.yaml → build_detectors → _detect_once → anomalies (Faz 4 Iter 4.2).

run() (poll loop + signal) pragma-no-cover; config→dedektör→tespit→persist yolu run()
olmadan doğrulanır. Ayrı bir imza testi run()'ın config-driven imzaya geçtiğini garanti eder.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

from detectors.config import build_detectors, load_detector_config
from detectors.service import _detect_once, run
from ingestion.message_parser import IngestedReading
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository


def test_run_signature_is_config_driven() -> None:
    """run() config-driven imzaya geçti: yalnız iki config yolu parametresi (Iter 4.2).

    Step 3'ten ÖNCE FAIL eder (eski imza poll_interval_s/window_s/motor_temp_threshold_c
    içerir) — bu testi yeşile çeviren tek şey run() refactor'udur.
    """
    params = set(inspect.signature(run).parameters)
    assert params == {"ingestion_config_path", "detectors_config_path"}


_CONFIG = """
detectors:
  poll_interval_s: 5.0
  window_s: 1000000000
  rules:
    - name: motor_temperature_high
      enabled: true
      severity: critical
      params:
        critical_threshold_c: 80.0
    - name: motor_voltage_erratic
      enabled: true
      severity: warning
      params:
        std_threshold_v: 1.0
        min_samples: 10
"""


def _reading(sensor: str, ts: str, value: float, state: str = "holding") -> IngestedReading:
    return IngestedReading(
        device_id="device_001", sensor=sensor, timestamp=ts, state=state, value=value, unit="x"
    )


def test_config_driven_detectors_persist_anomalies(tmp_path: Path) -> None:
    cfg_path = tmp_path / "detectors.yaml"
    cfg_path.write_text(_CONFIG, encoding="utf-8")
    db_path = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        # Eşik-üstü sıcaklık (temp_high tetikler) + erratik voltaj (voltage_erratic tetikler).
        repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
        for i, v in enumerate([24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]):
            repo.insert(_reading("motor_voltage", f"2026-05-30T00:01:{i:02d}.000Z", v))

        config = load_detector_config(cfg_path)
        detectors = build_detectors(config)
        seen: set[tuple[str, str, str]] = set()
        _detect_once(repo, detectors, config.window_s, seen, datetime(2026, 5, 30, 1, 0, 0, tzinfo=UTC))

        stored = repo.fetch_recent_anomalies(limit=10)
        rules = {a.rule_name for a in stored}
        assert "motor_temperature_high" in rules
        assert "motor_voltage_erratic" in rules
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/integration/test_detector_config_driven.py -q`
Expected: `test_run_signature_is_config_driven` FAIL eder (eski `run()` imzası fazladan parametre taşır → set eşleşmez). `test_config_driven_detectors_persist_anomalies` zaten PASS eder (build_detectors + _detect_once mevcut; bu destekleyici integration). Kırmızı sürücü imza testidir.

- [ ] **Step 3: `service.run()`'ı config-driven yap** — `src/detectors/service.py`

Importları güncelle: `MotorTemperatureHigh` importunu KALDIR, ekle:
```python
from detectors.config import build_detectors, load_detector_config
```
(Mevcut `from detectors.base import Anomaly, Detector` kalır; `from detectors.rules.motor_temperature_high import MotorTemperatureHigh` SİLİNİR.)

`run()` imzasını ve gövdesini değiştir (poll/window/threshold artık config'ten):
```python
def run(
    ingestion_config_path: Path = Path("config/ingestion.yaml"),
    detectors_config_path: Path = Path("config/detectors.yaml"),
) -> None:  # pragma: no cover
    """Detector servisini başlat. SIGINT/SIGTERM gelene kadar bloklar.

    db_path ingestion.yaml'dan (paylaşılan telemetry.db); poll_interval_s, window_s ve
    kural seti detectors.yaml'dan (config-driven, Iter 4.2). Gözlem modu: yalnız telemetry
    okur, yalnız anomalies yazar.

    Args:
        ingestion_config_path: db_path için ingestion.yaml yolu.
        detectors_config_path: kural seti + poll/window için detectors.yaml yolu.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: Config geçersizse.
    """
    ingestion_config = load_ingestion_config(ingestion_config_path)
    detector_config = load_detector_config(detectors_config_path)
    logger.remove()
    logger.add(sys.stderr, level=ingestion_config.log_level)

    engine = create_sqlite_engine(ingestion_config.db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repository = TelemetryRepository(engine)
        detectors: list[Detector] = build_detectors(detector_config)
        seen: set[tuple[str, str, str]] = set()

        shutdown = threading.Event()

        def _on_signal(signum: int, _frame: FrameType | None) -> None:
            logger.info("Shutdown sinyali alındı: {}", signum)
            shutdown.set()

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        logger.info(
            "Detector servisi başladı: poll={}s window={}s kurallar={}",
            detector_config.poll_interval_s,
            detector_config.window_s,
            [d.name for d in detectors],
        )
        while not shutdown.is_set():
            try:
                _detect_once(
                    repository, detectors, detector_config.window_s, seen, datetime.now(UTC)
                )
            except OperationalError as e:
                logger.error("Poll turu DB hatası (devam): {}", e)
            shutdown.wait(detector_config.poll_interval_s)
    finally:
        engine.dispose()
        logger.info("Detector servisi temiz kapandı")
```

(NOT: `_detect_once`, `build_window`, `_since_cutoff`, `SENSORS` DEĞİŞMEZ. `__main__.py` DEĞİŞMEZ — `run()` default'ları yeni imzayla uyumlu.)

- [ ] **Step 4: Run integration + full suite**

Run: `.venv/bin/python -m pytest tests/integration/test_detector_config_driven.py tests/unit/detectors/ -q`
Expected: PASS. Sonra tam suite:
Run: `.venv/bin/python -m pytest -q`
Expected: tüm önceki + yeni testler PASS (1 smoke skipped). Iter 4.1 `test_service_build_window.py` / `test_service_detect_once.py` / `test_detector_persistence.py` hâlâ geçer (MotorTemperatureHigh'ı direkt kurarlar, run() değişiminden etkilenmez).

- [ ] **Step 5: Lint + Commit**

```bash
.venv/bin/python -m mypy src/detectors tests/unit tests/integration && ruff check src/detectors tests/integration/test_detector_config_driven.py
git add src/detectors/service.py tests/integration/test_detector_config_driven.py
git commit -m "feat(detectors): service.run() config-driven kural kurulumu (Faz 4 Iter 4.2)"
```

---

## Task 9: A/B/C + clean imza testleri (acceptance gate)

**Files:**
- Create: `tests/fixtures/devices_clean_baseline.yaml`
- Modify: `tests/scenarios/conftest.py` (harness helper ekle)
- Test: `tests/scenarios/test_rule_signatures.py`

- [ ] **Step 1: Clean fixture** — `tests/fixtures/devices_clean_baseline.yaml`

```yaml
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [1, 1]
      raising:  [60, 60]
      holding:  [120, 120]
      lowering: [1, 1]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios: []
```

- [ ] **Step 2: Harness helper** — `tests/scenarios/conftest.py` sonuna ekle

```python
def build_detector_window(
    monkeypatch: "pytest.MonkeyPatch",
    clock: "CountingClock",
    devices_path: Path,
    max_iterations: int,
) -> "pd.DataFrame":
    """Engine'i fixture ile koşturup dedektör-hazır uzun-format pencere döndürür.

    Publisher timestamp üretmediğinden (publish anında kendi üretir), collected
    reading'lere PER-SENSÖR monoton 1sn timestamp atanır (slope bar/dk doğru çıksın).
    state DeviceState StrEnum value'suna ("raising" vb.) çevrilir.

    Args:
        monkeypatch: pytest monkeypatch (publisher mock için).
        clock: patched_engine_clock fixture'ından CountingClock.
        devices_path: fixture device YAML yolu.
        max_iterations: engine tick sayısı.

    Returns:
        [device_id, timestamp, sensor, state, value] kolonlu pencere.
    """
    from collections import defaultdict
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    import pandas as pd

    from simulator.config import DeviceState
    from simulator.engine import run

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=devices_path,
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=max_iterations,
        seed=None,
        clock=clock,
    )

    base = datetime(2026, 5, 30, 0, 0, 0, tzinfo=UTC)
    counters: dict[tuple[str, str], int] = defaultdict(int)
    records: list[dict[str, object]] = []
    for c in mock_publisher.publish_reading.call_args_list:
        device_id = c.kwargs["device_id"]
        sensor = c.kwargs["sensor"]
        state = c.kwargs["state"]
        state_str = state.value if isinstance(state, DeviceState) else str(state)
        k = counters[(device_id, sensor)]
        counters[(device_id, sensor)] += 1
        ts = (base + timedelta(seconds=k)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        records.append(
            {
                "device_id": device_id,
                "timestamp": ts,
                "sensor": sensor,
                "state": state_str,
                "value": c.kwargs["value"],
            }
        )
    return pd.DataFrame(records, columns=["device_id", "timestamp", "sensor", "state", "value"])
```

(NOT: `conftest.py` zaten `from pathlib import Path`, `import asyncio`, `import pytest`, `FIXTURES`, `CountingClock` içerir. `pandas`/`pytest` tip-only string anotasyonları runtime import gerektirmez; helper içi importlar local.)

- [ ] **Step 3: Failing imza testleri** — `tests/scenarios/test_rule_signatures.py`

```python
"""A/B/C + clean dedektör imza testleri (Faz 4 Iter 4.2, spec § 9, kabul kriteri 1 + 4).

Engine harness fixture senaryosunu koşturur → uzun-format pencere → dedektör çalıştırır:
- Arıza penceresinde ilgili kural TETİKLENİR.
- Clean (senaryosuz) pencerede HİÇBİR kural tetiklenmez (FP yok).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from detectors.config import build_detectors, load_detector_config
from detectors.rules.hydraulic_pressure_decline import HydraulicPressureDecline
from detectors.rules.motor_current_high import MotorCurrentHigh
from detectors.rules.motor_voltage_erratic import MotorVoltageErratic
from detectors.rules.vibration_elevated import VibrationElevated
from tests.scenarios.conftest import FIXTURES, CountingClock, build_detector_window


def test_mechanical_wear_triggers_motor_current_high(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """MechanicalWear penceresi motor_current_high'ı tetikler (RAISING ort. > 9.0A)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_mechanical_wear.yaml", max_iterations=200,
    )
    rule = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10)
    assert len(rule.detect(window)) == 1


def test_mechanical_wear_triggers_vibration_elevated(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """MechanicalWear penceresi vibration_elevated'ı tetikler (RAISING ort. > 0.37g)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_mechanical_wear.yaml", max_iterations=200,
    )
    rule = VibrationElevated(state="raising", threshold_g=0.37, min_samples=10)
    assert len(rule.detect(window)) == 1


def test_hydraulic_leak_triggers_pressure_decline(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """HydraulicLeak penceresi hydraulic_pressure_decline'ı tetikler (slope < -1.5 bar/dk).

    max_iterations=120 → tek HOLDING epizodu (idle1 + raising1 + holding~118), epizod-içi
    tek eğim (poll'daki window_s < holding süresi davranışını taklit eder).
    """
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_hydraulic_leak.yaml", max_iterations=120,
    )
    rule = HydraulicPressureDecline(
        state="holding", slope_threshold_bar_per_min=1.5, min_samples=10
    )
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    assert anomalies[0].value < -1.5  # slope bar/dk


def test_electrical_fault_triggers_voltage_erratic(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """ElectricalFault penceresi motor_voltage_erratic'i tetikler (std > 1.0V)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_electrical_fault.yaml", max_iterations=200,
    )
    rule = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert len(rule.detect(window)) == 1


def test_clean_baseline_triggers_no_rules(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """Senaryosuz clean pencere: TÜM kalibre kural seti HİÇBİR anomali üretmez (FP yok).

    max_iterations=181 → idle1 + raising60 + holding120 (tek epizod), her kuralın
    değerlendirme koşulu sağlanır (≥10 RAISING + ≥10 HOLDING örnek) ama tetiklenmez.
    """
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_clean_baseline.yaml", max_iterations=181,
    )
    detectors = build_detectors(load_detector_config(Path("config/detectors.yaml.example")))
    triggered = [a.rule_name for d in detectors for a in d.detect(window)]
    assert triggered == [], f"Clean veride beklenmeyen tetik: {triggered}"
```

- [ ] **Step 4: Run, confirm FAIL then iterate**

Run: `.venv/bin/python -m pytest tests/scenarios/test_rule_signatures.py -q`
Expected (ilk): bazıları FAIL olabilir (harness import / pencere kurulumu). Hata varsa düzelt. **Hedef davranış:** 4 arıza testi tetiklenmeyi, clean testi sıfır-tetiği doğrular.

> **Eğer clean testte beklenmeyen tetik çıkarsa:** ilgili sensörün clean dağılımını yazdırıp (örn. `print(window[window["sensor"]=="vibration"]["value"].describe())`) eşiğin clean üstünde kaldığını teyit et. Kalibrasyon ölçümleri (plan başı) bu eşiklerin clean-fault arasında olduğunu gösteriyor; tetik çıkarsa fixture/iteration sayısını gözden geçir (clean fixture seed 42 ile ölçümlerle aynı olmalı). **Eşikleri gevşetmek için clean testi ZAYIFLATMA** — kök nedeni bul.

- [ ] **Step 5: Run full suite + mypy + ruff (iterasyon kapanış gate'i)**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios
```
Expected: tüm testler PASS (1 smoke skipped), mypy temiz, ruff temiz.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/devices_clean_baseline.yaml tests/scenarios/conftest.py tests/scenarios/test_rule_signatures.py
git commit -m "test(detectors): A/B/C + clean imza testleri (Faz 4 Iter 4.2 acceptance)"
```

---

## Controller Closure (subagent task'larından SONRA — sen yaparsın)

1. **Manuel uçtan uca smoke** (gerçek Mosquitto + simulator + ingestion + detectors): `config/detectors.yaml` oluştur (`cp config/detectors.yaml.example config/detectors.yaml`); 3 servisi paralel çalıştır (device_002 MechanicalWear, device_003 HydraulicLeak+ElectricalFault — `devices.yaml.example`). Birkaç dakika sonra `sqlite3 data/telemetry.db "SELECT rule_name, COUNT(*) FROM anomalies GROUP BY rule_name"` → motor_current_high / vibration_elevated / hydraulic_pressure_decline / motor_voltage_erratic satırları görünmeli. SIGINT temiz kapanış.
2. **Doküman:** CLAUDE.md "Mevcut Faz" → Iter 4.2 closure bloğu (6 kural, config-driven, kalibre eşikler, `cp detectors.yaml.example detectors.yaml` çalıştırma notu, imza testleri). ROADMAP § Faz 4 (kabul kriteri 1+4+5 imza testleriyle karşılandı).
3. **Memory:** `project_active_phase` → Iter 4.2 DONE, Iter 4.3 (fusion + dashboard alerts paneli + FP doğrulama) next; kural seti + config runtime contract.
4. **Final whole-iteration review** (spec-compliance + code-quality).
5. **Push YAPMA** — kullanıcı onayı al.

---

## Self-Review (writing-plans)

**Spec coverage (Iter 4.2 maddeleri, spec § 3):**
- ≥5 kural (eşik/süre/türev/oran/varyans) → motor_current_high (eşik+süre, T1), vibration_elevated (oran, T2), hydraulic_pressure_decline (türev, T3), motor_voltage_erratic (varyans, T4), sensor_frozen (süre, T5), motor_temperature_high (eşik, T6) = 6 kural, 5 tip ✓
- `config/detectors.yaml` + `src/detectors/config.py` loader (eşik/param + hangi kural aktif) → T7 ✓
- A/B/C imza testleri (senaryo→kural tetikler; normal→tetiklemez/FP) → T9 ✓
- Eşik kalibrasyonu (normal-vs-arıza ayrımı config'e) → kalibrasyon ölçümleri (plan başı) + detectors.yaml.example değerleri (T7) + imza testleri (T9) ✓
- service config-driven → T8 ✓

**Tip/imza tutarlılığı:** Her kural `__init__(... , severity: str = "warning"|"critical")` + `name` property + `detect(window) -> list[Anomaly]`. `RULE_REGISTRY: dict[str, Callable[..., Detector]]` (T1) tüm tasklarda tutarlı. `build_detectors` `factory(severity=..., **params)` (T7) tüm kuralların imzasıyla uyumlu (params adları config'te kwargs ile birebir). `load_detector_config`/`DetectorConfig`/`RuleConfig` T7'de tanımlı, T8/T9'da kullanılır. `_detect_once(repo, detectors, window_s, seen, now)` Iter 4.1 imzası korunur (T8 yalnız `run()` değiştirir).

**Placeholder taraması:** Her kod adımı tam içerik taşır; eşik değerleri ölçümle gerekçeli (placeholder değil). Tek "iterate" noktası T9 Step 4 — kalibrasyon zaten ölçülü olduğundan testlerin geçmesi beklenir; talimat clean testi zayıflatmamayı açıkça söyler.

**Bağımlılık sırası:** Kurallar (T1-T6) → config (T7, RULE_REGISTRY'ye ihtiyaç duyar — kurallar önce) → service (T8) → imza testleri (T9). Doğru.

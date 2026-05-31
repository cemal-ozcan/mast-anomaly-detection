# Faz 5 Iter 5.2 — IQR + İstatistiksel İmza + Overlap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** İkinci istatistiksel dedektörü (`IQR`) eklemek, A/B/C arıza senaryolarının istatistiksel imzalarını test etmek ve kural ↔ istatistik katmanlarının aynı arızada örtüştüğünü (overlap) kanıtlamak — böylece Faz 5'i kapatmak.

**Architecture:** `IQR` dedektörü mevcut `statistical/base.py` saf yardımcılarını (`split_recent`, `iter_sensor_state_groups`, `EPSILON`) `ThreeSigma` ile aynı şekilde kullanır; on-the-fly rolling baseline (recent-vs-rest), (sensor, state)-bazlı, robust (Q1/Q3 + IQR fence, güncel tail **median**'ı karşılaştırır). `Detector` ABC ve `fuse_anomalies` **değişmez**. İmza testleri engine harness ile clean baseline + arıza tail içeren uzun pencere kurar; statistical dedektör içeride böler. Overlap testi kısa-pencere kural + uzun-pencere istatistik dedektörlerinin aynı sensörü işaretleyip `fuse_anomalies` ile tek `fused(N)`'e indiğini gösterir (servisin iki-pencere mimarisini birebir yansıtır, spec § 8).

**Tech Stack:** Python 3.11, pandas (quantile/median), pytest, mevcut simulator engine harness (CountingClock + monkeypatch).

---

## Ölçümle Doğrulanmış Domain Gerçekleri (plan yazımında ölçüldü, 2026-05-31)

Bu sayılar Iter 5.2 öncesi gerçek simülatör çıktısından ölçüldü (seed 42, üretim eşikleri `sigma_k=3.0`/`iqr_multiplier=1.5`). İmza testlerinin assertion'ları bunlara dayanır — [[feedback_domain_md_truth_source]] (istatistiksel kriteri ölçümle kalibre et, soyut akıl yürütme ile değil; Iter 4.2 dersi).

| Senaryo | Sinyal | Clean μ±σ (state) | Arıza μ | z-skor | 3σ/IQR tetikler mi? |
|---|---|---|---|---|---|
| **A** MechanicalWear | motor_current (raising) | 8.01 ± 0.10 | 9.98 | **19.3** | ✅ güçlü |
| **A** MechanicalWear | vibration (raising) | 0.300 ± 0.010 | 0.448 | **15.2** | ✅ güçlü |
| **B** HydraulicLeak (2-dk hold, mevcut fixture) | hydraulic_pressure (holding) | 79.99 ± 2.00 | 74.97 | 2.51 | ❌ fence içinde |
| **B** HydraulicLeak (**gelişmiş**, 600s hold) | hydraulic_pressure (holding) | 79.99 ± 2.00 | 55.1 (tüm) / 32.8 (son 60s) | **12.4 / 23.6** | ✅ güçlü |
| **C** ElectricalFault | motor_voltage (varyans, mean sabit) | mean sabit | mean sabit | <1.4 | ❌ tasarım gereği kör |

**Karar (kullanıcı, 2026-05-31):**
- **B:** mevcut 2-dk hold fixture istatistiksel olarak yetersiz (2.5σ); **gelişmiş kaçak** için yeni uzun-hold fixture (`devices_with_hydraulic_leak_developed.yaml`, holding 600s) eklenir → pozitif istatistiksel imza ("N saat sonra" gelişmiş arıza kabul kriteri).
- **C:** **tamamlayıcı katman** — ElectricalFault bir varyans/saçılım arızası; merkezi-eğilim (mean/median) dedektörleri tasarımı gereği kör. İmza testi statistical'ın tetiklenMEdiğini (negatif) + kural katmanının (`motor_voltage_erratic`, std) yakaladığını (tamamlayıcı) doğrular.
- **Overlap:** A (MechanicalWear) hem kural (`motor_current_high`) hem istatistik (`three_sigma:motor_current`) tarafından işaretlenir → `fused(N)` corroboration (spec § 8 birebir).

**KRİTİK harness gerçeği (plan yazımında ölçüldü — B2 review bulgusu, çözüldü):** İki-segment stitch (clean baseline + arıza tail) **farklı fixture state_duration'ları** kullanır (ör. clean holding=120s vs developed-leak holding=600s). `mast_position` (ve `motor_temperature`) **durağan-değil** (state'e göre rampalanır / stateful, her `run()` 25°C'ye sıfırlanır) → segmentler arası dağılımları **arızadan değil, farklı zamanlamadan** kayar → A/B testlerinde spurious `three_sigma:mast_position` tetikler (ölçümle gözlendi). Bu bir **harness artefaktıdır** (üretimde baseline süreklidir, sıfırlama yok), arıza sinyali değil. **Çözüm (spec § 5 `sensors` filtresi sanksiyonlu):** her imza testi dedektörü **ilgili durağan sensöre `sensors=[...]` ile daraltır.** Ölçümle doğrulanan scoped sonuçlar: A `[motor_current, vibration]`→ikisi de tetiklenir; B `[hydraulic_pressure]`→tetiklenir; C `[motor_voltage]`→`[]`; clean `[motor_current, motor_voltage, hydraulic_pressure, vibration]`→`[]`. [[feedback_domain_md_truth_source]] (ölç, soyut akıl yürütme ile global `==[]` iddia etme).

---

## Dosya Yapısı

**Yeni:**
- `src/detectors/statistical/iqr.py` — `IQR` dedektörü (tek sorumluluk, `three_sigma.py` ile simetrik).
- `tests/unit/detectors/statistical/test_iqr.py` — IQR birim testleri.
- `tests/fixtures/devices_with_hydraulic_leak_developed.yaml` — gelişmiş kaçak (uzun hold) fixture'ı.
- `tests/scenarios/test_statistical_signatures.py` — A/B/C + clean istatistiksel imza testleri.
- `tests/scenarios/test_statistical_overlap.py` — kural ↔ istatistik overlap testi.

**Değişen:**
- `src/detectors/statistical/__init__.py` — `STATISTICAL_REGISTRY`'ye `"iqr": IQR`.
- `config/detectors.yaml.example` — `statistical.detectors`'a `iqr` bloğu.
- `tests/unit/detectors/test_config.py` — `build_statistical_detectors` iqr testi.
- `tests/scenarios/conftest.py` — `build_statistical_window` (çok-segmentli uzun pencere) + DRY refactor.

**Değişmez (girdi kontratı, spec § 14):** `src/detectors/base.py` (`Detector` ABC, `Anomaly`), `src/detectors/fusion.py`, `src/detectors/service.py`, `src/detectors/statistical/base.py`, `src/detectors/statistical/three_sigma.py`, `src/detectors/config.py` (loader; sadece yaml.example + test eklenir).

---

## Önemli Kontratlar (mevcut koddan, değişmez)

`statistical/base.py` saf yardımcıları (IQR bunları ThreeSigma ile aynen kullanır):
```python
EPSILON = 1e-9
def split_recent(window: pd.DataFrame, current_window_s: int) -> tuple[pd.DataFrame, pd.DataFrame]: ...
def iter_sensor_state_groups(
    baseline_df, current_df, sensors: Sequence[str] | None, min_baseline: int, min_current: int
) -> Iterator[tuple[str, str, pd.Series[float], pd.Series[float]]]: ...
```
- `iter_sensor_state_groups` yield: `(sensor, state, base_vals, cur_vals)` — yalnız yeterli-örnekli gruplar.
- `Anomaly` alanları (frozen): `device_id, rule_name, sensor, severity, score, window_start, window_end, value, description`.
- `STATISTICAL_REGISTRY[name](severity=..., current_window_s=..., **params)` ile kurulur (`build_statistical_detectors`).

---

### Task 1: IQR dedektörü + registry + birim testleri

**Files:**
- Create: `src/detectors/statistical/iqr.py`
- Modify: `src/detectors/statistical/__init__.py`
- Test: `tests/unit/detectors/statistical/test_iqr.py`

- [ ] **Step 1: Birim testlerini yaz (failing)**

`tests/unit/detectors/statistical/test_iqr.py`:
```python
"""IQR istatistiksel dedektör birim testi (Faz 5 Iter 5.2, spec § 6)."""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly
from detectors.statistical.iqr import IQR


def _window(
    baseline_vals: list[float],
    current_vals: list[float],
    sensor: str = "motor_current",
    state: str = "holding",
) -> pd.DataFrame:
    """Baseline (geçmiş) + güncel (son tail) satırlı uzun pencere kurar (test_three_sigma deseni)."""
    rows: list[dict[str, object]] = []
    for i, v in enumerate(baseline_vals):
        rows.append({"device_id": "device_001", "timestamp": f"2026-05-30T00:{i // 60:02d}:{i % 60:02d}.000Z",
                     "sensor": sensor, "state": state, "value": v})
    for i, v in enumerate(current_vals):
        rows.append({"device_id": "device_001", "timestamp": f"2026-05-30T02:00:{i:02d}.000Z",
                     "sensor": sensor, "state": state, "value": v})
    return pd.DataFrame(rows, columns=["device_id", "timestamp", "sensor", "state", "value"])


# Varyanslı baseline (IQR>0): ~0.5 etrafında 0.4/0.5/0.6 döngüsü.
_BASELINE = [0.5 + 0.1 * ((i % 3) - 1) for i in range(40)]


def test_triggers_when_current_median_above_fence() -> None:
    """Güncel medyan baseline üst fence'in dışındaysa iqr:<sensor> anomalisi."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    anomalies = rule.detect(_window(_BASELINE, [2.0] * 6))
    assert len(anomalies) == 1
    a = anomalies[0]
    assert isinstance(a, Anomaly)
    assert a.rule_name == "iqr:motor_current"
    assert a.sensor == "motor_current"
    assert a.device_id == "device_001"
    assert a.value == 2.0  # güncel medyan
    assert a.severity == "warning"
    assert 0.0 <= a.score <= 1.0


def test_triggers_when_current_median_below_fence() -> None:
    """Güncel medyan alt fence'in altındaysa da tetikler (B kaçak yönü)."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    anomalies = rule.detect(_window(_BASELINE, [-2.0] * 6))
    assert len(anomalies) == 1
    assert anomalies[0].value == -2.0


def test_no_trigger_when_current_within_fence() -> None:
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    assert rule.detect(_window(_BASELINE, [0.5] * 6)) == []


def test_no_trigger_when_baseline_constant_iqr_zero() -> None:
    """Sabit baseline (IQR≈0) → güvenilir fence yok → atlanır (EPSILON koruması)."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    assert rule.detect(_window([0.5] * 40, [2.0] * 6)) == []


def test_no_trigger_when_insufficient_baseline() -> None:
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    assert rule.detect(_window(_BASELINE[:10], [2.0] * 6)) == []


def test_per_state_baseline_isolation() -> None:
    """Baseline HOLDING; güncel RAISING → eşleşen state baseline'ı yok → atlanır."""
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    window = _window(_BASELINE, [8.0] * 6, state="holding")
    window.loc[window["timestamp"].str.startswith("2026-05-30T02:00"), "state"] = "raising"
    assert rule.detect(window) == []


def test_sensors_filter_limits_evaluation() -> None:
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5,
               sensors=["vibration"])
    assert rule.detect(_window(_BASELINE, [2.0] * 6, sensor="motor_current")) == []


def test_empty_window_returns_empty() -> None:
    rule = IQR(current_window_s=60, iqr_multiplier=1.5, min_baseline=30, min_current=5)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []
```

- [ ] **Step 2: Testi koştur, fail doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/statistical/test_iqr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.statistical.iqr'`.

- [ ] **Step 3: IQR dedektörünü yaz**

`src/detectors/statistical/iqr.py`:
```python
"""IQR: güncel pencere baseline Q1/Q3 ± m·IQR dışındaysa anomali (Faz 5, spec § 6).

On-the-fly rolling: uzun pencereyi recent-vs-rest böler, (sensor, state) başına baseline
Q1/Q3 + IQR hesaplar, güncel tail median'ı fence dışındaysa tetikler. Robust (median/IQR →
aykırı dirençli, ThreeSigma'nın mean/σ'sına tamamlayıcı). Saf — `now` gerekmez.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from detectors.base import Anomaly, Detector
from detectors.statistical.base import EPSILON, iter_sensor_state_groups, split_recent


class IQR(Detector):
    """Her (sensor, state) için baseline [Q1−m·IQR, Q3+m·IQR]; güncel tail median'ı dışındaysa tetikler."""

    def __init__(
        self,
        current_window_s: int,
        iqr_multiplier: float = 1.5,
        min_baseline: int = 30,
        min_current: int = 5,
        sensors: Sequence[str] | None = None,
        severity: str = "warning",
    ) -> None:
        """Args: current_window_s — güncel tail saniyesi (config'ten); iqr_multiplier — fence çarpanı;
        min_baseline/min_current — minimum örnek; sensors — izlenen sensörler (None=tümü); severity."""
        self._current_window_s = current_window_s
        self._iqr_multiplier = iqr_multiplier
        self._min_baseline = min_baseline
        self._min_current = min_current
        self._sensors = list(sensors) if sensors is not None else None
        self._severity = severity

    @property
    def name(self) -> str:
        return "iqr"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        baseline_df, current_df = split_recent(window, self._current_window_s)
        if current_df.empty:
            return []
        device_id = str(current_df["device_id"].iloc[0])
        win_start = str(current_df["timestamp"].min())
        win_end = str(current_df["timestamp"].max())
        anomalies: list[Anomaly] = []
        for sensor, state, base_vals, cur_vals in iter_sensor_state_groups(
            baseline_df, current_df, self._sensors, self._min_baseline, self._min_current
        ):
            q1 = float(base_vals.quantile(0.25))
            q3 = float(base_vals.quantile(0.75))
            iqr = q3 - q1
            if iqr < EPSILON:
                continue
            cur_median = float(cur_vals.median())
            fence = self._iqr_multiplier * iqr
            lower = q1 - fence
            upper = q3 + fence
            if lower <= cur_median <= upper:
                continue
            # Fence dışı mesafenin IQR'a oranı (spec § 6: "mesafenin IQR'a oranı"); ≥0, ≤1 clamp.
            distance = (lower - cur_median) if cur_median < lower else (cur_median - upper)
            score = min(1.0, distance / iqr)
            anomalies.append(
                Anomaly(
                    device_id=device_id,
                    rule_name=f"iqr:{sensor}",
                    sensor=sensor,
                    severity=self._severity,
                    score=score,
                    window_start=win_start,
                    window_end=win_end,
                    value=cur_median,
                    description=(
                        f"{sensor} {state} güncel medyan {cur_median:.2f} "
                        f"baseline IQR [{lower:.2f}, {upper:.2f}] dışı"
                    ),
                )
            )
        return anomalies
```

- [ ] **Step 4: Registry'ye ekle**

`src/detectors/statistical/__init__.py` — mevcut içerik:
```python
"""İstatistiksel dedektör registry (Faz 5). build_statistical_detectors config-driven kurar."""
from __future__ import annotations

from collections.abc import Callable

from detectors.base import Detector
from detectors.statistical.three_sigma import ThreeSigma

STATISTICAL_REGISTRY: dict[str, Callable[..., Detector]] = {
    "three_sigma": ThreeSigma,
}
```
şununla değiştir:
```python
"""İstatistiksel dedektör registry (Faz 5). build_statistical_detectors config-driven kurar."""
from __future__ import annotations

from collections.abc import Callable

from detectors.base import Detector
from detectors.statistical.iqr import IQR
from detectors.statistical.three_sigma import ThreeSigma

STATISTICAL_REGISTRY: dict[str, Callable[..., Detector]] = {
    "three_sigma": ThreeSigma,
    "iqr": IQR,
}
```

- [ ] **Step 5: Testleri koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/statistical/test_iqr.py -v`
Expected: PASS (8 test).

- [ ] **Step 6: Commit**

```bash
git add src/detectors/statistical/iqr.py src/detectors/statistical/__init__.py tests/unit/detectors/statistical/test_iqr.py
git commit -m "feat(detectors): IQR istatistiksel dedektör + STATISTICAL_REGISTRY (Faz 5 Iter 5.2)"
```

---

### Task 2: IQR config wiring (yaml.example + config testi)

**Files:**
- Modify: `config/detectors.yaml.example`
- Test: `tests/unit/detectors/test_config.py`

- [ ] **Step 1: Config testini yaz (failing)**

`tests/unit/detectors/test_config.py` dosyasının SONUNA ekle (mevcut import'ları kontrol et; `StatisticalConfig`, `RuleConfig`, `build_statistical_detectors` `detectors.config`'ten import edilmeli — yoksa dosya başındaki import satırına ekle):
```python
def test_build_statistical_detectors_includes_iqr() -> None:
    """statistical bloğunda iqr varsa build_statistical_detectors bir IQR kurar."""
    from detectors.config import RuleConfig, StatisticalConfig, build_statistical_detectors

    config = StatisticalConfig(
        baseline_window_s=3600,
        current_window_s=60,
        detectors=(
            RuleConfig(name="three_sigma", severity="warning", enabled=True, params={"sigma_k": 3.0}),
            RuleConfig(name="iqr", severity="warning", enabled=True,
                       params={"iqr_multiplier": 1.5, "min_baseline": 30, "min_current": 5}),
        ),
    )
    detectors = build_statistical_detectors(config)
    assert [d.name for d in detectors] == ["three_sigma", "iqr"]
```

- [ ] **Step 2: Testi koştur (regresyon-guard, PASS beklenir)**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_config.py::test_build_statistical_detectors_includes_iqr -v`
Expected: PASS — Task 1 `STATISTICAL_REGISTRY`'ye `iqr` eklediğinden `build_statistical_detectors` onu kurabilir. Bu test bir regresyon-guard'dır (config yolunun iqr'ı tanıdığını sabitler); klasik kırmızı-adım yok çünkü registry desteği Task 1'de geldi.

- [ ] **Step 3: yaml.example'a iqr bloğu ekle**

`config/detectors.yaml.example` içindeki `statistical.detectors` listesinde şu satırı:
```yaml
    # IQR Iter 5.2'de eklenecek.
```
şununla değiştir:
```yaml
    - name: iqr
      enabled: true
      severity: warning
      params: {iqr_multiplier: 1.5, min_baseline: 30, min_current: 5}
```

- [ ] **Step 4: Config testlerini koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_config.py -v`
Expected: PASS (mevcut + yeni test).

- [ ] **Step 5: yaml.example'ın gerçekten yüklenip kurulduğunu doğrula**

Run:
```bash
.venv/bin/python -c "
from pathlib import Path
from detectors.config import load_detector_config, build_statistical_detectors
c = load_detector_config(Path('config/detectors.yaml.example'))
print([d.name for d in build_statistical_detectors(c.statistical)])
"
```
Expected çıktı: `['three_sigma', 'iqr']`
(PYTHONPATH gerekirse: `PYTHONPATH=src .venv/bin/python -c "..."`.)

- [ ] **Step 6: Commit**

```bash
git add config/detectors.yaml.example tests/unit/detectors/test_config.py
git commit -m "feat(detectors): detectors.yaml.example iqr bloğu + config testi (Faz 5 Iter 5.2)"
```

---

### Task 3: İstatistiksel imza-pencere harness'ı + gelişmiş kaçak fixture'ı

**Files:**
- Create: `tests/fixtures/devices_with_hydraulic_leak_developed.yaml`
- Modify: `tests/scenarios/conftest.py`

Bu task test altyapısıdır: çok-segmentli (clean baseline + arıza tail) uzun pencere üreten `build_statistical_window` ekler. Mevcut `build_detector_window` API'si **değişmez** (rule signature testleri kırılmaz); ortak mantık DRY helper'lara çıkarılır. Doğrulama Task 4/5 testleriyle yapılır; ayrıca bu task'ta hızlı bir altyapı-smoke testi yazılır.

- [ ] **Step 1: Gelişmiş kaçak fixture'ını oluştur**

`tests/fixtures/devices_with_hydraulic_leak_developed.yaml`:
```yaml
# Gelişmiş hidrolik kaçak: uzun holding (600s) → basınç derin düşer (ölçüldü: holding μ~55, son-60s ~33).
# Mevcut 2-dk hold fixture istatistiksel olarak yetersizdi (2.5σ); bu, "N saat sonra" gelişmiş arıza
# kabul kriterini (statistical pozitif imza) karşılar. Iter 5.2 imza testleri kullanır.
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [1, 1]
      raising:  [1, 1]
      holding:  [600, 600]
      lowering: [1, 1]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: hydraulic_leak
        start_after_s: 0
        duration_s: 3600
        params:
          leak_rate_bar_per_min: 5.0
          position_sag_mm: 2.0
```

- [ ] **Step 2: conftest.py'yi DRY refactor + build_statistical_window ekle**

`tests/scenarios/conftest.py` içindeki mevcut `build_detector_window` fonksiyonunu (satır ~64-125, `def build_detector_window(...)` gövdesinin tamamı) şu üç fonksiyonla **değiştir** (import'lar fonksiyon içinde kalır — mevcut desen korunur):
```python
def _run_segment(
    monkeypatch: pytest.MonkeyPatch,
    clock: CountingClock,
    devices_path: Path,
    max_iterations: int,
    mock_publisher: object,
) -> None:
    """Engine'i bir fixture ile koşturur; publish_reading çağrıları paylaşılan mock_publisher'a birikir."""
    from simulator.engine import run

    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=devices_path,
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=max_iterations,
        seed=None,
        clock=clock,
    )


def _frame_from_publisher(mock_publisher: object) -> pd.DataFrame:
    """Birikmiş publish_reading çağrılarına PER-(device,sensor) monoton 1sn timestamp atayıp uzun-format DataFrame döndürür.

    Çağrı sırası korunur → önce koşan segment(ler) daha eski timestamp alır (baseline),
    son segment en yeni (current). state DeviceState StrEnum value'suna çevrilir.
    """
    from collections import defaultdict
    from datetime import UTC, datetime, timedelta

    import pandas as pd  # gövde içi import (mevcut build_detector_window deseni; TYPE_CHECKING dışı runtime kullanımı)

    from simulator.config import DeviceState

    base = datetime(2026, 5, 30, 0, 0, 0, tzinfo=UTC)
    counters: dict[tuple[str, str], int] = defaultdict(int)
    records: list[dict[str, object]] = []
    for c in mock_publisher.publish_reading.call_args_list:  # type: ignore[attr-defined]
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


def build_detector_window(
    monkeypatch: pytest.MonkeyPatch,
    clock: CountingClock,
    devices_path: Path,
    max_iterations: int,
) -> pd.DataFrame:
    """Engine'i tek fixture ile koşturup dedektör-hazır uzun-format pencere döndürür (kural imza testleri)."""
    from unittest.mock import MagicMock

    mock_publisher = MagicMock()
    _run_segment(monkeypatch, clock, devices_path, max_iterations, mock_publisher)
    return _frame_from_publisher(mock_publisher)


def build_statistical_window(
    monkeypatch: pytest.MonkeyPatch,
    clock: CountingClock,
    segments: list[tuple[Path, int]],
) -> pd.DataFrame:
    """Birden çok (fixture, iterations) segmentini SIRAYLA koşturup tek uzun-format pencere döndürür.

    İlk segment(ler) baseline (eski timestamp), son segment güncel (yeni timestamp) olur →
    statistical dedektör split_recent ile içeride ayırır. Tüm segmentler tek mock_publisher'a
    birikir (çağrı sırası = timestamp sırası). current_window_s'i son segmentin iterasyon
    sayısına (~saniye) eşitleyen test, son segmenti "current" yapar.

    Args:
        segments: [(devices_yaml_path, max_iterations), ...]. En az 2 önerilir (baseline + tail).

    Returns:
        [device_id, timestamp, sensor, state, value] kolonlu uzun pencere.
    """
    from unittest.mock import MagicMock

    mock_publisher = MagicMock()
    for devices_path, max_iterations in segments:
        _run_segment(monkeypatch, clock, devices_path, max_iterations, mock_publisher)
    return _frame_from_publisher(mock_publisher)
```

> **Not (TYPE_CHECKING / pd import — B1):** Mevcut conftest `pd`'yi yalnız `TYPE_CHECKING` altında import ediyor ama `_frame_from_publisher`/`build_*` artık `-> pd.DataFrame` döndürüyor ve gövdede `pd.DataFrame(...)` çağırıyor. `from __future__ import annotations` aktif olduğundan dönüş-tipi anotasyonu string kalır (runtime import gerekmez); ANCAK gövdedeki `pd.DataFrame(...)` runtime import ister. Bu yüzden yukarıdaki `_frame_from_publisher` kod bloğu gövdesinde **zaten `import pandas as pd` var** (mevcut `build_detector_window` deseni). Mevcut dosya başındaki `if TYPE_CHECKING: import pandas as pd` satırını **olduğu gibi bırak** (anotasyonlar için yeterli, çakışma yok).

- [ ] **Step 3: Altyapı-smoke testi yaz (failing)**

`tests/scenarios/test_statistical_signatures.py` (Task 4 bunu genişletecek; şimdilik harness'ı doğrulayan tek test):
```python
"""A/B/C + clean istatistiksel imza testleri (Faz 5 Iter 5.2, spec § 10, kabul kriteri 2/4).

build_statistical_window: clean baseline segment(leri) + arıza tail segmenti → uzun pencere.
Statistical dedektör içeride split_recent ile böler; current_window_s = son (arıza) segmentin
iterasyon sayısı → arıza tail "current" olur.
"""
from __future__ import annotations

import pytest

from detectors.statistical.iqr import IQR
from detectors.statistical.three_sigma import ThreeSigma
from tests.scenarios.conftest import FIXTURES, CountingClock, build_statistical_window


def test_harness_builds_two_segment_window(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """build_statistical_window iki segmenti birleştirir; baseline+current ayrılabilir boyutta."""
    window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(FIXTURES / "devices_clean_baseline.yaml", 182),
         (FIXTURES / "devices_with_mechanical_wear.yaml", 181)],
    )
    assert not window.empty
    assert set(window.columns) == {"device_id", "timestamp", "sensor", "state", "value"}
    # motor_current hem baseline hem current segmentten satır içermeli (split anlamlı olsun)
    mc = window[window["sensor"] == "motor_current"]
    assert len(mc) > 300  # ~363 satır (182 + 181)
    # split_recent ile current = son 181s, baseline > 0 satır olmalı (sensors=motor_current ile daralt)
    ts = ThreeSigma(current_window_s=181, sigma_k=3.0, min_baseline=30, min_current=5, sensors=["motor_current"])
    iqr = IQR(current_window_s=181, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=["motor_current"])
    # mechanical_wear motor_current güçlü sinyal → en az bir dedektör yakalamalı
    rules = {a.rule_name for a in ts.detect(window)} | {a.rule_name for a in iqr.detect(window)}
    assert "three_sigma:motor_current" in rules or "iqr:motor_current" in rules
```

- [ ] **Step 4: Testi koştur, fail→pass doğrula**

Run: `.venv/bin/python -m pytest tests/scenarios/test_statistical_signatures.py -v`
Expected: `build_statistical_window` import edilemiyorsa önce FAIL (Step 2 öncesi); Step 2 sonrası PASS.
Ayrıca regresyon: `.venv/bin/python -m pytest tests/scenarios/test_rule_signatures.py -v` → mevcut 5 test hâlâ PASS (build_detector_window API korundu).

- [ ] **Step 5: Commit**

```bash
git add tests/scenarios/conftest.py tests/fixtures/devices_with_hydraulic_leak_developed.yaml tests/scenarios/test_statistical_signatures.py
git commit -m "test(detectors): build_statistical_window harness + gelişmiş kaçak fixture (Faz 5 Iter 5.2)"
```

---

### Task 4: A/B/C + clean istatistiksel imza testleri

**Files:**
- Modify: `tests/scenarios/test_statistical_signatures.py`

Task 3'teki dosyaya A (pozitif), B-developed (pozitif), C (negatif + tamamlayıcı kural) ve clean (FP yok) testlerini ekler. Tüm assertion'lar plan başındaki ölçüm tablosuna dayanır.

- [ ] **Step 1: İmza testlerini ekle (failing değil — IQR/ThreeSigma + harness hazır, doğrudan PASS beklenir)**

`tests/scenarios/test_statistical_signatures.py` dosyasının başındaki import bloğunu şununla genişlet:
```python
from detectors.rules.motor_voltage_erratic import MotorVoltageErratic
from detectors.statistical.iqr import IQR
from detectors.statistical.three_sigma import ThreeSigma
from tests.scenarios.conftest import (
    FIXTURES,
    CountingClock,
    build_detector_window,
    build_statistical_window,
)
```
ve dosyanın SONUNA şu testleri ekle:
```python
# Clean baseline: idle1+raising60+holding120+lowering1 = 182 iter/epizod.
# mechanical_wear: idle1+raising60+holding60+lowering60 = 181 iter/epizod.
# developed leak: idle1+raising1+holding600+lowering1 = 603 iter/epizod.
# electrical_fault: idle60+raising60+holding60+lowering60 = 240 iter/epizod.
# sensors=[...] daraltması: durağan-değil mast_position/motor_temperature harness artefaktını dışlar
# (plan başı "KRİTİK harness gerçeği"; spec § 5 sensors filtresi). Hepsi ölçümle doğrulandı.
_CLEAN = FIXTURES / "devices_clean_baseline.yaml"
_STATIONARY = ["motor_current", "motor_voltage", "hydraulic_pressure", "vibration"]


def test_mechanical_wear_triggers_three_sigma_and_iqr(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """A: MechanicalWear motor_current (z≈19) + vibration (z≈15) hem 3σ hem IQR ile tetiklenir."""
    window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(_CLEAN, 364), (FIXTURES / "devices_with_mechanical_wear.yaml", 181)],
    )
    watched = ["motor_current", "vibration"]
    ts_rules = {a.rule_name for a in ThreeSigma(
        current_window_s=181, sigma_k=3.0, min_baseline=30, min_current=5, sensors=watched).detect(window)}
    iqr_rules = {a.rule_name for a in IQR(
        current_window_s=181, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=watched).detect(window)}
    assert ts_rules == {"three_sigma:motor_current", "three_sigma:vibration"}, f"3σ: {ts_rules}"
    assert iqr_rules == {"iqr:motor_current", "iqr:vibration"}, f"IQR: {iqr_rules}"


def test_developed_hydraulic_leak_triggers_three_sigma_and_iqr(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """B: gelişmiş kaçak hydraulic_pressure'ı (HOLDING, ölçülen z≈12) hem 3σ hem IQR ile tetikler."""
    window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(_CLEAN, 364), (FIXTURES / "devices_with_hydraulic_leak_developed.yaml", 603)],
    )
    watched = ["hydraulic_pressure"]
    ts_rules = {a.rule_name for a in ThreeSigma(
        current_window_s=603, sigma_k=3.0, min_baseline=30, min_current=5, sensors=watched).detect(window)}
    iqr_rules = {a.rule_name for a in IQR(
        current_window_s=603, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=watched).detect(window)}
    assert ts_rules == {"three_sigma:hydraulic_pressure"}, f"3σ: {ts_rules}"
    assert iqr_rules == {"iqr:hydraulic_pressure"}, f"IQR: {iqr_rules}"


def test_electrical_fault_statistical_silent_rule_catches(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """C (varyans arızası): merkezi-eğilim statistical SESSIZ; kural katmanı (std) yakalar — tamamlayıcı.

    ElectricalFault mean/median'ı kaydırmaz (spike'lar simetrik, ölçülen z<1.4) → 3σ/IQR motor_voltage'da
    tetiklenMEZ. Aynı arıza penceresinde motor_voltage_erratic (std) tetiklenir (komplementerlik, spec § 9 C).
    """
    stat_window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(_CLEAN, 364), (FIXTURES / "devices_with_electrical_fault.yaml", 240)],
    )
    watched = ["motor_voltage"]
    ts_anoms = ThreeSigma(
        current_window_s=240, sigma_k=3.0, min_baseline=30, min_current=5, sensors=watched).detect(stat_window)
    iqr_anoms = IQR(
        current_window_s=240, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=watched).detect(stat_window)
    assert ts_anoms == [], f"3σ beklenmedik tetik (varyans arızası kör olmalı): {[a.rule_name for a in ts_anoms]}"
    assert iqr_anoms == [], f"IQR beklenmedik tetik (varyans arızası kör olmalı): {[a.rule_name for a in iqr_anoms]}"

    # Tamamlayıcı kural katmanı: aynı arızayı kısa pencerede motor_voltage_erratic yakalar.
    rule_window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_electrical_fault.yaml", max_iterations=200,
    )
    erratic = MotorVoltageErratic(std_threshold_v=1.0, min_samples=10)
    assert len(erratic.detect(rule_window)) == 1


def test_clean_baseline_no_statistical_trigger(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """Clean baseline + clean tail → durağan sensörlerde statistical HİÇBİR anomali üretmez (FP yok, kriter 4)."""
    window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(_CLEAN, 364), (_CLEAN, 182)],
    )
    ts = ThreeSigma(current_window_s=182, sigma_k=3.0, min_baseline=30, min_current=5, sensors=_STATIONARY)
    iqr = IQR(current_window_s=182, iqr_multiplier=1.5, min_baseline=30, min_current=5, sensors=_STATIONARY)
    assert ts.detect(window) == [], f"clean'de 3σ FP: {[a.rule_name for a in ts.detect(window)]}"
    assert iqr.detect(window) == [], f"clean'de IQR FP: {[a.rule_name for a in iqr.detect(window)]}"
```

- [ ] **Step 2: İmza testlerini koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/scenarios/test_statistical_signatures.py -v`
Expected: PASS (Task 3 smoke + 4 yeni imza testi = 5 test).

> **Eğer bir assertion FAIL ederse:** Plan başındaki ölçüm tablosu + "KRİTİK harness gerçeği" notuyla karşılaştır. Tetiklenmesi gereken (A/B) tetiklemiyorsa: `current_window_s`'in son segmentin iterasyonuna eşit olduğunu, `sensors=[...]` daraltmasının doğru sensörü içerdiğini, baseline'da ilgili (sensor,state)'in ≥30 örnek aldığını doğrula. Beklenmedik tetik (C/clean) varsa: hangi (sensor,state) saptığını logla — büyük olasılıkla `sensors=[...]` listesine durağan-değil bir sensör (mast_position/motor_temperature) sızmıştır. [[feedback_domain_md_truth_source]] gereği assertion'ı değil, sapmanın nedenini araştır.

- [ ] **Step 3: Commit**

```bash
git add tests/scenarios/test_statistical_signatures.py
git commit -m "test(detectors): A/B/C istatistiksel imza + clean FP testleri (Faz 5 Iter 5.2)"
```

---

### Task 5: Overlap analizi testi (kural ↔ istatistik tutarlılığı)

**Files:**
- Create: `tests/scenarios/test_statistical_overlap.py`

Kabul kriteri 3 (ROADMAP § Faz 5): aynı arızayı her iki katman da işaretler. A (MechanicalWear) için kısa-pencere kural (`motor_current_high`) + uzun-pencere istatistik (`three_sigma:motor_current`) aynı sensörü işaretler; servis bunları tek turda `fuse_anomalies` ile `fused(N)`'e indirir (spec § 8).

- [ ] **Step 1: Overlap testini yaz (geç beklenir — bileşenler hazır)**

`tests/scenarios/test_statistical_overlap.py`:
```python
"""Overlap analizi: kural ↔ istatistik aynı arızayı işaretler (Faz 5 Iter 5.2, spec § 10, kabul kriteri 3).

MechanicalWear (A): kısa pencere motor_current_high (kural) + uzun pencere three_sigma:motor_current
(istatistik) aynı motor_current arızasını yakalar. Servis (_detect_once) iki-pencere anomalilerini
tek turda fuse_anomalies ile birleştirir → fused(N) corroboration (spec § 8). Bu test o birleşmeyi
dedektör + fusion seviyesinde gösterir (servisin iki-pencere mimarisini yansıtır).
"""
from __future__ import annotations

import pytest

from detectors.fusion import fuse_anomalies
from detectors.rules.motor_current_high import MotorCurrentHigh
from detectors.statistical.three_sigma import ThreeSigma
from tests.scenarios.conftest import (
    FIXTURES,
    CountingClock,
    build_detector_window,
    build_statistical_window,
)


def test_mechanical_wear_rule_and_statistical_overlap_fused(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """A: motor_current_high (kural, kısa) + three_sigma:motor_current (istatistik, uzun) → fused(N)."""
    mech = FIXTURES / "devices_with_mechanical_wear.yaml"

    # İstatistik katmanı (uzun pencere: clean baseline + arıza tail)
    stat_window = build_statistical_window(
        monkeypatch, patched_engine_clock,
        [(FIXTURES / "devices_clean_baseline.yaml", 364), (mech, 181)],
    )
    stat_anoms = ThreeSigma(
        current_window_s=181, sigma_k=3.0, min_baseline=30, min_current=5, sensors=["motor_current"]
    ).detect(stat_window)  # sensors daraltması: mast_position harness artefaktını dışla (plan başı B2 notu)

    # Kural katmanı (kısa pencere: yalnız arıza verisi, servisteki window_s gibi)
    rule_window = build_detector_window(monkeypatch, patched_engine_clock, mech, max_iterations=181)
    rule_anoms = MotorCurrentHigh(state="raising", threshold_a=9.0, min_samples=10).detect(rule_window)

    # Her iki katman da motor_current'ı bağımsız işaretledi (tutarlılık / overlap)
    assert any(a.sensor == "motor_current" for a in rule_anoms), "kural motor_current'ı yakalamadı"
    assert any(a.rule_name == "three_sigma:motor_current" for a in stat_anoms), \
        "istatistik motor_current'ı yakalamadı"

    # Servis bunları tek turda birleştirir → fused(N), her iki katman description'da
    fused = fuse_anomalies(rule_anoms + stat_anoms)
    assert fused is not None
    assert fused.rule_name.startswith("fused("), f"birleşmedi: {fused.rule_name}"
    assert "motor_current_high" in fused.description
    assert "three_sigma:motor_current" in fused.description
```

- [ ] **Step 2: Testi koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/scenarios/test_statistical_overlap.py -v`
Expected: PASS (1 test).

- [ ] **Step 3: Commit**

```bash
git add tests/scenarios/test_statistical_overlap.py
git commit -m "test(detectors): kural↔istatistik overlap analizi (Faz 5 Iter 5.2)"
```

---

### Task 6: İterasyon kapanış doğrulaması (controller)

Bu task subagent'a verilmez — controller (ana oturum) yürütür. Faz 4/5.1 kapanış deseni.

- [ ] **Step 1: Tam test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: tüm testler PASS (277 + Task1 8 + Task2 1 + Task3 1 + Task4 4 + Task5 1 ≈ 292; smoke skipped 1). Kesin sayı yürütmede doğrulanır.

- [ ] **Step 2: mypy strict**

Run: `.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios`
Expected: `Success: no issues found`.

- [ ] **Step 3: ruff**

Run: `.venv/bin/python -m ruff check src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios`
Expected: `All checks passed!`

- [ ] **Step 4: Canlı uçtan-uca smoke (reduced baseline + seed)**

CLAUDE.md/memory kuralı: istatistik canlı smoke `baseline_window_s` düşürülmüş + geçmiş seed edilmiş şekilde yapılır (prod 3600s hızlı tetiklenmez). ThreeSigma için Iter 5.1'de yapıldı; Iter 5.2'de **IQR'ın da canlı tetiklendiğini** doğrula:
1. `cp config/detectors.yaml.example config/detectors.yaml`, `statistical.baseline_window_s`'i ~300'e düşür.
2. Mosquitto + `python -m simulator` (mechanical_wear'lı fixture veya seeded baseline + yüksek motor_current) + `python -m ingestion` + `python -m detectors`.
3. `sqlite3 data/telemetry.db "SELECT device_id,rule_name,description FROM anomalies"` → `fused(N)` içinde `iqr:...` ve/veya `three_sigma:...` katkısı görülmeli.
4. Temiz kapanış (SIGINT), clean cihazda FP yok.

> Memory dersi: controlled testler FP'yi kaçırabilir; canlı smoke şart. Sonucu kapanış notuna yaz.

- [ ] **Step 5: Dokümanları güncelle (controller)**

- **`docs/specs/2026-05-31-faz5-statistical-detector-design.md` (spec = tek hakem, N4):** § 10/§ 11'i gerçeğe hizala — (a) C (ElectricalFault, varyans arızası) merkezi-eğilim dedektörlerine **tamamlayıcı** (negatif statistical + kural pozitif), § 9 C ile tutarlı; (b) B pozitif statistical imzası **gelişmiş kaçak** (uzun-hold) gerektirir (kısa epizot 2.5σ < fence); (c) imza testleri durağan-değil sensörleri (`mast_position`/`motor_temperature`) `sensors=[...]` ile dışlar (§ 5 filtresi — iki-segment harness artefaktı). Spec arbiter olduğundan kod ile çelişmemeli.
- `CLAUDE.md` → "Mevcut Faz" + "Faz 5" bölümüne Iter 5.2 closure özeti (IQR + imza + overlap + developed-leak fixture + ölçüm tablosu özeti + B/C kararları).
- `docs/ROADMAP.md` → Faz 5 kabul kriterleri (1-5) karşılandı işareti.
- Memory `project_active_phase.md` → Iter 5.2 DONE, Faz 5 closure, IQR runtime contract (score=distance/iqr, name="iqr", rule_name=f"iqr:{sensor}") + B/C imza kararları (varyans arızası mean/median-kör; developed-leak fixture; harness mast_position artefaktı → sensors filtresi).

- [ ] **Step 6: Final whole-iteration review + closure commit**

Faz 4/5.1 deseni: tüm iterasyon diff'ine son review, sonra `docs(faz5): Iter 5.2 closure ...` commit. Push **proaktif yapılmaz** — kullanıcı onayı alınır.

---

## Self-Review (yazım sonrası, spec § 3/§ 6/§ 10/§ 11 karşılaştırması)

**Spec coverage:**
- § 3 Iter 5.2 "IQR dedektörü" → Task 1 ✅
- § 3 Iter 5.2 "A/B/C istatistiksel imza testleri" → Task 4 (A pozitif, B-developed pozitif, C negatif+tamamlayıcı) ✅
- § 3 Iter 5.2 "overlap analizi" → Task 5 ✅
- § 6 IQR modeli (Q1/Q3 ± m·IQR, median, score, EPSILON, rule_name `iqr:{sensor}`) → Task 1 implementasyonu ✅
- § 7 config (`iqr` bloğu, `STATISTICAL_REGISTRY[name](severity=, current_window_s=, **params)`) → Task 2 ✅
- § 10 test stratejisi (birim + imza + overlap + coverage ≥%85) → Task 1/4/5 + Task 6 coverage ✅
- § 11 kabul kriterleri: (2) A/B yakalanır + canlı smoke → Task 4 + Task 6; (3) overlap → Task 5; (4) clean FP yok → Task 4 clean testi; (5) ≥2 dedektör (3σ+IQR) + yeşil + mypy/ruff → Task 1 + Task 6 ✅
- § 9 hata yönetimi (IQR ≈0 → skip; yetersiz örnek → abstain) → Task 1 birim testleri (`test_no_trigger_when_baseline_constant_iqr_zero`, `test_no_trigger_when_insufficient_baseline`) ✅

**Placeholder taraması:** Yok — her kod adımı tam içerik, her komut beklenen çıktıyla.

**Type/isim tutarlılığı:**
- `IQR(current_window_s, iqr_multiplier, min_baseline, min_current, sensors, severity)` — Task 1 tanımı, Task 2/4/5 kullanımı tutarlı.
- `rule_name=f"iqr:{sensor}"`, `name="iqr"` — Task 1 ↔ Task 4/5 assertion'ları tutarlı.
- `build_statistical_window(monkeypatch, clock, segments: list[tuple[Path, int]])` — Task 3 tanımı, Task 3/4/5 kullanımı tutarlı.
- `build_detector_window(monkeypatch, clock, devices_path, max_iterations)` — API korundu (mevcut rule signature testleri ve Task 4/5 kullanır).
- `fuse_anomalies(list[Anomaly]) -> Anomaly | None` — değişmez, Task 5 kullanımı tutarlı.

**C senaryosu kapsam notu:** spec § 10 "A/B/C statistical tetiklenir" ifadesi C için fiziksel olarak yanlıştır (varyans arızası mean/median-kör — ölçümle doğrulandı, z<1.4). Kullanıcı kararıyla (2026-05-31) C "tamamlayıcı katman" olarak ele alınır: statistical negatif + kural pozitif. Bu sapma planda + closure'da belgelenir; spec § 9 C (ElectricalFault) ile tutarlı (varyans imzası kural katmanının işidir).

**Review turu çözümleri (plan-review subagent, 2026-05-31 — receiving-code-review liyakatle değerlendirildi):**
- **B1 (BLOCKING, kabul):** `_frame_from_publisher` kod bloğuna gövde-içi `import pandas as pd` eklendi (verbatim kopyada NameError önlendi).
- **B2 (BLOCKING, kabul + ölçümle doğrulandı):** Global `== []` assertion'ları kırılgan — iki-segment stitch farklı fixture state_duration'ları nedeniyle durağan-değil `mast_position`'ı (review `motor_temperature` sandı; ölçüm `mast_position`'ı gösterdi) A/B'de spurious tetikliyor. Çözüm: tüm imza/overlap testleri `sensors=[...]` ile ilgili durağan sensöre daraltıldı (spec § 5 sanksiyonlu). Scoped sonuçların TAMAMI gerçek simülatörle ölçüldü (A→mc+vib, B→hp, C→[], clean→[]).
- **S1 (kabul):** IQR `score` böleni `fence`(=m·IQR) → `iqr`'a düzeltildi (spec § 6 "mesafenin IQR'a oranı").
- **S3 (kabul):** Task 2 Step 2 "FAIL bekle" → "regresyon-guard PASS" olarak yeniden etiketlendi.
- **N4 (kabul):** Task 6 closure'a spec § 10/§ 11 hizalaması eklendi.
- **Review hipotez düzeltmesi:** Review B2'de `motor_temperature` confound öngördü; ölçüm bunun TETİKLEMEDİĞİNİ, asıl artefaktın `mast_position` olduğunu gösterdi — yine de kök-neden (durağan-değil sensör + harness segment timing) ve çözüm (sensors filtresi) aynı. [[feedback_domain_md_truth_source]].

# Faz 5 — Iterasyon 5.1: İstatistiksel Altyapı + ThreeSigma + İki-Pencere Servis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** İstatistiksel dedektör katmanının iskeleti: saf baseline yardımcıları (recent-vs-rest split + (sensor,state) gruplama) + `ThreeSigma` dedektörü (on-the-fly rolling, μ±k·σ) + `statistical` config bloğu + poll servisinin iki-pencere'ye (kısa kural penceresi + uzun istatistik penceresi) geçişi, çıktılar mevcut fusion'a akar.

**Architecture:** Yeni `src/detectors/statistical/` paketi `rules/` ile simetrik. `base.py` saf (pandas) — `split_recent` (pencerenin max-ts'ine göre baseline/güncel böler) + `iter_sensor_state_groups` (yeterli-örnekli (sensor,state) için baseline+güncel value Series'leri yield eder; DRY — 5.2 IQR de kullanır). `ThreeSigma` ABC'yi (`detect(window)`) uygular, uzun pencereyi içeride böler → SAF kalır. `service._detect_once` `detector_groups: list[(detectors, window_s)]` alır (kural grubu 120s + istatistik grubu 3600s); cihaz başına grup-pencerelerini kurar, anomalileri birleştirir → mevcut `fuse_anomalies` + debounce. `Detector` ABC ve `fuse_anomalies` DEĞİŞMEZ.

**Tech Stack:** Python 3.11, pandas (numpy gerekmez — Series.mean/std), SQLAlchemy, loguru, pytest. Yeni bağımlılık YOK.

---

## Spec Hizalama / Kararlar (spec `docs/specs/2026-05-31-faz5-statistical-detector-design.md`)

- **On-the-fly rolling** (§ 2.1): eğitim/tablo/persist yok. Baseline her poll uzun pencereden hesaplanır; yetersiz örnek → abstain.
- **Aynı servis** (§ 2.2): istatistik anomalileri kural anomalileriyle tek `fused(N)` satırda birleşir.
- **Tek uzun pencere, recent-vs-rest** (§ 2.3): `Detector` ABC değişmez; dedektör timestamp-bazlı böler (`now` gerekmez).
- **(sensor, state)-bazlı robust agregat** (§ 5): baseline μ/σ; güncel tail **mean**'i karşılaştırılır (flicker'a karşı). `σ < 1e-9` → o grup atlanır.
- **`rule_name=f"three_sigma:{sensor}"`** (§ 6): fusion/debounce granülaritesi sensör-bazlı.
- **İki-pencere refaktörü** (§ 8): `_detect_once` `detector_groups` alır (Faz 6 ML grubu da eklenebilir → genişletilebilir soyutlama). Mevcut 7 `_detect_once` testi + integration test yeni imzaya güncellenir (davranış korunur).

**Test/lint komutu (her task sonunda; `.venv/bin/python`, mypy için `MYPYPATH=src`):**
```bash
.venv/bin/python -m pytest -q
MYPYPATH=src .venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/dashboard tests/unit tests/integration tests/scenarios
ruff check src/detectors tests/unit tests/integration
```

---

## Dosya Yapısı

**Oluşturulacak:**
- `src/detectors/statistical/__init__.py` — `STATISTICAL_REGISTRY`
- `src/detectors/statistical/base.py` — `EPSILON`, `split_recent`, `iter_sensor_state_groups`
- `src/detectors/statistical/three_sigma.py` — `ThreeSigma`
- `tests/unit/detectors/statistical/__init__.py`
- `tests/unit/detectors/statistical/test_base.py`
- `tests/unit/detectors/statistical/test_three_sigma.py`
- `tests/integration/test_statistical_detector.py`

**Değiştirilecek:**
- `src/detectors/config.py` — `StatisticalConfig` + `DetectorConfig.statistical` + load parse + `build_statistical_detectors`
- `config/detectors.yaml.example` — `statistical` bloğu
- `tests/unit/detectors/test_config.py` — statistical parse + build testleri
- `src/detectors/service.py` — `_detect_once` `detector_groups` + `run()` iki grup
- `tests/unit/detectors/test_service_detect_once.py` — yeni imza (`[(detectors, window_s)]`)
- `tests/integration/test_detector_config_driven.py` — yeni imza

---

## Task 1: statistical/base.py saf yardımcıları

**Files:**
- Create: `src/detectors/statistical/__init__.py` (geçici boş — Task 2 doldurur)
- Create: `src/detectors/statistical/base.py`
- Create: `tests/unit/detectors/statistical/__init__.py`
- Test: `tests/unit/detectors/statistical/test_base.py`

- [ ] **Step 1: Paket marker'ları**

`src/detectors/statistical/__init__.py` (Task 2'de `STATISTICAL_REGISTRY` ile değişecek; şimdilik docstring):
```python
"""İstatistiksel dedektör katmanı (Faz 5)."""
```
`tests/unit/detectors/statistical/__init__.py`: boş dosya.

- [ ] **Step 2: Failing test** — `tests/unit/detectors/statistical/test_base.py`

```python
"""statistical.base saf yardımcıları (Faz 5 Iter 5.1, spec § 5)."""
from __future__ import annotations

import pandas as pd

from detectors.statistical.base import iter_sensor_state_groups, split_recent


def _row(ts: str, value: float, sensor: str = "motor_current", state: str = "holding") -> dict[str, object]:
    return {"device_id": "device_001", "timestamp": ts, "sensor": sensor, "state": state, "value": value}


def test_split_recent_partitions_by_max_timestamp() -> None:
    """current = son current_window_s; baseline = öncesi (pencerenin max-ts'ine göre)."""
    rows = [_row(f"2026-05-30T00:00:{i:02d}.000Z", float(i)) for i in range(40)]  # 0..39 sn
    window = pd.DataFrame(rows)
    baseline, current = split_recent(window, current_window_s=10)
    # max_ts = ...:39; cutoff = ...:29 → current = [29..39] (11 satır), baseline = [0..28] (29 satır)
    assert list(current["value"]) == [float(i) for i in range(29, 40)]
    assert list(baseline["value"]) == [float(i) for i in range(0, 29)]


def test_split_recent_empty_window() -> None:
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    baseline, current = split_recent(empty, current_window_s=60)
    assert baseline.empty and current.empty


def test_iter_groups_yields_sufficient_only() -> None:
    """Yeterli baseline (≥min_baseline) + güncel (≥min_current) örnekli (sensor,state) yield edilir."""
    baseline = pd.DataFrame([_row(f"2026-05-30T00:{i:02d}:00.000Z", 0.5) for i in range(30)])
    current = pd.DataFrame([_row(f"2026-05-30T01:00:{i:02d}.000Z", 2.0) for i in range(5)])
    groups = list(iter_sensor_state_groups(baseline, current, None, min_baseline=30, min_current=5))
    assert len(groups) == 1
    sensor, state, base_vals, cur_vals = groups[0]
    assert sensor == "motor_current" and state == "holding"
    assert len(base_vals) == 30 and len(cur_vals) == 5


def test_iter_groups_skips_insufficient() -> None:
    """Az örnekli grup atlanır (abstain)."""
    baseline = pd.DataFrame([_row(f"2026-05-30T00:{i:02d}:00.000Z", 0.5) for i in range(10)])  # <30
    current = pd.DataFrame([_row(f"2026-05-30T01:00:{i:02d}.000Z", 2.0) for i in range(5)])
    assert list(iter_sensor_state_groups(baseline, current, None, min_baseline=30, min_current=5)) == []


def test_iter_groups_respects_sensor_filter() -> None:
    """sensors verilirse yalnız o sensörler değerlendirilir."""
    base = [_row(f"2026-05-30T00:{i:02d}:00.000Z", 0.5, sensor="motor_current") for i in range(30)]
    base += [_row(f"2026-05-30T00:{i:02d}:30.000Z", 0.05, sensor="vibration") for i in range(30)]
    cur = [_row(f"2026-05-30T01:00:{i:02d}.000Z", 2.0, sensor="motor_current") for i in range(5)]
    cur += [_row(f"2026-05-30T01:00:{i:02d}.500Z", 0.5, sensor="vibration") for i in range(5)]
    groups = list(iter_sensor_state_groups(
        pd.DataFrame(base), pd.DataFrame(cur), ["motor_current"], min_baseline=30, min_current=5
    ))
    assert [g[0] for g in groups] == ["motor_current"]
```

- [ ] **Step 3: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/statistical/test_base.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.statistical.base'`

- [ ] **Step 4: Implement** — `src/detectors/statistical/base.py`

```python
"""İstatistiksel dedektör saf yardımcıları (Faz 5, spec § 5).

split_recent: uzun pencereyi baseline (eski) + güncel (son tail) olarak böler.
iter_sensor_state_groups: yeterli-örnekli (sensor, state) için baseline+güncel value Series üretir.
Saf — yalnız pandas; storage/service import etmez. ThreeSigma (5.1) + IQR (5.2) ortak kullanır.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence

import pandas as pd

# σ/IQR < EPSILON → yeterli değişkenlik yok, güvenilir baseline değil (o grup atlanır).
EPSILON = 1e-9


def split_recent(
    window: pd.DataFrame, current_window_s: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Uzun pencereyi (baseline, current) olarak böler (pencerenin max timestamp'ine göre).

    current = [max_ts - current_window_s, max_ts]; baseline = öncesi. Güncel'i baseline'dan
    dışlamak gelişen arızanın baseline'ı kirletmesini azaltır (spec § 5). `now` gerekmez —
    bölme pencerenin kendi zaman aralığına dayanır (dedektör saf kalır).

    Args:
        window: [device_id, timestamp, sensor, state, value] uzun-format (ISO 8601 ms Z).
        current_window_s: son "güncel" pencere saniyesi.

    Returns:
        (baseline_df, current_df). Boş pencere → (window, window).
    """
    if window.empty:
        return window, window
    ts = pd.to_datetime(window["timestamp"], format="ISO8601", utc=True)
    cutoff = ts.max() - pd.Timedelta(seconds=current_window_s)
    is_current = ts >= cutoff
    return window[~is_current], window[is_current]


def iter_sensor_state_groups(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    sensors: Sequence[str] | None,
    min_baseline: int,
    min_current: int,
) -> Iterator[tuple[str, str, "pd.Series[float]", "pd.Series[float]"]]:
    """Yeterli-örnekli (sensor, state) için (sensor, state, baseline_values, current_values).

    Güncel tail'de görülen her (sensor, state) için, baseline'da ≥min_baseline ve güncelde
    ≥min_current örnek varsa yield eder; aksi halde atlar (abstain).

    Args:
        baseline_df, current_df: split_recent çıktısı.
        sensors: İzlenecek sensörler; None → güncelde görülen tüm sensörler (sıralı).
        min_baseline, min_current: minimum örnek eşikleri.

    Yields:
        (sensor, state, baseline_values: pd.Series, current_values: pd.Series).
    """
    if current_df.empty:
        return
    sensor_list = sensors if sensors is not None else sorted(current_df["sensor"].unique())
    for sensor in sensor_list:
        cur_sensor = current_df[current_df["sensor"] == sensor]
        base_sensor = baseline_df[baseline_df["sensor"] == sensor]
        for state in sorted(cur_sensor["state"].unique()):
            cur_vals = cur_sensor[cur_sensor["state"] == state]["value"]
            base_vals = base_sensor[base_sensor["state"] == state]["value"]
            if len(cur_vals) < min_current or len(base_vals) < min_baseline:
                continue
            yield str(sensor), str(state), base_vals, cur_vals
```

- [ ] **Step 5: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/statistical/test_base.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Lint**

Run: `MYPYPATH=src .venv/bin/python -m mypy src/detectors tests/unit/detectors/statistical && ruff check src/detectors tests/unit/detectors/statistical`
Expected: temiz. (mypy `pd.Series[float]` string-annotation pandas override altında geçer; sorun çıkarsa `pd.Series` yalın yaz.)

- [ ] **Step 7: Commit**

```bash
git add src/detectors/statistical/__init__.py src/detectors/statistical/base.py tests/unit/detectors/statistical/
git commit -m "feat(detectors): statistical/base saf yardımcıları (split_recent, group iter) (Faz 5 Iter 5.1)"
```

---

## Task 2: ThreeSigma dedektörü + STATISTICAL_REGISTRY

**Files:**
- Create: `src/detectors/statistical/three_sigma.py`
- Modify: `src/detectors/statistical/__init__.py`
- Test: `tests/unit/detectors/statistical/test_three_sigma.py`

- [ ] **Step 1: Failing test** — `tests/unit/detectors/statistical/test_three_sigma.py`

```python
"""ThreeSigma istatistiksel dedektör birim testi (Faz 5 Iter 5.1, spec § 6)."""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly
from detectors.statistical.three_sigma import ThreeSigma


def _window(
    baseline_vals: list[float],
    current_vals: list[float],
    sensor: str = "motor_current",
    state: str = "holding",
) -> pd.DataFrame:
    """Baseline (geçmiş, dakikalar) + güncel (son ~saniyeler) satırlı uzun pencere kurar."""
    rows: list[dict[str, object]] = []
    for i, v in enumerate(baseline_vals):
        rows.append({"device_id": "device_001", "timestamp": f"2026-05-30T00:{i // 60:02d}:{i % 60:02d}.000Z",
                     "sensor": sensor, "state": state, "value": v})
    for i, v in enumerate(current_vals):
        rows.append({"device_id": "device_001", "timestamp": f"2026-05-30T02:00:{i:02d}.000Z",
                     "sensor": sensor, "state": state, "value": v})
    return pd.DataFrame(rows, columns=["device_id", "timestamp", "sensor", "state", "value"])


# Varyanslı baseline (σ>0): ~0.5 etrafında 0.4/0.5/0.6 döngüsü.
_BASELINE = [0.5 + 0.1 * ((i % 3) - 1) for i in range(40)]


def test_triggers_when_current_mean_far_from_baseline() -> None:
    """Güncel ort baseline μ±3σ dışındaysa three_sigma:<sensor> anomalisi."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    window = _window(_BASELINE, [2.0] * 6)  # baseline ~0.5±0.08, güncel 2.0 → çok dışında
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert isinstance(a, Anomaly)
    assert a.rule_name == "three_sigma:motor_current"
    assert a.sensor == "motor_current"
    assert a.device_id == "device_001"
    assert a.value == 2.0  # güncel ortalama
    assert a.severity == "warning"
    assert 0.0 <= a.score <= 1.0


def test_no_trigger_when_current_within_fence() -> None:
    """Güncel ort baseline'a yakınsa tetiklemez."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    assert rule.detect(_window(_BASELINE, [0.5] * 6)) == []


def test_no_trigger_when_baseline_constant_sigma_zero() -> None:
    """Sabit baseline (σ≈0) → güvenilir fence yok → atlanır (EPSILON koruması)."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    assert rule.detect(_window([0.5] * 40, [2.0] * 6)) == []


def test_no_trigger_when_insufficient_baseline() -> None:
    """Baseline < min_baseline → o (sensor,state) atlanır."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    assert rule.detect(_window(_BASELINE[:10], [2.0] * 6)) == []


def test_per_state_baseline_isolation() -> None:
    """Baseline HOLDING; güncel RAISING → eşleşen state baseline'ı yok → atlanır."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    window = _window(_BASELINE, [8.0] * 6, state="holding")
    # güncel satırların state'ini RAISING yap (baseline HOLDING kalır)
    window.loc[window["timestamp"].str.startswith("2026-05-30T02:00"), "state"] = "raising"
    assert rule.detect(window) == []


def test_sensors_filter_limits_evaluation() -> None:
    """sensors=['vibration'] → motor_current sapması yok sayılır."""
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5,
                      sensors=["vibration"])
    assert rule.detect(_window(_BASELINE, [2.0] * 6, sensor="motor_current")) == []


def test_empty_window_returns_empty() -> None:
    rule = ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/statistical/test_three_sigma.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.statistical.three_sigma'`

- [ ] **Step 3: Implement** — `src/detectors/statistical/three_sigma.py`

```python
"""ThreeSigma: güncel pencere baseline μ±k·σ dışındaysa anomali (Faz 5, spec § 6).

On-the-fly rolling: uzun pencereyi recent-vs-rest böler, (sensor, state) başına baseline
mean μ + std σ hesaplar, güncel tail mean'i fence dışındaysa tetikler. Saf — `now` gerekmez.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from detectors.base import Anomaly, Detector
from detectors.statistical.base import EPSILON, iter_sensor_state_groups, split_recent


class ThreeSigma(Detector):
    """Her (sensor, state) için baseline mean±k·σ; güncel tail mean'i fence dışındaysa tetikler."""

    def __init__(
        self,
        current_window_s: int,
        sigma_k: float = 3.0,
        min_baseline: int = 30,
        min_current: int = 5,
        sensors: Sequence[str] | None = None,
        severity: str = "warning",
    ) -> None:
        """Args: current_window_s — güncel tail saniyesi (config'ten); sigma_k — fence katsayısı;
        min_baseline/min_current — minimum örnek; sensors — izlenen sensörler (None=tümü); severity."""
        self._current_window_s = current_window_s
        self._sigma_k = sigma_k
        self._min_baseline = min_baseline
        self._min_current = min_current
        self._sensors = list(sensors) if sensors is not None else None
        self._severity = severity

    @property
    def name(self) -> str:
        return "three_sigma"

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
            mu = float(base_vals.mean())
            sigma = float(base_vals.std())  # ddof=1
            if sigma < EPSILON:
                continue
            cur_mean = float(cur_vals.mean())
            deviation = abs(cur_mean - mu)
            fence = self._sigma_k * sigma
            if deviation <= fence:
                continue
            score = min(1.0, (deviation - fence) / fence)
            anomalies.append(
                Anomaly(
                    device_id=device_id,
                    rule_name=f"three_sigma:{sensor}",
                    sensor=sensor,
                    severity=self._severity,
                    score=score,
                    window_start=win_start,
                    window_end=win_end,
                    value=cur_mean,
                    description=(
                        f"{sensor} {state} güncel ort {cur_mean:.2f} "
                        f"baseline {mu:.2f}±{sigma:.2f} ({self._sigma_k:.0f}σ dışı)"
                    ),
                )
            )
        return anomalies
```

- [ ] **Step 4: STATISTICAL_REGISTRY** — `src/detectors/statistical/__init__.py` (TÜM içeriği değiştir)

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

- [ ] **Step 5: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/statistical/test_three_sigma.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: Lint**

Run: `MYPYPATH=src .venv/bin/python -m mypy src/detectors tests/unit/detectors/statistical && ruff check src/detectors tests/unit/detectors/statistical`
Expected: temiz

- [ ] **Step 7: Commit**

```bash
git add src/detectors/statistical/three_sigma.py src/detectors/statistical/__init__.py tests/unit/detectors/statistical/test_three_sigma.py
git commit -m "feat(detectors): ThreeSigma istatistiksel dedektör + STATISTICAL_REGISTRY (Faz 5 Iter 5.1)"
```

---

## Task 3: config — StatisticalConfig + build_statistical_detectors + example bloğu

**Files:**
- Modify: `src/detectors/config.py`
- Modify: `config/detectors.yaml.example`
- Test: `tests/unit/detectors/test_config.py`

- [ ] **Step 1: detectors.yaml.example'a statistical bloğu ekle** — `config/detectors.yaml.example` SONUNA ekle

(Mevcut `detectors:` bloğunun ARDINDAN, top-level sibling olarak):
```yaml

# İstatistiksel dedektörler (Faz 5): on-the-fly rolling baseline (1h geçmiş) → 3-sigma.
# Kural penceresinden (window_s) ayrı, daha uzun baseline penceresi kullanır.
statistical:
  baseline_window_s: 3600     # ~1 saat geçmiş baseline
  current_window_s: 60        # son 60s "güncel" pencere
  detectors:
    - name: three_sigma
      enabled: true
      severity: warning
      params: {sigma_k: 3.0, min_baseline: 30, min_current: 5}
    # IQR Iter 5.2'de eklenecek.
```

- [ ] **Step 2: Failing test** — `tests/unit/detectors/test_config.py` SONUNA ekle

(Mevcut testlerin altına; mevcut importlara `StatisticalConfig`, `build_statistical_detectors` ekle.)

Önce dosya başındaki import bloğunu güncelle:
```python
from detectors.config import (
    DetectorConfig,
    RuleConfig,
    StatisticalConfig,
    build_detectors,
    build_statistical_detectors,
    load_detector_config,
)
```

Sonuna testler ekle:
```python
_VALID_WITH_STATISTICAL = """
detectors:
  poll_interval_s: 5.0
  window_s: 120
  rules:
    - name: motor_temperature_high
      enabled: true
      severity: critical
      params: {critical_threshold_c: 80.0}
statistical:
  baseline_window_s: 3600
  current_window_s: 60
  detectors:
    - name: three_sigma
      enabled: true
      severity: warning
      params: {sigma_k: 3.0, min_baseline: 30, min_current: 5}
"""


def test_load_parses_statistical_block(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID_WITH_STATISTICAL))
    assert isinstance(cfg.statistical, StatisticalConfig)
    assert cfg.statistical.baseline_window_s == 3600
    assert cfg.statistical.current_window_s == 60
    assert len(cfg.statistical.detectors) == 1
    assert cfg.statistical.detectors[0].name == "three_sigma"


def test_load_no_statistical_block_is_none(tmp_path: Path) -> None:
    """statistical bloğu yoksa cfg.statistical None (geriye uyumlu — Faz 4 config'leri)."""
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID))
    assert cfg.statistical is None


def test_build_statistical_detectors_constructs_three_sigma(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID_WITH_STATISTICAL))
    detectors = build_statistical_detectors(cfg.statistical)
    assert [d.name for d in detectors] == ["three_sigma"]


def test_build_statistical_detectors_none_returns_empty() -> None:
    assert build_statistical_detectors(None) == []


def test_build_statistical_unknown_raises(tmp_path: Path) -> None:
    bad = _VALID_WITH_STATISTICAL.replace("three_sigma", "nonexistent_stat")
    cfg = load_detector_config(_write(tmp_path / "d.yaml", bad))
    with pytest.raises(ValueError, match="bilinmeyen istatistiksel"):
        build_statistical_detectors(cfg.statistical)


def test_example_file_statistical_builds() -> None:
    """config/detectors.yaml.example statistical bloğu geçerli + three_sigma kurar."""
    cfg = load_detector_config(Path("config/detectors.yaml.example"))
    assert cfg.statistical is not None
    assert [d.name for d in build_statistical_detectors(cfg.statistical)] == ["three_sigma"]
```

(NOT: `_VALID` ve `_write` mevcut test dosyasında zaten tanımlı — yeniden tanımlama.)

- [ ] **Step 3: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'StatisticalConfig'`

- [ ] **Step 4: config.py'yi güncelle** — `src/detectors/config.py`

Import bölümüne ekle (`from detectors.rules import RULE_REGISTRY` altına):
```python
from detectors.statistical import STATISTICAL_REGISTRY
```

`RuleConfig` altına `StatisticalConfig` ekle ve `DetectorConfig`'e `statistical` alanı:
```python
@dataclass(frozen=True)
class StatisticalConfig:
    """detectors.yaml `statistical` bloğu (Faz 5)."""

    baseline_window_s: int
    current_window_s: int
    detectors: tuple[RuleConfig, ...]


@dataclass(frozen=True)
class DetectorConfig:
    """detectors.yaml `detectors` bloğu (+ opsiyonel `statistical`, Faz 5)."""

    poll_interval_s: float
    window_s: int
    rules: tuple[RuleConfig, ...]
    statistical: StatisticalConfig | None = None
```

`load_detector_config`'te, `return DetectorConfig(...)`'tan ÖNCE statistical parse et ve döndürülen yapıya ekle:
```python
        statistical = _parse_statistical(data.get("statistical"))
        return DetectorConfig(
            poll_interval_s=float(det["poll_interval_s"]),
            window_s=int(det["window_s"]),
            rules=rules,
            statistical=statistical,
        )
```

`load_detector_config`'in ÜSTÜNE `_parse_statistical` helper ekle:
```python
def _parse_statistical(block: Any) -> StatisticalConfig | None:
    """`statistical` bloğunu (varsa) StatisticalConfig'e çevirir; yoksa None."""
    if block is None:
        return None
    detectors = tuple(
        RuleConfig(
            name=str(d["name"]),
            severity=str(d.get("severity", "warning")),
            enabled=bool(d.get("enabled", True)),
            params=dict(d.get("params") or {}),
        )
        for d in block["detectors"]
    )
    return StatisticalConfig(
        baseline_window_s=int(block["baseline_window_s"]),
        current_window_s=int(block["current_window_s"]),
        detectors=detectors,
    )
```

`build_detectors`'ın altına `build_statistical_detectors` ekle:
```python
def build_statistical_detectors(config: StatisticalConfig | None) -> list[Detector]:
    """Config'ten aktif istatistiksel dedektörleri STATISTICAL_REGISTRY üzerinden kurar.

    Her dedektör `STATISTICAL_REGISTRY[name](severity=..., current_window_s=..., **params)` ile
    inşa edilir (current_window_s blok seviyesinden geçer).

    Args:
        config: StatisticalConfig veya None (statistical bloğu yoksa).

    Returns:
        Kurulu Detector listesi (None → boş; disabled atlanır).

    Raises:
        ValueError: Bilinmeyen dedektör adı veya geçersiz params.
    """
    if config is None:
        return []
    detectors: list[Detector] = []
    for rc in config.detectors:
        if not rc.enabled:
            continue
        factory = STATISTICAL_REGISTRY.get(rc.name)
        if factory is None:
            raise ValueError(
                f"detectors config: bilinmeyen istatistiksel dedektör '{rc.name}' (registry'de yok)"
            )
        try:
            detectors.append(
                factory(severity=rc.severity, current_window_s=config.current_window_s, **rc.params)
            )
        except TypeError as e:
            raise ValueError(
                f"detectors config: istatistiksel dedektör '{rc.name}' parametre hatası: {e}"
            ) from e
    return detectors
```

- [ ] **Step 5: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_config.py -q`
Expected: PASS (mevcut 8 + 6 yeni = 14 passed)

- [ ] **Step 6: Lint + Commit**

```bash
MYPYPATH=src .venv/bin/python -m mypy src/detectors tests/unit/detectors/test_config.py && ruff check src/detectors tests/unit/detectors/test_config.py
git add src/detectors/config.py config/detectors.yaml.example tests/unit/detectors/test_config.py
git commit -m "feat(detectors): StatisticalConfig + build_statistical_detectors + example bloğu (Faz 5 Iter 5.1)"
```

---

## Task 4: _detect_once iki-pencere (detector_groups) refaktörü + run()

**Files:**
- Modify: `src/detectors/service.py`
- Modify: `tests/unit/detectors/test_service_detect_once.py`
- Modify: `tests/integration/test_detector_config_driven.py`

- [ ] **Step 1: Mevcut testleri yeni imzaya güncelle** — `tests/unit/detectors/test_service_detect_once.py`

Tüm `_detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)` çağrılarını `_detect_once(repo, [(detectors, _BIG_WINDOW_S)], active, _NOW)` yap (7 test: persists_single, fuses_multiple, debounces, rearms, escalation, below_threshold, failing_rule). Çağrı dışındaki her şey (seed, assertion) AYNI kalır — refaktör davranış-korur.

Örnek (her çağrı bu şekilde sarmalanır):
```python
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], active, _NOW)
```
`test_detect_once_rearms_after_fault_clears` ve `test_detect_once_escalation_writes_new_row`'daki ardışık çağrılar da aynı şekilde sarmalanır.

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -q`
Expected: FAIL — eski `_detect_once` 2. argümanı `list[Detector]` olarak iterler ve `.detect` çağırır; test `[(detectors, window_s)]` geçer → iç döngü tuple'a çarpar → **`AttributeError: 'tuple' object has no attribute 'detect'`**. Gerçek kırmızı (yeni gövde Step 3'te yazılınca yeşile döner).

- [ ] **Step 3: `_detect_once`'u detector_groups'a refaktör et** — `src/detectors/service.py`

Import ekle (`from detectors.fusion import fuse_anomalies` altına):
```python
from detectors.config import build_detectors, build_statistical_detectors, load_detector_config
```
(Mevcut `from detectors.config import build_detectors, load_detector_config` satırını bununla DEĞİŞTİR.)

`_detect_once`'u TÜMÜYLE değiştir:
```python
def _detect_once(
    repository: TelemetryRepository,
    detector_groups: list[tuple[list[Detector], int]],
    active: dict[str, frozenset[str]],
    now: datetime,
) -> None:
    """Tek poll turu: her cihaz × her dedektör-grubu (kendi penceresinde) → fusion → debounce.

    `detector_groups`: (dedektörler, window_s) çiftleri — kural grubu kısa pencere (120s),
    istatistik grubu uzun pencere (3600s). Cihaz başına her grubun penceresi kurulur
    (aynı window_s tekrar kurulmaz — window_cache), tüm anomaliler birleştirilir → fuse_anomalies →
    epizot debounce (`active`). Faz 6 ML grubu yeni bir çift olarak eklenebilir.
    """
    created_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    for device_id in repository.list_devices():
        device_anomalies: list[Anomaly] = []
        window_cache: dict[int, pd.DataFrame] = {}
        for detectors, window_s in detector_groups:
            window = window_cache.get(window_s)
            if window is None:
                window = build_window(
                    repository, device_id, SENSORS, _since_cutoff(now, window_s)
                )
                window_cache[window_s] = window
            if window.empty:  # pragma: no cover - list_devices yalnız telemetri'si olan cihazları döndürür
                continue
            for detector in detectors:
                try:
                    device_anomalies.extend(detector.detect(window))
                except (KeyError, ValueError) as e:
                    logger.error("Dedektör '{}' hata verdi, atlandı: {}", detector.name, e)
                    continue

        rule_set = frozenset(a.rule_name for a in device_anomalies)
        if not rule_set:
            active.pop(device_id, None)  # fault temizlendi → re-arm
            continue
        # NOT: list_devices() append-only telemetry'den DISTINCT okur → cihaz asla "düşmez".
        if active.get(device_id) == rule_set:
            continue  # aynı kural-seti süregeliyor → debounce
        fused = fuse_anomalies(device_anomalies)
        if fused is None:  # pragma: no cover - rule_set boş değilse fused None olamaz
            continue
        try:
            repository.insert_anomaly(fused, created_at)
        except OperationalError as e:
            logger.error("Anomali yazılamadı (atlandı): {}", e)
            continue
        active[device_id] = rule_set
        logger.info(
            "Alert: device={} rules={} value={:.2f} sev={}",
            fused.device_id,
            sorted(rule_set),
            fused.value,
            fused.severity,
        )
```

(NOT: `build_window`, `_since_cutoff`, `SENSORS` DEĞİŞMEZ. `_since_cutoff` artık `_detect_once` içinde grup başına çağrılır.)

- [ ] **Step 4: `run()`'ı iki gruba göre güncelle** — `src/detectors/service.py`

`run()` içinde `detectors: list[Detector] = build_detectors(detector_config)` ve `active = {}` ile log+loop kısmını şununla değiştir:
```python
        rule_detectors: list[Detector] = build_detectors(detector_config)
        statistical_detectors: list[Detector] = build_statistical_detectors(detector_config.statistical)
        detector_groups: list[tuple[list[Detector], int]] = [
            (rule_detectors, detector_config.window_s)
        ]
        if statistical_detectors and detector_config.statistical is not None:
            detector_groups.append(
                (statistical_detectors, detector_config.statistical.baseline_window_s)
            )
        active: dict[str, frozenset[str]] = {}

        shutdown = threading.Event()

        def _on_signal(signum: int, _frame: FrameType | None) -> None:
            logger.info("Shutdown sinyali alındı: {}", signum)
            shutdown.set()

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        logger.info(
            "Detector servisi başladı: poll={}s kurallar={} istatistik={}",
            detector_config.poll_interval_s,
            [d.name for d in rule_detectors],
            [d.name for d in statistical_detectors],
        )
        while not shutdown.is_set():
            try:
                _detect_once(repository, detector_groups, active, datetime.now(UTC))
            except OperationalError as e:
                logger.error("Poll turu DB hatası (devam): {}", e)
            shutdown.wait(detector_config.poll_interval_s)
```
(`run()` `# pragma: no cover` kalır. Eski `seen`/tek-pencere log satırları kalkar.)

- [ ] **Step 5: Integration testini yeni imzaya güncelle** — `tests/integration/test_detector_config_driven.py`

`test_config_driven_detectors_persist_anomalies` içindeki çağrıyı sarmala:
```python
        _detect_once(repo, [(detectors, config.window_s)], active, datetime(2026, 5, 30, 1, 0, 0, tzinfo=UTC))
```
(`test_run_signature_is_config_driven` AYNI kalır — `run()` imzası değişmedi: hâlâ `(ingestion_config_path, detectors_config_path)`.)

- [ ] **Step 6: Run, confirm PASS + full suite**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py tests/integration/test_detector_config_driven.py -q`
Expected: PASS (7 + 2). Sonra tam suite:
Run: `.venv/bin/python -m pytest -q`
Expected: tümü PASS (1 smoke skipped). Iter 4.1 `test_service_build_window.py` + `test_detector_persistence.py` etkilenmez.

- [ ] **Step 7: Lint + Commit**

```bash
MYPYPATH=src .venv/bin/python -m mypy src/detectors tests/unit tests/integration && ruff check src/detectors tests/unit tests/integration
git add src/detectors/service.py tests/unit/detectors/test_service_detect_once.py tests/integration/test_detector_config_driven.py
git commit -m "refactor(detectors): _detect_once detector_groups (iki-pencere) + run() istatistik grubu (Faz 5 Iter 5.1)"
```

---

## Task 5: İstatistiksel uçtan-uca integration testi

**Files:**
- Test: `tests/integration/test_statistical_detector.py`

- [ ] **Step 1: Failing test** — `tests/integration/test_statistical_detector.py`

```python
"""Integration: uzun pencere → ThreeSigma tespit → fusion → anomalies (Faz 5 Iter 5.1).

Servis _detect_once iki-pencere yolu: kural (kısa) + istatistik (uzun) anomalileri aynı
cihazda birleşir → tek fused satır. Statistical dedektör on-the-fly rolling baseline'dan
güncel sapmayı yakalar.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from detectors.base import Detector
from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.service import _detect_once
from detectors.statistical.three_sigma import ThreeSigma
from ingestion.message_parser import IngestedReading
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository

_BIG_WINDOW_S = 1_000_000_000


def _reading(sensor: str, ts: str, value: float, state: str = "holding") -> IngestedReading:
    return IngestedReading(
        device_id="device_001", sensor=sensor, timestamp=ts, state=state, value=value, unit="x"
    )


def test_three_sigma_detects_and_fuses_with_rule(tmp_path: Path) -> None:
    """Geçmiş normal motor_current baseline + sapan güncel tail → three_sigma; temp_high ile fused(2)."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        # Baseline: 40 normal HOLDING motor_current (~0.5±0.08, varyanslı) geçmişte.
        for i in range(40):
            v = 0.5 + 0.1 * ((i % 3) - 1)
            repo.insert(_reading("motor_current", f"2026-05-30T11:{i:02d}:00.000Z", v))
        # Güncel tail: 6 yüksek motor_current (~2.0) son 60s içinde.
        for i in range(6):
            repo.insert(_reading("motor_current", f"2026-05-30T12:00:{i:02d}.000Z", 2.0))
        # Aynı turda bir kural da tetiklensin: motor_temperature 95°C (güncel).
        repo.insert(_reading("motor_temperature", "2026-05-30T12:00:03.000Z", 95.0))

        rule_detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
        stat_detectors: list[Detector] = [
            ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
        ]
        groups: list[tuple[list[Detector], int]] = [
            (rule_detectors, _BIG_WINDOW_S),
            (stat_detectors, _BIG_WINDOW_S),
        ]
        active: dict[str, frozenset[str]] = {}
        _detect_once(repo, groups, active, datetime(2026, 5, 30, 12, 0, 10, tzinfo=UTC))

        stored = repo.fetch_recent_anomalies(limit=10)
        assert len(stored) == 1
        assert stored[0].rule_name == "fused(2)"
        assert "three_sigma:motor_current" in stored[0].description
        assert "motor_temperature_high" in stored[0].description
    finally:
        engine.dispose()


def test_three_sigma_no_fire_on_normal_current(tmp_path: Path) -> None:
    """Güncel tail baseline'a yakınsa istatistik tetiklemez (FP yok)."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        for i in range(40):
            v = 0.5 + 0.1 * ((i % 3) - 1)
            repo.insert(_reading("motor_current", f"2026-05-30T11:{i:02d}:00.000Z", v))
        for i in range(6):
            repo.insert(_reading("motor_current", f"2026-05-30T12:00:{i:02d}.000Z", 0.5))

        stat_detectors: list[Detector] = [
            ThreeSigma(current_window_s=60, sigma_k=3.0, min_baseline=30, min_current=5)
        ]
        active: dict[str, frozenset[str]] = {}
        _detect_once(repo, [(stat_detectors, _BIG_WINDOW_S)], active, datetime(2026, 5, 30, 12, 0, 10, tzinfo=UTC))

        assert repo.fetch_recent_anomalies(limit=10) == []
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/integration/test_statistical_detector.py -q`
Expected: PASS (2 passed). (build_window `_BIG_WINDOW_S` ile tüm geçmişi alır; ThreeSigma son 60s'i güncel ayırır; baseline 40 satır ≥30, güncel 6 ≥5 → fires. İlk testte temp_high de tetiklenir → fused(2).)

- [ ] **Step 3: Full gate**

Run:
```bash
.venv/bin/python -m pytest -q
MYPYPATH=src .venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/dashboard tests/unit tests/integration tests/scenarios
ruff check src/detectors tests/unit tests/integration
```
Expected: tümü PASS (1 smoke skipped), mypy + ruff temiz.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_statistical_detector.py
git commit -m "test(detectors): istatistiksel uçtan-uca (ThreeSigma tespit + fusion) (Faz 5 Iter 5.1)"
```

---

## Controller Closure (subagent task'larından SONRA — sen yaparsın)

1. **Manuel/canlı smoke (kısaltılmış baseline):** `config/detectors.yaml`'da `statistical.baseline_window_s`'i smoke için DÜŞÜR (örn. 120s) ki istatistik 1 saat beklemeden tetiklensin; ya da geçmiş seed et. Simulator (device_002 mechanical_wear) + ingestion + detectors → `three_sigma:motor_current` anomalisi `anomalies` tablosunda + kural `motor_current_high` ile `fused(N)` (overlap kanıtı). `sqlite3 ... "SELECT rule_name FROM anomalies"`. NOT: prod default `baseline_window_s=3600` (1h) — gerçek warmup.
2. **Doküman:** CLAUDE.md "Mevcut Faz" → Faz 5 Iter 5.1 closure (statistical paket, iki-pencere servis, ThreeSigma). ROADMAP § Faz 5 ilerleme.
3. **Memory:** `project_active_phase` → Iter 5.1 DONE, Iter 5.2 (IQR + imza + overlap) next; statistical runtime contract.
4. **Final whole-iteration review.**
5. **Push YAPMA** — kullanıcı onayı al.

---

## Self-Review (writing-plans)

**Spec coverage (Iter 5.1 maddeleri, spec § 3):**
- `statistical/base.py` (split_recent + group iter) → T1 ✓
- `ThreeSigma` + STATISTICAL_REGISTRY → T2 ✓
- `StatisticalConfig` + `build_statistical_detectors` + example bloğu → T3 ✓
- `_detect_once` iki-pencere (detector_groups) + `run()` → T4 ✓
- İstatistiksel uçtan-uca (tespit + fusion) → T5 ✓ (A/B/C imza + overlap Iter 5.2)

**Tip/imza tutarlılığı:** `split_recent(window, current_window_s) -> (df, df)` + `iter_sensor_state_groups(baseline, current, sensors, min_baseline, min_current)` (T1) → `ThreeSigma.detect` (T2) kullanır. `ThreeSigma(current_window_s, sigma_k, min_baseline, min_current, sensors, severity)` (T2) → `build_statistical_detectors` `factory(severity=, current_window_s=, **params)` (T3) ile uyumlu (params: sigma_k/min_baseline/min_current; current_window_s ayrı geçer; severity ayrı). `StatisticalConfig(baseline_window_s, current_window_s, detectors)` (T3) → `run()` `detector_config.statistical.baseline_window_s` (T4). `_detect_once(repo, detector_groups: list[tuple[list[Detector], int]], active, now)` (T4) → T5 integration + güncellenmiş unit testler aynı imza. `fuse_anomalies` + `active` debounce DEĞİŞMEZ.

**Placeholder taraması:** Her kod adımı tam; baseline varyanslı (σ>0) seed'ler açık (sabit→σ=0 koruması ayrı test). example'da yalnız three_sigma (iqr 5.2). Refaktör testleri davranış-korur (mekanik sarmalama).

**Bağımlılık sırası:** T1 (base) → T2 (ThreeSigma, base'e bağlı) → T3 (config, registry'ye bağlı) → T4 (service, build_statistical_detectors'a bağlı) → T5 (integration, hepsine bağlı). Doğru.

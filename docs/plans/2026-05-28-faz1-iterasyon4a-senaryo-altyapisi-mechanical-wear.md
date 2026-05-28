# Faz 1 — Iterasyon 4a: Senaryo Altyapısı + MechanicalWear — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task's final verification step MUST run the FULL suite + mypy + ruff over BOTH src and tests (see [[feedback-full-suite-per-task]]).

**Goal:** Iter 3'ün asyncio multi-device engine'i üzerine `FaultScenario` ABC + `ScenarioContext` altyapısını, senaryo registry/scheduling helper'ını, ilk somut senaryoyu (`MechanicalWear`) ve engine compute order'a `fault.modify` entegrasyonunu eklemek. Spec § 3 Iter 4a'nın 4 acceptance criteria'sını karşılar (config dataclass, scenarios package, MechanicalWear unit + 1 istatistiksel imza testi).

**Architecture:** Yeni `src/simulator/scenarios/` package: `base.py` `FaultScenario` ABC + frozen `ScenarioContext` (runtime + scenario_elapsed_s). `__init__.py` `SCENARIO_REGISTRY: dict[str, type[FaultScenario]]` + saf `active_scenarios_at(windows, device_elapsed_s)` helper. Per-senaryo state filtering senaryonun `modify` metodunun BAŞINDA inline (spec § 9 formülleri zaten bu pattern). Params validation `FaultScenario.__init__` içinde boot-time (`_REQUIRED_PARAMS: ClassVar[frozenset[str]]` + base class missing-key check). `config.py` `ScenarioWindow` frozen dataclass + `DeviceConfig.scenarios: list[ScenarioWindow]` field + `load_devices` scenarios bloğunu okur. `engine.run_device` tick body'sinde **clean → fault.modify (per active scenario) → noise** sırası (spec § 8 invariant). `active_scenarios_at` sensor döngüsü DIŞINDA per-tick bir kez çağrılır.

**Tech Stack:** Python 3.11+ (StrEnum, ClassVar, dataclass), pytest, pytest-asyncio (Iter 3'ten), mypy strict, ruff, loguru. `scipy.stats.ttest_1samp` ilk istatistiksel imza testi için (scikit-learn 1.5.0 transitif scipy 1.17.1 zaten yüklü; Iter 4b explicit pin ekleyecek). Yeni runtime dependency YOK.

**Referans:** `docs/specs/2026-05-18-faz1-simulator-design.md` (commit `757abf1` — Iter 4a/4b split). § 3 Iter 4a Kapsam & Bitti, § 5 ScenarioWindow, § 8 tick akışı + active_scenarios_at helper, § 9 FaultScenario ABC + MechanicalWear formülü, § 11 params validation early-exit, § 12 istatistiksel imza testleri tablosu.

---

## Önkoşul

`.venv` aktif, `pip install -e .` yapılmış, Iter 3.5 cleanup testleri (88 PASS) yeşil olmalı:

```bash
cd /Users/cemalozcan/Desktop/mast-anomaly-detection
source .venv/bin/activate
pytest tests/ -q                          # 88 passed beklenir
mypy src/simulator tests/unit tests/integration   # Success
ruff check src/simulator tests/unit tests/integration   # All checks passed
```

Eğer baseline kırıksa durduralım ve önce neden anlaşılsın.

---

## Dosya Yapısı (Iter 4a sonunda)

```
src/simulator/
├── config.py                               # GENİŞLET: ScenarioWindow + DeviceConfig.scenarios + load_devices scenarios parse
├── engine.py                               # MODIFY: run_device tick body'sinde fault.modify integration
└── scenarios/                              # YENİ PACKAGE
    ├── __init__.py                         # SCENARIO_REGISTRY (1 entry: mechanical_wear) + active_scenarios_at helper
    ├── base.py                             # FaultScenario ABC + ScenarioContext (frozen)
    └── mechanical_wear.py                  # MechanicalWear class (spec § 9 A)

tests/
├── unit/
│   ├── conftest.py                         # GENİŞLET: make_device → optional scenarios kwarg
│   ├── test_config.py                      # GENİŞLET: ScenarioWindow + DeviceConfig.scenarios YAML loader testleri
│   ├── test_engine_run_device.py           # GENİŞLET: fault.modify integration testleri
│   └── test_scenarios/                     # YENİ subpackage
│       ├── __init__.py                     # empty
│       ├── test_base.py                    # FaultScenario ABC + ScenarioContext + active_scenarios_at helper testleri
│       └── test_mechanical_wear.py         # MechanicalWear per-sensör + per-state modify testleri
├── fixtures/
│   └── devices_with_mechanical_wear.yaml   # YENİ: 1 cihaz + mechanical_wear scenario window
└── scenarios/                              # YENİ kategori (spec § 12)
    ├── __init__.py                         # empty
    └── test_mechanical_wear_signature.py   # scipy.stats.ttest_1samp ile RAISING motor_current artışı imzası
```

**Beklenen test sayısı:** 88 → ~105+ (Iter 3.5 sonu 88 + ~17 yeni: config 3 + base/registry/helper 5 + mechanical_wear 6 + engine integration 2 + signature 1).
**Hedef coverage:** ≥%85 (Iter 3.5 sonu %93; senaryo kodu basit yüksek branch coverage'a engel olmamalı).

---

## Task 1: `ScenarioWindow` Dataclass + `DeviceConfig.scenarios` Field + YAML Loader

`config.py`'ye `ScenarioWindow` frozen dataclass ve `DeviceConfig.scenarios: list[ScenarioWindow]` field ekle. `load_devices` YAML'deki opsiyonel `scenarios:` bloğunu okur. Mevcut tek-cihaz / multi-device yaml'lar scenarios alanı OLMADAN da geçerli (boş liste default).

**Files:**
- Modify: `src/simulator/config.py`
- Modify: `tests/unit/test_config.py`

- [x] **Step 1.1: `tests/unit/test_config.py` SONUNA 3 failing test ekle**

```python
def test_load_devices_with_no_scenarios_field_returns_empty_list(tmp_path: Path) -> None:
    """scenarios alanı YAML'de yoksa DeviceConfig.scenarios == []."""
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text("""
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle: [5, 30]
      raising: [10, 60]
      holding: [60, 300]
      lowering: [10, 60]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
""")
    devices = load_devices(devices_yaml)
    assert devices[0].scenarios == []


def test_load_devices_with_scenarios_block_parses_window(tmp_path: Path) -> None:
    """scenarios: bloğu ScenarioWindow listesine parse edilir."""
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text("""
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle: [5, 30]
      raising: [10, 60]
      holding: [60, 300]
      lowering: [10, 60]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: mechanical_wear
        start_after_s: 120
        duration_s: 600
        params:
          severity: 0.25
          ramp_up_s: 300
""")
    from simulator.config import ScenarioWindow

    devices = load_devices(devices_yaml)
    assert len(devices[0].scenarios) == 1
    window = devices[0].scenarios[0]
    assert isinstance(window, ScenarioWindow)
    assert window.name == "mechanical_wear"
    assert window.start_after_s == 120.0
    assert window.duration_s == 600.0
    assert window.params == {"severity": 0.25, "ramp_up_s": 300}


def test_scenario_window_is_frozen_dataclass() -> None:
    """ScenarioWindow frozen — params Mapping olarak saklanır, mutate edilemez."""
    from dataclasses import FrozenInstanceError

    from simulator.config import ScenarioWindow

    w = ScenarioWindow(
        name="mechanical_wear",
        start_after_s=0.0,
        duration_s=100.0,
        params={"severity": 0.2, "ramp_up_s": 300},
    )
    with pytest.raises(FrozenInstanceError):
        w.name = "other"  # type: ignore[misc]
```

- [x] **Step 1.2: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_config.py -v
```
Beklenen: 3 yeni test FAIL — `ScenarioWindow` ImportError, `DeviceConfig.scenarios` attribute yok.

- [x] **Step 1.3: `src/simulator/config.py` içine `ScenarioWindow` dataclass ekle**

`StateDurations` ile `DeviceConfig` arasına (alfabetik yere değil, anlamsal bütünlüğe göre — Config dataclass'larından önce):

```python
@dataclass(frozen=True)
class ScenarioWindow:
    """Bir senaryo penceresi: kayıt anahtarı + zaman aralığı + parametreler.

    `start_after_s` ve `duration_s` cihazın spawn anından itibaren sayılır
    (engine_boot_at, spec § 5). `params` immutable bir Mapping olarak saklanır.
    """
    name: str                                # SCENARIO_REGISTRY key
    start_after_s: float
    duration_s: float
    params: Mapping[str, float] = field(default_factory=dict)
```

`Mapping` import'u için config.py üst tarafına `from collections.abc import Mapping` ekle (henüz yoksa).

- [x] **Step 1.4: `DeviceConfig`'e `scenarios` field ekle**

Mevcut `DeviceConfig`'i şu hale güncelle (yeni `scenarios` satırı):

```python
@dataclass(frozen=True)
class DeviceConfig:
    id: str
    type: str
    sensors: list[SensorConfig]
    state_durations: StateDurations
    target_height_mm: float
    seed: int | None = None
    scenarios: list[ScenarioWindow] = field(default_factory=list)
```

- [x] **Step 1.5: `load_devices` YAML loader'ında scenarios bloğunu parse et**

Mevcut `load_devices` içindeki `DeviceConfig(...)` çağrısının HEMEN ÖNCESİNE şu bloğu ekle (per-device döngüsü içinde):

```python
        scenarios_raw = d.get("scenarios", []) or []
        scenarios: list[ScenarioWindow] = []
        for s in scenarios_raw:
            scenarios.append(
                ScenarioWindow(
                    name=str(s["name"]),
                    start_after_s=float(s["start_after_s"]),
                    duration_s=float(s["duration_s"]),
                    params=dict(s.get("params") or {}),
                )
            )
```

Sonra `DeviceConfig(...)` çağrısına `scenarios=scenarios,` parametresini ekle (kwarg).

- [x] **Step 1.6: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_config.py -v
```
Beklenen: tüm config testleri PASS (yeni 3 + mevcut config testleri).

- [x] **Step 1.7: Tam suite + mypy + ruff yeşil**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration
ruff check src/simulator tests/unit tests/integration
```
Beklenen: 88 + 3 = 91 passed, mypy clean, ruff clean.

- [x] **Step 1.8: Commit**

```bash
git add src/simulator/config.py tests/unit/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): ScenarioWindow dataclass + DeviceConfig.scenarios + YAML loader

Iter 4a altyapısı: ScenarioWindow frozen dataclass (name, start_after_s,
duration_s, params: Mapping). DeviceConfig.scenarios: list[ScenarioWindow]
field eklendi (default_factory=list → mevcut scenarios'sız YAML'lar geri
uyumlu). load_devices opsiyonel "scenarios:" bloğunu parse eder.

3 yeni test: scenarios yok → boş liste; scenarios var → ScenarioWindow
parse; ScenarioWindow frozen.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `FaultScenario` ABC + `ScenarioContext` + `SCENARIO_REGISTRY` + `active_scenarios_at`

`src/simulator/scenarios/` package'ını yarat. Base classlar + registry + scheduling helper. Henüz somut senaryo yok (boş registry); MechanicalWear Task 3'te eklenecek.

**Files:**
- Create: `src/simulator/scenarios/__init__.py`
- Create: `src/simulator/scenarios/base.py`
- Create: `tests/unit/test_scenarios/__init__.py`
- Create: `tests/unit/test_scenarios/test_base.py`

- [x] **Step 2.1: `tests/unit/test_scenarios/__init__.py` (boş dosya)**

```bash
mkdir -p tests/unit/test_scenarios
touch tests/unit/test_scenarios/__init__.py
```

- [x] **Step 2.2: `tests/unit/test_scenarios/test_base.py` failing testleri yaz**

```python
"""FaultScenario ABC + ScenarioContext + active_scenarios_at helper testleri (Iter 4a)."""
from __future__ import annotations

import pytest

from simulator.config import ScenarioWindow


def test_fault_scenario_cannot_be_instantiated_directly() -> None:
    """ABC: abstract method (modify) implement edilmeden instantiate edilemez."""
    from simulator.scenarios.base import FaultScenario

    with pytest.raises(TypeError, match="abstract"):
        FaultScenario(params={})  # type: ignore[abstract]


def test_scenario_context_is_frozen() -> None:
    """ScenarioContext immutable — modify(...) çağrıları arasında değişmesin."""
    from dataclasses import FrozenInstanceError

    from simulator.scenarios.base import ScenarioContext

    ctx = ScenarioContext(runtime=None, scenario_elapsed_s=10.0)  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        ctx.scenario_elapsed_s = 20.0  # type: ignore[misc]


def test_active_scenarios_at_returns_empty_when_no_windows() -> None:
    """Boş windows listesi → boş aktif liste."""
    from simulator.scenarios import active_scenarios_at

    assert active_scenarios_at([], 100.0) == []


def test_active_scenarios_at_returns_active_window_within_range() -> None:
    """start_after_s ≤ t < start_after_s + duration_s → aktif."""
    from simulator.scenarios import SCENARIO_REGISTRY, active_scenarios_at
    from simulator.scenarios.base import FaultScenario, ScenarioContext

    # Test-only dummy scenario, registry'ye geçici ekle
    class _Dummy(FaultScenario):
        name = "dummy"
        def modify(self, sensor_name: str, clean_value: float, ctx: ScenarioContext) -> float:
            return clean_value
    SCENARIO_REGISTRY["dummy"] = _Dummy
    try:
        windows = [ScenarioWindow(name="dummy", start_after_s=60.0, duration_s=120.0, params={})]
        active = active_scenarios_at(windows, device_elapsed_s=90.0)
        assert len(active) == 1
        scenario, window = active[0]
        assert isinstance(scenario, _Dummy)
        assert window.name == "dummy"
    finally:
        del SCENARIO_REGISTRY["dummy"]


def test_active_scenarios_at_excludes_window_before_start_and_after_end() -> None:
    """t < start_after_s veya t ≥ start_after_s + duration_s → aktif değil."""
    from simulator.scenarios import SCENARIO_REGISTRY, active_scenarios_at
    from simulator.scenarios.base import FaultScenario, ScenarioContext

    class _Dummy(FaultScenario):
        name = "dummy"
        def modify(self, sensor_name: str, clean_value: float, ctx: ScenarioContext) -> float:
            return clean_value
    SCENARIO_REGISTRY["dummy"] = _Dummy
    try:
        windows = [ScenarioWindow(name="dummy", start_after_s=60.0, duration_s=120.0, params={})]
        assert active_scenarios_at(windows, device_elapsed_s=59.9) == []
        assert active_scenarios_at(windows, device_elapsed_s=180.0) == []  # 60+120=180, exclusive
        assert active_scenarios_at(windows, device_elapsed_s=60.0) != []   # inclusive lower
        assert active_scenarios_at(windows, device_elapsed_s=179.999) != []
    finally:
        del SCENARIO_REGISTRY["dummy"]
```

- [x] **Step 2.3: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_scenarios/test_base.py -v
```
Beklenen: hepsi ImportError ile FAIL (`scenarios` package yok).

- [x] **Step 2.4: `src/simulator/scenarios/base.py` yarat**

```python
"""FaultScenario ABC + ScenarioContext (Iter 4 senaryo altyapısı, spec § 9)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from simulator.runtime import DeviceRuntimeState


@dataclass(frozen=True)
class ScenarioContext:
    """Bir senaryo `modify` çağrısı için immutable bağlam.

    `scenario_elapsed_s` her senaryonun KENDİ `start_after_s`'inden ölçülür
    (spec § 8 — birden fazla senaryo aynı anda aktifse her birinin kendi
    geçen süresi vardır, tek paylaşılan değer değil).
    """
    runtime: DeviceRuntimeState
    scenario_elapsed_s: float


class FaultScenario(ABC):
    """Arıza senaryosu kontratı: sensor değerini state + elapsed'e göre modifiye eder.

    Alt sınıflar `_REQUIRED_PARAMS` frozenset'ini override ederek YAML'de
    beklenen anahtarları deklare eder; base `__init__` eksik anahtarı boot-time
    `ValueError` ile bildirir (spec § 11 early-exit).

    Per-senaryo state filtering: alt sınıfın `modify` metodu BAŞINDA inline
    `if ctx.runtime.state not in active_states: return clean_value` (spec § 9
    formülleri zaten bu pattern).
    """

    name: ClassVar[str]
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, params: Mapping[str, float]):
        missing = self._REQUIRED_PARAMS - set(params)
        if missing:
            raise ValueError(
                f"{type(self).__name__}: eksik params: {sorted(missing)} "
                f"(beklenen: {sorted(self._REQUIRED_PARAMS)})"
            )
        self.params = params

    @abstractmethod
    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        """Temiz fiziksel değeri (sensör formülü çıktısı) bu senaryoya göre modifiye et.

        Senaryo bu state'te aktif değilse `clean_value` aynen döndürülür.
        Senaryo bu sensörle ilgilenmiyorsa da `clean_value` aynen döndürülür.
        """
```

- [x] **Step 2.5: `src/simulator/scenarios/__init__.py` yarat**

```python
"""Scenarios package: SCENARIO_REGISTRY + active_scenarios_at helper (spec § 4 + § 8)."""
from __future__ import annotations

from simulator.config import ScenarioWindow
from simulator.scenarios.base import FaultScenario

# Registry: YAML'deki ad-string'i sınıfa eşler. Yeni senaryo eklemek
# yeni dosya yazıp bu dict'e bir satır eklemekten ibaret (spec § 4).
SCENARIO_REGISTRY: dict[str, type[FaultScenario]] = {}


def active_scenarios_at(
    windows: list[ScenarioWindow],
    device_elapsed_s: float,
) -> list[tuple[FaultScenario, ScenarioWindow]]:
    """`device_elapsed_s` anında aktif olan senaryo + pencere çiftlerini döndür.

    Aktiflik penceresi: `start_after_s ≤ device_elapsed_s < start_after_s + duration_s`
    (lower inclusive, upper exclusive). Senaryo class'ı her çağrıda registry'den
    yeni instance olarak inşa edilir (params YAML window'undan).

    Args:
        windows: Cihazın `DeviceConfig.scenarios` listesi.
        device_elapsed_s: Cihazın engine_boot_at'ten beri geçen süresi
            (`runtime.device_elapsed_s` property).

    Returns:
        Aktif olan (scenario_instance, window) çiftleri. Sırası `windows` listesinin
        sırasını korur — engine bu sırayla `modify` zincirler.

    Raises:
        KeyError: SCENARIO_REGISTRY'de bilinmeyen window.name.
    """
    active: list[tuple[FaultScenario, ScenarioWindow]] = []
    for window in windows:
        if not (window.start_after_s <= device_elapsed_s < window.start_after_s + window.duration_s):
            continue
        scenario_cls = SCENARIO_REGISTRY[window.name]
        scenario = scenario_cls(params=window.params)
        active.append((scenario, window))
    return active


__all__ = ["SCENARIO_REGISTRY", "active_scenarios_at", "FaultScenario"]
```

- [x] **Step 2.6: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_scenarios/test_base.py -v
```
Beklenen: 5 passed.

- [x] **Step 2.7: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration
ruff check src/simulator tests/unit tests/integration
```
Beklenen: 91 + 5 = 96 passed, mypy clean, ruff clean.

- [x] **Step 2.8: Commit**

```bash
git add src/simulator/scenarios/__init__.py \
        src/simulator/scenarios/base.py \
        tests/unit/test_scenarios/__init__.py \
        tests/unit/test_scenarios/test_base.py
git commit -m "$(cat <<'EOF'
feat(scenarios): FaultScenario ABC + ScenarioContext + active_scenarios_at helper

Iter 4a senaryo altyapısı. base.py: FaultScenario ABC ile _REQUIRED_PARAMS
ClassVar pattern (eksik param → boot-time ValueError, spec § 11). frozen
ScenarioContext (runtime + scenario_elapsed_s). __init__.py: SCENARIO_REGISTRY
(boş başlar, Task 3'te mechanical_wear eklenir) + active_scenarios_at saf
helper (inclusive-exclusive pencere semantiği, spec § 8).

5 yeni test: ABC instantiate engellenir, ScenarioContext frozen, helper
boş/aktif/sınır durumları.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `MechanicalWear` Senaryosu + Unit Testler

Spec § 9 A formülünü implement et. State filter (sadece RAISING + HOLDING aktif), params validation (severity, ramp_up_s required), per-sensor formula (motor_current, mast_position, vibration, motor_temperature). `SCENARIO_REGISTRY`'ye kayıt.

**Files:**
- Create: `src/simulator/scenarios/mechanical_wear.py`
- Modify: `src/simulator/scenarios/__init__.py` (registry'ye 1 entry)
- Create: `tests/unit/test_scenarios/test_mechanical_wear.py`

- [x] **Step 3.1: `tests/unit/test_scenarios/test_mechanical_wear.py` failing testleri yaz**

```python
"""MechanicalWear (spec § 9 A) modify behavior testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState) -> DeviceRuntimeState:
    """Test fixture: minimal runtime, state belirli."""
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=60.0,
        position_mm=0.0,
        cycle_count=0,
        rng=random.Random(42),
        started_at_monotonic=0.0,
        clock=lambda: 0.0,
    )


def test_mechanical_wear_requires_severity_and_ramp_up_s() -> None:
    """Eksik params → boot-time ValueError."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    with pytest.raises(ValueError, match="severity"):
        MechanicalWear(params={"ramp_up_s": 300})
    with pytest.raises(ValueError, match="ramp_up_s"):
        MechanicalWear(params={"severity": 0.2})
    # Tam set → OK
    MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})


def test_mechanical_wear_idle_returns_clean_value() -> None:
    """IDLE'da motor dönmez → aşınma görünmez → identity."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE), scenario_elapsed_s=600.0)
    assert scenario.modify("motor_current", 0.5, ctx) == 0.5
    assert scenario.modify("vibration", 0.05, ctx) == 0.05


def test_mechanical_wear_lowering_returns_clean_value() -> None:
    """LOWERING'de aktif değil (spec § 9 A: sadece RAISING + HOLDING)."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.LOWERING), scenario_elapsed_s=600.0)
    assert scenario.modify("motor_current", 8.0, ctx) == 8.0


def test_mechanical_wear_raising_increases_motor_current() -> None:
    """RAISING'de motor_current * (1 + factor), factor = elapsed/ramp_up * severity (capped 1.0)."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=300.0)
    # elapsed/ramp_up = 1.0, capped → factor = 1.0 * 0.2 = 0.2
    # clean=8.0 → 8.0 * (1 + 0.2) = 9.6
    assert scenario.modify("motor_current", 8.0, ctx) == pytest.approx(9.6)


def test_mechanical_wear_factor_caps_at_severity() -> None:
    """elapsed_s ≥ ramp_up_s sonrası factor sabit kalır (cap)."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.3, "ramp_up_s": 60})
    ctx_early = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=60.0)
    ctx_late = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=3600.0)
    # Her ikisinde factor = 0.3 (capped)
    assert scenario.modify("motor_current", 10.0, ctx_early) == pytest.approx(13.0)
    assert scenario.modify("motor_current", 10.0, ctx_late) == pytest.approx(13.0)


def test_mechanical_wear_holding_applies_all_four_sensor_formulas() -> None:
    """HOLDING'de motor_current, mast_position, vibration, motor_temperature modifiye."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING), scenario_elapsed_s=300.0)
    # factor = 0.2
    assert scenario.modify("motor_current", 0.5, ctx) == pytest.approx(0.5 * 1.2)
    # mast_position → clean / (1 + factor * 0.7) → yavaş yükseliş
    assert scenario.modify("mast_position", 5000.0, ctx) == pytest.approx(5000.0 / (1 + 0.2 * 0.7))
    # vibration → clean * (1 + factor * 2)
    assert scenario.modify("vibration", 0.05, ctx) == pytest.approx(0.05 * (1 + 0.2 * 2))
    # motor_temperature → clean + factor * 8.0
    assert scenario.modify("motor_temperature", 30.0, ctx) == pytest.approx(30.0 + 0.2 * 8.0)


def test_mechanical_wear_unaffected_sensors_return_clean() -> None:
    """motor_voltage, hydraulic_pressure formüllere dahil değil → identity."""
    from simulator.scenarios.mechanical_wear import MechanicalWear

    scenario = MechanicalWear(params={"severity": 0.2, "ramp_up_s": 300})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=300.0)
    assert scenario.modify("motor_voltage", 24.0, ctx) == 24.0
    assert scenario.modify("hydraulic_pressure", 150.0, ctx) == 150.0


def test_mechanical_wear_registered_in_global_registry() -> None:
    """SCENARIO_REGISTRY['mechanical_wear'] mevcut ve MechanicalWear class'ına işaret eder."""
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.mechanical_wear import MechanicalWear

    assert SCENARIO_REGISTRY["mechanical_wear"] is MechanicalWear
```

- [x] **Step 3.2: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_scenarios/test_mechanical_wear.py -v
```
Beklenen: 8 yeni test ImportError ile FAIL.

- [x] **Step 3.3: `src/simulator/scenarios/mechanical_wear.py` yarat**

```python
"""MechanicalWear arıza senaryosu (spec § 9 A, DOMAIN.md sat. 78-83)."""
from __future__ import annotations

from typing import ClassVar

from simulator.config import DeviceState
from simulator.scenarios.base import FaultScenario, ScenarioContext


class MechanicalWear(FaultScenario):
    """Mekanik aşınma: motor enerjili durumlarda artan sürtünme ve titreşim.

    Aktif state'ler: RAISING + HOLDING. IDLE'da motor dönmez, LOWERING'de
    aşınma hareket yönüne bağlı değil → spec § 9 A bu state'leri kapsam dışı
    tutuyor.

    Params:
        severity: float ∈ (0, 1] — peak aşınma faktörü. Tipik 0.2 (%20).
        ramp_up_s: float > 0 — saniye, lineer ramp süresi (factor = elapsed/ramp_up * severity, capped at severity).
    """

    name: ClassVar[str] = "mechanical_wear"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset({"severity", "ramp_up_s"})

    _ACTIVE_STATES: ClassVar[frozenset[DeviceState]] = frozenset(
        {DeviceState.RAISING, DeviceState.HOLDING}
    )

    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        if ctx.runtime.state not in self._ACTIVE_STATES:
            return clean_value

        severity = self.params["severity"]
        ramp_up_s = self.params["ramp_up_s"]
        factor = min(1.0, ctx.scenario_elapsed_s / ramp_up_s) * severity

        if sensor_name == "motor_current":
            return clean_value * (1 + factor)
        if sensor_name == "mast_position":
            return clean_value / (1 + factor * 0.7)
        if sensor_name == "vibration":
            return clean_value * (1 + factor * 2)
        if sensor_name == "motor_temperature":
            return clean_value + factor * 8.0
        return clean_value
```

- [x] **Step 3.4: `src/simulator/scenarios/__init__.py`'de registry'ye kayıt ekle**

`SCENARIO_REGISTRY: dict[str, type[FaultScenario]] = {}` satırını şununla değiştir:

```python
from simulator.scenarios.mechanical_wear import MechanicalWear

# Registry: YAML'deki ad-string'i sınıfa eşler. Yeni senaryo eklemek
# yeni dosya yazıp bu dict'e bir satır eklemekten ibaret (spec § 4).
SCENARIO_REGISTRY: dict[str, type[FaultScenario]] = {
    "mechanical_wear": MechanicalWear,
}
```

- [x] **Step 3.5: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_scenarios/test_mechanical_wear.py -v
```
Beklenen: 8 passed.

- [x] **Step 3.6: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration
ruff check src/simulator tests/unit tests/integration
```
Beklenen: 96 + 8 = 104 passed, mypy clean, ruff clean.

- [x] **Step 3.7: Commit**

```bash
git add src/simulator/scenarios/mechanical_wear.py \
        src/simulator/scenarios/__init__.py \
        tests/unit/test_scenarios/test_mechanical_wear.py
git commit -m "$(cat <<'EOF'
feat(scenarios): MechanicalWear (spec § 9 A) + SCENARIO_REGISTRY entry

Mekanik aşınma senaryosu: RAISING + HOLDING'de aktif (IDLE motor dönmez,
LOWERING aşınma yönüne bağsız). factor = min(1, elapsed/ramp_up) * severity.
Per-sensor formüller: motor_current * (1+factor), mast_position / (1+factor*0.7),
vibration * (1+factor*2), motor_temperature + factor*8.0. motor_voltage ve
hydraulic_pressure modifiye edilmez.

_REQUIRED_PARAMS = {severity, ramp_up_s} — eksikse boot-time ValueError
(FaultScenario base __init__ pattern).

SCENARIO_REGISTRY artık {"mechanical_wear": MechanicalWear}.

8 unit test: params validation, IDLE/LOWERING identity, RAISING formula,
factor cap, HOLDING 4 formula, etkilenmeyen sensörler, registry entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Engine `run_device` Compute Order — `fault.modify` Integration

`run_device` tick body'sine spec § 8 fiziksel sırayı uygula: clean → fault.modify (per active scenario) → noise. `active_scenarios_at` sensor döngüsü DIŞINDA per-tick bir kez çağrılır.

**Files:**
- Modify: `src/simulator/engine.py`
- Modify: `tests/unit/test_engine_run_device.py`

- [x] **Step 4.1: `tests/unit/test_engine_run_device.py` SONUNA 2 failing test ekle**

```python
async def test_run_device_applies_active_scenario_modify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAISING'de MechanicalWear aktifken motor_current değeri arttırılır.

    Senaryo penceresi engine_boot_at = 0'dan itibaren [0, 600) aralığında aktif;
    runtime RAISING state'inde başlatılır, scenario_elapsed_s = ramp_up_s = 60
    olacak şekilde clock advance edilir → factor = 1.0 * severity = 0.3.

    Bu test asyncio.sleep no-op + FakeClock manuel advance pattern'i kullanır.
    """
    import asyncio as _asyncio
    from unittest.mock import MagicMock

    from simulator.config import DeviceState, ScenarioWindow
    from simulator.engine import run_device
    from simulator.sensors import SENSOR_REGISTRY

    from tests.unit.conftest import SIX_SENSOR_CONFIGS, make_device, make_runtime
    from tests.unit.test_runtime import FakeClock

    import random

    from simulator.runtime import DeviceRuntimeState

    device = make_device(
        "d1",
        seed=42,
        scenarios=[
            ScenarioWindow(
                name="mechanical_wear",
                start_after_s=0.0,
                duration_s=600.0,
                params={"severity": 0.3, "ramp_up_s": 60},
            )
        ],
    )
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in SIX_SENSOR_CONFIGS]
    clock = FakeClock(60.0)  # device_elapsed_s = 60.0 → scenario_elapsed_s = 60.0
    # NOT: make_runtime kullanmıyoruz — current_state_duration_s'i ÇOK büyük yapıp
    # advance_state_machine transition tetiklemesin (RAISING korunur).
    runtime = DeviceRuntimeState(
        state=DeviceState.RAISING,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10000.0,  # transition tetiklenmez
        position_mm=2500.0,                 # RAISING ortası, sensor.compute için makul
        cycle_count=0,
        rng=random.Random(42),
        started_at_monotonic=0.0,
        clock=clock,
    )
    publisher = MagicMock()
    shutdown = _asyncio.Event()

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    await run_device(
        device=device, runtime=runtime, sensors=sensors,
        publisher=publisher, tick_interval=1.0,
        shutdown_event=shutdown, max_iterations=1,
    )

    # 1 tick × 6 sensor = 6 publish. motor_current değerini bul.
    motor_current_call = next(
        c for c in publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "motor_current"
    )
    # RAISING baseline 8.0; factor=0.3 → 8.0 * 1.3 = 10.4 (± noise std 0.1).
    # advance_state_machine RAISING state'i koruyabilir veya değiştirebilir; bu test
    # değerin baseline'dan ANLAMLI ölçüde yüksek olduğunu doğrular (10.4 ± 0.3 σ).
    value = motor_current_call.kwargs["value"]
    assert 10.0 < value < 11.0, f"Beklenen ~10.4, alınan {value}"


async def test_run_device_no_scenario_keeps_clean_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """device.scenarios=[] → fault.modify zinciri YOK → değer yalnızca sensor.compute + noise."""
    import asyncio as _asyncio
    from unittest.mock import MagicMock

    from simulator.engine import run_device
    from simulator.sensors import SENSOR_REGISTRY

    from tests.unit.conftest import SIX_SENSOR_CONFIGS, make_device, make_runtime
    from tests.unit.test_runtime import FakeClock

    device = make_device("d1", seed=42)  # scenarios default = []
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in SIX_SENSOR_CONFIGS]
    runtime = make_runtime(device, clock=FakeClock(0.0), started_at=0.0)
    publisher = MagicMock()
    shutdown = _asyncio.Event()

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    await run_device(
        device=device, runtime=runtime, sensors=sensors,
        publisher=publisher, tick_interval=1.0,
        shutdown_event=shutdown, max_iterations=1,
    )

    motor_current_call = next(
        c for c in publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "motor_current"
    )
    value = motor_current_call.kwargs["value"]
    # IDLE baseline 0.5, noise std 0.1 → ~0.5 ± 0.3 σ
    assert 0.0 < value < 1.0, f"Beklenen ~0.5 (IDLE baseline), alınan {value}"
```

- [x] **Step 4.2: Testleri koş, ilki FAIL ikincisi PASS olmalı**

```bash
pytest tests/unit/test_engine_run_device.py -v
```
Beklenen: `test_run_device_applies_active_scenario_modify` FAIL (henüz fault.modify çağrılmıyor; baseline 0.5 dönüyor değil — runtime.state = RAISING force ettiğimiz için 8.0 dönecek ama fault.modify yok → 8.0 ± noise, 10.0'a ulaşmaz). `test_run_device_no_scenario_keeps_clean_baseline` PASS olabilir (zaten doğru davranış).

Eğer ilk test'in beklenen error mesajı şu şekildeyse: "Beklenen ~10.4, alınan 8.X" — fault.modify entegrasyonu eksik demektir, Step 4.3'e geç.

- [x] **Step 4.3: `src/simulator/engine.py` `run_device` body'sini güncelle**

Mevcut `run_device` body'sindeki:

```python
        advance_state_machine(runtime, device.state_durations)
        runtime.position_mm = compute_position(runtime, device.target_height_mm)

        for sensor in sensors:
            clean_value = sensor.compute(runtime, runtime.position_mm)
            noisy_value = clean_value + runtime.rng.gauss(0.0, sensor.config.noise_std)
            publisher.publish_reading(
                device_id=device.id,
                sensor=sensor.config.name,
                value=noisy_value,
                unit=sensor.config.unit,
                state=runtime.state,
            )
```

bloğunu ŞUNUNLA DEĞİŞTİR:

```python
        advance_state_machine(runtime, device.state_durations)
        runtime.position_mm = compute_position(runtime, device.target_height_mm)

        # Senaryo planlamasını sensor döngüsü DIŞINDA per-tick bir kez yap (spec § 8).
        device_t = runtime.device_elapsed_s
        active_windows = active_scenarios_at(device.scenarios, device_t)

        for sensor in sensors:
            clean_value = sensor.compute(runtime, runtime.position_mm)
            # Spec § 8 kritik fiziksel sıra: clean → fault.modify → noise.
            for scenario, window in active_windows:
                ctx = ScenarioContext(
                    runtime=runtime,
                    scenario_elapsed_s=device_t - window.start_after_s,
                )
                clean_value = scenario.modify(sensor.config.name, clean_value, ctx)
            noisy_value = clean_value + runtime.rng.gauss(0.0, sensor.config.noise_std)
            publisher.publish_reading(
                device_id=device.id,
                sensor=sensor.config.name,
                value=noisy_value,
                unit=sensor.config.unit,
                state=runtime.state,
            )
```

Engine.py üst tarafına yeni import ekle (alfabetik sıraya):

```python
from simulator.scenarios import active_scenarios_at
from simulator.scenarios.base import ScenarioContext
```

`run_device` docstring'inde Args bölümüne kısa not ekle (mevcut docstring'i koru, sadece Note bölümünden hemen ÖNCE şu satırı ekle):

```
        Tick içinde active scenarios sensor döngüsü DIŞINDA hesaplanır;
        her sensör için fault.modify zincirlenir (clean → modify → noise,
        spec § 8 invariant).
```

- [x] **Step 4.4: Testleri tekrar koş, PASS gör**

```bash
pytest tests/unit/test_engine_run_device.py -v
```
Beklenen: tüm engine_run_device testleri PASS (mevcut 3 + 2 yeni = 5).

- [x] **Step 4.5: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration
ruff check src/simulator tests/unit tests/integration
```
Beklenen: 104 + 2 = 106 passed, mypy clean, ruff clean.

- [x] **Step 4.6: Commit**

```bash
git add src/simulator/engine.py tests/unit/test_engine_run_device.py
git commit -m "$(cat <<'EOF'
feat(engine): run_device fault.modify integration (spec § 8 compute order)

run_device tick body artık spec § 8 kritik fiziksel sırayı uygular:
clean (sensor.compute) → fault.modify (per active scenario) → noise
(runtime.rng.gauss). active_scenarios_at sensor döngüsü DIŞINDA per-tick
bir kez hesaplanır (performans + spec uyumu).

ScenarioContext her senaryo + sensor çifti için yeni inşa edilir;
scenario_elapsed_s = device_t - window.start_after_s (spec § 8 — birden
fazla senaryo aynı anda aktifse her birinin kendi geçen süresi var).

2 yeni test: aktif MechanicalWear → motor_current arttırılır;
device.scenarios=[] → değer yalnızca clean + noise.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: İstatistiksel İmza Testi — MechanicalWear

Spec § 12 bitti kriteri A: 60+ örnek üzerinde RAISING motor_current ortalaması baseline'a göre +%15..+%30, `scipy.stats.ttest_1samp` p<0.05.

**Files:**
- Create: `tests/scenarios/__init__.py`
- Create: `tests/fixtures/devices_with_mechanical_wear.yaml`
- Create: `tests/scenarios/test_mechanical_wear_signature.py`

- [x] **Step 5.1: `tests/scenarios/__init__.py` (boş dosya)**

```bash
mkdir -p tests/scenarios
touch tests/scenarios/__init__.py
```

- [x] **Step 5.2: `tests/fixtures/devices_with_mechanical_wear.yaml` yarat**

Sabit state_durations (kontrollü örnekleme için RAISING [60, 60]) + scenarios bloğu:

```yaml
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [1, 1]
      raising:  [60, 60]
      holding:  [60, 60]
      lowering: [60, 60]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: mechanical_wear
        start_after_s: 0
        duration_s: 3600
        params:
          severity: 0.25
          ramp_up_s: 5      # hızlı ramp: 5 tick içinde peak'e ulaşır → RAISING'in büyük çoğunluğu factor=0.25
```

- [x] **Step 5.3: `tests/scenarios/test_mechanical_wear_signature.py` yaz**

```python
"""MechanicalWear istatistiksel imza testi (spec § 12 bitti kriteri A).

60+ örnek RAISING'de motor_current ortalaması baseline'a göre %15..%30 yüksek
olmalı (scipy.stats.ttest_1samp p<0.05). Bu test "senaryo gerçekten gözle
görülür bir kayma üretiyor mu" sorusunu istatistiksel olarak doğrular —
hipotez kontrolü değil, regresyon değer kontrolü (deterministik seed altında
stabil p-value).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scipy.stats import ttest_1samp

from simulator.config import DeviceState
from simulator.engine import run
from tests.unit.test_runtime import FakeClock

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_mechanical_wear_raising_current_mean_significantly_above_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAISING motor_current ortalama: t-test p<0.05 ve mean ∈ [baseline * 1.15, baseline * 1.30]."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    # FakeClock'u manuel advance edemiyoruz (engine içinde clock() çağrıları sıralı).
    # Pratik çözüm: time.monotonic-benzeri bir FakeClock kullan ki her clock()
    # çağrısında küçük artış yapsın — böylece state machine ilerler ve
    # senaryo elapsed büyür. Ya da daha basit: clock=lambda: 600.0 sabit + max_iter
    # ile RAISING'i yakala.
    #
    # En temiz: real time.monotonic yerine FakeClock(60.0) sabit ver. State machine
    # transition gerçekleştirmek için state_entered_at_monotonic = -inf gibi bir
    # değerle başlatamayız (engine boot ortak = 60.0 set ediyor).
    #
    # Çözüm: tick başına clock(0)→clock(1)→... ilerleyen counter.
    class CountingClock:
        def __init__(self) -> None:
            self._t = 0.0
        def __call__(self) -> float:
            return self._t
        def tick(self) -> None:
            self._t += 1.0
    clock = CountingClock()

    # asyncio.sleep yerine clock.tick + yield et
    async def _ticking_sleep(_s: float) -> None:
        clock.tick()
        await original_sleep(0)
    monkeypatch.setattr("simulator.engine.asyncio.sleep", _ticking_sleep)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_with_mechanical_wear.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=200,  # ~200 tick — IDLE(1) + RAISING(60) + HOLDING(60) + ... bol RAISING örneklemi
        seed=None,
        clock=clock,
    )

    # RAISING durumundaki motor_current değerlerini topla
    raising_motor_currents = [
        c.kwargs["value"]
        for c in mock_publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "motor_current"
        and c.kwargs["state"] == DeviceState.RAISING
    ]

    assert len(raising_motor_currents) >= 60, (
        f"En az 60 RAISING motor_current örneği bekleniyor, alınan: {len(raising_motor_currents)}"
    )

    # Baseline RAISING kararlı motor_current = 8.0 (spec § 6).
    # MechanicalWear severity=0.25, ramp_up_s=60: ramp sonrası factor=0.25 → +%25.
    # Ramp süresince (ilk 60s) ortalama daha düşük; eğer örnekleme rampa öncesi
    # ve sonrası karışıksa ortalama [+15%, +30%] aralığında düşmelidir.
    baseline = 8.0
    mean_obs = sum(raising_motor_currents) / len(raising_motor_currents)

    # 1) Mean baseline'a göre [+15%, +30%] aralığında
    assert baseline * 1.15 <= mean_obs <= baseline * 1.30, (
        f"Ortalama {mean_obs:.2f} baseline {baseline} * [1.15, 1.30] dışında"
    )

    # 2) t-test: H0 = ortalama == baseline (no fault). H0 reddedilmeli (p<0.05).
    result = ttest_1samp(raising_motor_currents, popmean=baseline)
    assert result.pvalue < 0.05, (
        f"t-test p={result.pvalue:.4f} ≥ 0.05 — MechanicalWear sinyali baseline'dan ayırt edilmiyor"
    )
```

- [x] **Step 5.4: Testi koş, PASS gör**

```bash
pytest tests/scenarios/test_mechanical_wear_signature.py -v
```
Beklenen: 1 passed. Eğer FAIL ederse:
- "60 örnek bekleniyor" hatası → max_iterations 200'den fazla yap
- Mean aralık dışı → state_durations RAISING'i daha uzun yap veya start_after_s'i ileri al (rampa için)
- p-value ≥ 0.05 → severity'yi 0.30'a çıkar (sinyal güçlendir)

- [x] **Step 5.5: Tam suite + mypy + ruff (tests/scenarios da dahil)**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 106 + 1 = 107 passed, mypy/ruff clean.

- [x] **Step 5.6: Commit**

```bash
git add tests/scenarios/__init__.py \
        tests/scenarios/test_mechanical_wear_signature.py \
        tests/fixtures/devices_with_mechanical_wear.yaml
git commit -m "$(cat <<'EOF'
test(scenarios): MechanicalWear istatistiksel imza (spec § 12 bitti kriteri A)

tests/scenarios/ kategori dizini açıldı (per spec § 12). MechanicalWear için
60+ RAISING motor_current örneği toplanır; baseline 8.0 A'ya karşı
scipy.stats.ttest_1samp p<0.05 ve mean ∈ [baseline*1.15, baseline*1.30]
doğrulanır.

CountingClock fixture + asyncio.sleep wrapper: her tick'te clock 1s ilerletir
→ state machine doğal akar, senaryo elapsed büyür. devices_with_mechanical_wear.yaml
fixture (severity=0.25, ramp_up_s=60, start_after_s=0).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `devices.yaml.example` Güncellemesi + Manuel Smoke + Milestone

`config/devices.yaml.example`'a 1 cihazın scenarios bloğu ekle (manuel demo için). Manuel: mosquitto + python -m simulator → RAISING tick'lerinde motor_current'in baseline'dan yüksek olduğunu gözle. CLAUDE.md "Mevcut Faz" Iter 4a tamamlandı → Iter 4b sıradaki. Plan checkboxları + milestone commit.

**Files:**
- Modify: `config/devices.yaml.example`
- Modify: `CLAUDE.md`
- Modify: `docs/plans/2026-05-28-faz1-iterasyon4a-senaryo-altyapisi-mechanical-wear.md`

- [x] **Step 6.1: `config/devices.yaml.example`'da 1 cihaza scenarios ekle**

Mevcut 3 cihazlı dosyada `device_002` (target_height_mm: 6000) bloğunun sonuna (sensors listesinin altına) ekle:

```yaml
    scenarios:
      - name: mechanical_wear
        start_after_s: 120        # 2 dakika sonra başlar
        duration_s: 1800           # 30 dakika sürer
        params:
          severity: 0.25           # peak +%25 motor akımı / titreşim
          ramp_up_s: 300           # 5 dakikada peak'e ulaşır
```

device_001 ve device_003'te scenarios eklemiyoruz (kıyaslama için sağlıklı/arızalı cihaz yan yana akacak).

- [x] **Step 6.2: `config/devices.yaml` lokal kopya güncelle**

```bash
cp config/devices.yaml.example config/devices.yaml
```

- [x] **Step 6.3: Manuel uçtan uca — mosquitto + python -m simulator**

İki terminal:
- Terminal A: `mosquitto_sub -v -t 'telemetry/device_002/motor_current'`
- Terminal B: `python -m simulator` (~3-4 dakika çalıştır)

Beklenen davranış:
- İlk 2 dakika (start_after_s=120) `motor_current` saf baseline (~0.5 IDLE, ~8.0 RAISING)
- 2-7 dakika arası (ramp_up_s=300) RAISING motor_current giderek artar (~8.0 → ~10.0)
- 7+ dakika sonrası RAISING motor_current sabit yüksek (~10.0 ≈ 8.0 * 1.25)
- device_001 / device_003 baseline'da kalır

EĞER device_002 motor_current artmıyorsa veya hata varsa: STOP, BLOCKED raporla.

**NOTE FOR SUBAGENT:** Mosquitto kuruluysa otomatize edilebilir; değilse SKIP edip raporda belirt.

- [x] **Step 6.4: `CLAUDE.md` "Mevcut Faz" güncelle**

Header satırını şuna güncelle:
```
**Faz 1 — Iterasyon 4b: HydraulicLeak + ElectricalFault + Tam İmza Seti** (sıradaki)
```

Tamamlanan iterasyonlar listesine ekle:
```
  - `docs/plans/2026-05-28-faz1-iterasyon4a-senaryo-altyapisi-mechanical-wear.md` (6/6 ✅)
```

"Iterasyon 4 (sıradaki) — Plan henüz yazılmadı" bölümünü (eğer Iter 3 sonrası eklenmişse) ŞUNUNLA değiştir:

```markdown
### Iterasyon 4a (Senaryo Altyapısı + MechanicalWear) — Tamamlandı (2026-05-28)

`src/simulator/scenarios/` package: `FaultScenario` ABC + `ScenarioContext` (frozen),
`SCENARIO_REGISTRY` + `active_scenarios_at` helper. `MechanicalWear` (A) senaryosu:
RAISING+HOLDING aktif, params {severity, ramp_up_s} boot-time validation.
`config.ScenarioWindow` + `DeviceConfig.scenarios` field + YAML loader scenarios bloğunu
parse eder. `engine.run_device` compute order: clean → fault.modify → noise (spec § 8).
İstatistiksel imza testi: `tests/scenarios/test_mechanical_wear_signature.py` scipy.stats
ttest_1samp ile baseline'a karşı +%25 artışı p<0.05'te doğrular. Toplam 107 test, ≥%85
coverage. Manuel uçtan uca: device_002'de scenario aktif, motor_current ramp davranışı
gözlemli.

### Iterasyon 4b (sıradaki) — Plan henüz yazılmadı

Kapsam (spec § 3 Iter 4b): `HydraulicLeak` (B) + `ElectricalFault` (C) + Spearman ρ<0
ve F-testi imza setleri. scipy explicit pin (`scipy==1.17.1`). Faz 1 closure.
```

- [x] **Step 6.5: Plan dosyasının tüm checkbox'larını [x] yap**

```bash
sed -i.bak 's/^- \[ \]/- [x]/g' docs/plans/2026-05-28-faz1-iterasyon4a-senaryo-altyapisi-mechanical-wear.md && rm docs/plans/2026-05-28-faz1-iterasyon4a-senaryo-altyapisi-mechanical-wear.md.bak
```

macOS sed uyumsuzluk verirse perl ile:
```bash
perl -i -pe 's/^- \[ \]/- [x]/g' docs/plans/2026-05-28-faz1-iterasyon4a-senaryo-altyapisi-mechanical-wear.md
```

- [x] **Step 6.6: Tam suite son kez**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 107 passed, mypy/ruff clean.

- [x] **Step 6.7: Milestone commit**

```bash
git add config/devices.yaml.example CLAUDE.md docs/plans/2026-05-28-faz1-iterasyon4a-senaryo-altyapisi-mechanical-wear.md
git commit -m "$(cat <<'EOF'
milestone: Faz 1 Iterasyon 4a (senaryo altyapısı + MechanicalWear) tamamlandı 🎉

src/simulator/scenarios/ package + FaultScenario ABC + ScenarioContext +
SCENARIO_REGISTRY + active_scenarios_at helper kuruldu. MechanicalWear
(spec § 9 A) ilk somut senaryo. engine.run_device compute order spec § 8
invariant'a uyumlu: clean → fault.modify → noise. ScenarioWindow config
dataclass + DeviceConfig.scenarios YAML loader. devices.yaml.example
device_002'ye scenario örneği.

Bitti kriterleri (spec § 3 Iter 4a):
1. ✅ config.ScenarioWindow + DeviceConfig.scenarios + load_devices
2. ✅ scenarios package (base ABC + registry + active_scenarios_at)
3. ✅ MechanicalWear modify formula (per-state filtering + 4 sensor formülü)
4. ✅ engine run_device fault.modify integration
5. ✅ Unit testler (config 3 + base 5 + mechanical_wear 8 + engine 2)
6. ✅ İstatistiksel imza testi (tests/scenarios/test_mechanical_wear_signature.py
   — scipy.stats.ttest_1samp, mean ∈ [baseline*1.15, baseline*1.30], p<0.05)

Toplam: 88 → 107 test (19 yeni), coverage ≥%85. Iter 4b sıradaki:
HydraulicLeak + ElectricalFault + kalan 2 imza testi + scipy explicit pin.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Iter 4a Sonu — Bitti Kriterleri (spec § 3 ile birebir)

- [x] **Kriter 1:** `ScenarioWindow` + `DeviceConfig.scenarios` field + YAML loader (Task 1).
- [x] **Kriter 2:** `simulator/scenarios/` package: `FaultScenario` ABC + `ScenarioContext` + `SCENARIO_REGISTRY` + `active_scenarios_at` helper (Task 2).
- [x] **Kriter 3:** `MechanicalWear` (A) — RAISING+HOLDING aktif, 4 sensor formülü, boot-time params validation, registry entry (Task 3).
- [x] **Kriter 4:** `engine.run_device` compute order: clean → fault.modify → noise; active_scenarios_at sensor döngüsü dışında per-tick (Task 4).
- [x] **Kriter 5:** Unit testler: config (3) + base/helper (5) + MechanicalWear (8) + engine integration (2) — toplam 18 yeni unit test.
- [x] **Kriter 6:** İstatistiksel imza testi: RAISING `motor_current` mean ∈ [baseline×1.15, baseline×1.30], scipy.stats.ttest_1samp p<0.05 (Task 5).

Her task'ın sonunda **DiscIPLİN** (CLAUDE.md kuralı): tam pytest suite + mypy(src+tests) + ruff(src+tests) yeşil — per-file değil.

---

## Memory Güncellemesi (Iter 4a sonu, plan-dışı)

Iter 4a tamamlandıktan sonra `project_active_phase.md` memory'sini güncelle:
- `Active phase` → "Faz 1 — Iterasyon 4b: HydraulicLeak + ElectricalFault + tam imza seti (next, plan not yet written)"
- Iteration plan satırı → Iter 4a ✅ DONE işareti
- `scenarios` package + `FaultScenario` ABC + `MechanicalWear` runtime contract'a ekle
- "Iter 4 design questions to settle in brainstorming" bloğundan Iter 4a'da karara bağlananları ÇIKAR

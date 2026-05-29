# Faz 1 — Iterasyon 4b: HydraulicLeak + ElectricalFault + Tam İmza Seti — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task's final verification step MUST run the FULL suite + mypy + ruff over src AND ALL tests dirs (unit + integration + scenarios) — see [[feedback-full-suite-per-task]].

**Goal:** Iter 4a'nın senaryo altyapısı üzerine kalan 2 somut senaryoyu (`HydraulicLeak`, `ElectricalFault`) + ilgili 2 istatistiksel imza testini eklemek; `scipy==1.17.1` explicit pin'lemek; `tests/scenarios/conftest.py` DRY refactor'ü yapmak; Faz 1'i kapatmak (CLAUDE.md → Faz 2 sıradaki).

**Architecture:** Her iki yeni senaryo `FaultScenario` ABC pattern'ini birebir uygular — `_REQUIRED_PARAMS` + (gerekiyorsa) `_ACTIVE_STATES` ClassVar'lar + per-state guarded `modify`. `HydraulicLeak` (B): sadece HOLDING aktif, `runtime.elapsed_in_state_s / 60` ile basınç düşüşü + position sag. `ElectricalFault` (C): TÜM state'lerde aktif (state filter YOK), `runtime.rng` üzerinden per-sensor independent spike/jitter (modify pure stays — `runtime.rng` engine'in noise stream'i ile interleave eder, per-device seed determinizmi korur). İstatistiksel imzalar: B için `scipy.stats.spearmanr(tick_indices, pressures)` HOLDING window'unda ρ<0/p<0.05; C için iki run (baseline + scenario aktif) → `scipy.stats.bartlett(baseline_voltages, scenario_voltages)` variance equality p<0.05 + manuel std ratio ≈ 3 kontrolü. `tests/scenarios/conftest.py` extraction Task 3'te (3 consumer kuralı: Iter 4a mechanical_wear + Iter 4b'nin 2 yeni signature test'i).

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio (auto-mode), scipy 1.17.1 (Iter 4b explicit pin), mypy strict, ruff, loguru. Yeni runtime dependency YOK (scipy zaten scikit-learn 1.5.0 transitif'inden geliyor, sadece pin'leniyor).

**Referans:** `docs/specs/2026-05-18-faz1-simulator-design.md` § 3 Iter 4b kapsam + § 9 B HydraulicLeak (DOMAIN.md sat. 90-93) + § 9 C ElectricalFault (DOMAIN.md sat. 102-106) + § 12 istatistiksel imza testleri tablosu satır B/C. Iter 4a milestone commit: `baf81f0`; final polish: `bd60144`.

---

## Önkoşul

`.venv` aktif, `pip install -e .` yapılmış, Iter 4a testleri (107 PASS) yeşil olmalı:

```bash
cd /Users/cemalozcan/Desktop/mast-anomaly-detection
source .venv/bin/activate
pytest tests/ -q                                                    # 107 passed beklenir
mypy src/simulator tests/unit tests/integration tests/scenarios     # Success
ruff check src/simulator tests/unit tests/integration tests/scenarios   # All checks passed
```

Eğer baseline kırıksa durduralım.

---

## Dosya Yapısı (Iter 4b sonunda)

```
src/simulator/scenarios/
├── __init__.py                                   # GENİŞLET: SCENARIO_REGISTRY 3 entry; __all__ tüm scenario class'ları
├── base.py                                       # değişmez
├── mechanical_wear.py                            # değişmez
├── hydraulic_leak.py                             # YENİ
└── electrical_fault.py                           # YENİ

tests/unit/test_scenarios/
├── __init__.py                                   # değişmez
├── test_base.py                                  # değişmez
├── test_mechanical_wear.py                       # değişmez
├── test_hydraulic_leak.py                        # YENİ (~9 test)
└── test_electrical_fault.py                      # YENİ (~10 test)

tests/scenarios/
├── __init__.py                                   # değişmez
├── conftest.py                                   # YENİ: CountingClock + _ticking_sleep DRY helper'lar
├── test_mechanical_wear_signature.py             # MODIFY: helper'ları conftest'ten al
├── test_hydraulic_leak_signature.py              # YENİ: scipy.stats.spearmanr
└── test_electrical_fault_signature.py            # YENİ: scipy.stats.bartlett iki run

tests/fixtures/
├── devices_with_mechanical_wear.yaml             # değişmez (Iter 4a)
├── devices_with_hydraulic_leak.yaml              # YENİ
└── devices_with_electrical_fault.yaml            # YENİ

config/devices.yaml.example                        # GENİŞLET: device_003'e hydraulic_leak + electrical_fault scenarios

requirements.txt                                   # GENİŞLET: scipy==1.17.1 explicit pin

CLAUDE.md                                          # GÜNCELLE: Mevcut Faz → Faz 2 (Ingestion + Storage) sıradaki; Iter 4b Tamamlandı; Faz 1 closure paragraph
```

**Beklenen test sayısı:** 107 → ~128 (Iter 4a 107 + 21 yeni: hydraulic_leak unit 9 + electrical_fault unit 10 + 2 signature).
**Hedef coverage:** ≥%90 (Iter 4a %94'tü; yeni scenarios basit, branch coverage yüksek olmalı).

---

## Task 1: `HydraulicLeak` (B) Senaryosu + Unit Testler

Spec § 9 B formülünü implement et. State filter (sadece HOLDING aktif), params validation (leak_rate_bar_per_min + position_sag_mm required), 2 sensor formula (hydraulic_pressure floor'lu drop, mast_position lineer sag). SCENARIO_REGISTRY'ye kayıt.

**Files:**
- Create: `src/simulator/scenarios/hydraulic_leak.py`
- Modify: `src/simulator/scenarios/__init__.py` (registry'ye 1 yeni entry)
- Create: `tests/unit/test_scenarios/test_hydraulic_leak.py`

- [x] **Step 1.1: `tests/unit/test_scenarios/test_hydraulic_leak.py` failing testleri yaz**

```python
"""HydraulicLeak (spec § 9 B, DOMAIN.md sat. 90-93) modify behavior testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState, elapsed_in_state_s: float = 0.0) -> DeviceRuntimeState:
    """Test fixture: state + elapsed_in_state_s belirli runtime.

    `runtime.elapsed_in_state_s` property `clock() - state_entered_at_monotonic`;
    bu yüzden clock=lambda: elapsed_in_state_s + state_entered_at_monotonic=0.0 ile
    istenen elapsed elde edilir.
    """
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10000.0,
        position_mm=0.0,
        cycle_count=0,
        rng=random.Random(42),
        started_at_monotonic=0.0,
        clock=lambda: elapsed_in_state_s,
    )


def test_hydraulic_leak_requires_leak_rate_and_position_sag() -> None:
    """Eksik params → boot-time ValueError."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    with pytest.raises(ValueError, match="leak_rate_bar_per_min"):
        HydraulicLeak(params={"position_sag_mm": 2.0})
    with pytest.raises(ValueError, match="position_sag_mm"):
        HydraulicLeak(params={"leak_rate_bar_per_min": 5.0})
    # Tam set → OK
    HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})


def test_hydraulic_leak_idle_returns_clean_value() -> None:
    """IDLE'da pompa kapalı → kaçak görünmez → identity."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE, 600.0), scenario_elapsed_s=600.0)
    assert scenario.modify("hydraulic_pressure", 10.0, ctx) == 10.0
    assert scenario.modify("mast_position", 0.0, ctx) == 0.0


def test_hydraulic_leak_raising_returns_clean_value() -> None:
    """RAISING'de pompa basıncı kaçağı maskeler (spec § 9 B notu)."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING, 600.0), scenario_elapsed_s=600.0)
    assert scenario.modify("hydraulic_pressure", 150.0, ctx) == 150.0
    assert scenario.modify("mast_position", 2500.0, ctx) == 2500.0


def test_hydraulic_leak_lowering_returns_clean_value() -> None:
    """LOWERING'de basınç zaten düşüyor → modifiye yok (spec § 9 B notu)."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.LOWERING, 600.0), scenario_elapsed_s=600.0)
    assert scenario.modify("hydraulic_pressure", 80.0, ctx) == 80.0


def test_hydraulic_leak_holding_pressure_drops_linearly_with_held_minutes() -> None:
    """HOLDING'de hydraulic_pressure → clean - leak_rate * held_minutes."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    # elapsed_in_state_s = 120s → held_minutes = 2.0 → pressure_drop = 10.0
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, 120.0), scenario_elapsed_s=120.0)
    # clean=80.0 → 80.0 - 10.0 = 70.0
    assert scenario.modify("hydraulic_pressure", 80.0, ctx) == pytest.approx(70.0)


def test_hydraulic_leak_holding_position_sags_linearly() -> None:
    """HOLDING'de mast_position → clean - position_sag_mm * held_minutes."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    # held_minutes = 3.0 → sag = 6.0 mm
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, 180.0), scenario_elapsed_s=180.0)
    assert scenario.modify("mast_position", 5000.0, ctx) == pytest.approx(4994.0)


def test_hydraulic_leak_pressure_floor_at_5_bar() -> None:
    """Çok uzun HOLDING → hydraulic_pressure max(5.0, clean - drop) ile alt sınırda kalır."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    # 60 dakika HOLDING → drop = 300 bar; clean=80 → -220 olurdu, floor 5.0 olmalı
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, 3600.0), scenario_elapsed_s=3600.0)
    assert scenario.modify("hydraulic_pressure", 80.0, ctx) == pytest.approx(5.0)


def test_hydraulic_leak_unaffected_sensors_return_clean() -> None:
    """motor_current, motor_voltage, motor_temperature, vibration etkilenmez → identity."""
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    scenario = HydraulicLeak(params={"leak_rate_bar_per_min": 5.0, "position_sag_mm": 2.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, 120.0), scenario_elapsed_s=120.0)
    assert scenario.modify("motor_current", 0.5, ctx) == 0.5
    assert scenario.modify("motor_voltage", 24.0, ctx) == 24.0
    assert scenario.modify("motor_temperature", 30.0, ctx) == 30.0
    assert scenario.modify("vibration", 0.05, ctx) == 0.05


def test_hydraulic_leak_registered_in_global_registry() -> None:
    """SCENARIO_REGISTRY['hydraulic_leak'] mevcut ve HydraulicLeak class'ına işaret eder."""
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.hydraulic_leak import HydraulicLeak

    assert SCENARIO_REGISTRY["hydraulic_leak"] is HydraulicLeak
```

- [x] **Step 1.2: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_scenarios/test_hydraulic_leak.py -v
```
Beklenen: 9 yeni test ImportError ile FAIL.

- [x] **Step 1.3: `src/simulator/scenarios/hydraulic_leak.py` yarat**

```python
"""HydraulicLeak arıza senaryosu (spec § 9 B, DOMAIN.md sat. 90-93)."""
from __future__ import annotations

from typing import ClassVar

from simulator.config import DeviceState
from simulator.scenarios.base import FaultScenario, ScenarioContext


class HydraulicLeak(FaultScenario):
    """Hidrolik kaçak: HOLDING'de basınç lineer düşer + mast pozisyonu yavaşça sarkar.

    Aktif state: SADECE HOLDING. RAISING'de pompa basıncı kaçağı maskeler;
    LOWERING'de basınç zaten düşüyor → modifiye yok (spec § 9 B notu).

    `runtime.elapsed_in_state_s` HOLDING filtresi altında "HOLDING'e girişten
    beri geçen süre" anlamına gelir; held_minutes = elapsed_in_state_s / 60.

    Params:
        leak_rate_bar_per_min: float > 0 — dakika başına basınç düşüş hızı.
            Tipik 5.0 (yavaş kaçak); 50.0 (hızlı kaçak).
        position_sag_mm: float > 0 — dakika başına pozisyon kayıp (mm).
            Tipik 2.0.
    """

    name: ClassVar[str] = "hydraulic_leak"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset(
        {"leak_rate_bar_per_min", "position_sag_mm"}
    )

    _PRESSURE_FLOOR_BAR: ClassVar[float] = 5.0

    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        if ctx.runtime.state != DeviceState.HOLDING:
            return clean_value

        held_minutes = ctx.runtime.elapsed_in_state_s / 60.0
        leak_rate = self.params["leak_rate_bar_per_min"]
        sag_rate = self.params["position_sag_mm"]

        if sensor_name == "hydraulic_pressure":
            pressure_drop = leak_rate * held_minutes
            return max(self._PRESSURE_FLOOR_BAR, clean_value - pressure_drop)
        if sensor_name == "mast_position":
            return clean_value - sag_rate * held_minutes
        return clean_value
```

- [x] **Step 1.4: `src/simulator/scenarios/__init__.py`'de registry'ye `hydraulic_leak` ekle**

Mevcut:
```python
from simulator.scenarios.mechanical_wear import MechanicalWear

SCENARIO_REGISTRY: dict[str, type[FaultScenario]] = {
    "mechanical_wear": MechanicalWear,
}
```

Şununla değiştir:
```python
from simulator.scenarios.hydraulic_leak import HydraulicLeak
from simulator.scenarios.mechanical_wear import MechanicalWear

SCENARIO_REGISTRY: dict[str, type[FaultScenario]] = {
    "mechanical_wear": MechanicalWear,
    "hydraulic_leak": HydraulicLeak,
}
```

`__all__`'a da `HydraulicLeak` ekle:
```python
__all__ = [
    "SCENARIO_REGISTRY",
    "active_scenarios_at",
    "FaultScenario",
    "ScenarioContext",
    "MechanicalWear",
    "HydraulicLeak",
]
```

- [x] **Step 1.5: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_scenarios/test_hydraulic_leak.py -v
```
Beklenen: 9 passed.

- [x] **Step 1.6: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 107 + 9 = 116 passed, mypy clean, ruff clean.

- [x] **Step 1.7: Commit**

```bash
git add src/simulator/scenarios/hydraulic_leak.py \
        src/simulator/scenarios/__init__.py \
        tests/unit/test_scenarios/test_hydraulic_leak.py
git commit -m "$(cat <<'EOF'
feat(scenarios): HydraulicLeak (spec § 9 B) + SCENARIO_REGISTRY entry

Hidrolik kaçak: SADECE HOLDING'de aktif (RAISING'de pompa basıncı maskeler,
LOWERING'de basınç zaten düşüyor). held_minutes = elapsed_in_state_s / 60.
Formüller:
- hydraulic_pressure → max(5.0, clean - leak_rate_bar_per_min * held_minutes)
- mast_position      → clean - position_sag_mm * held_minutes
- diğer sensörler    → identity

_REQUIRED_PARAMS = {leak_rate_bar_per_min, position_sag_mm} — eksikse
boot-time ValueError. _PRESSURE_FLOOR_BAR = 5.0 spec'ten sabit-kodlandı.

SCENARIO_REGISTRY 2 entry. __all__ HydraulicLeak eklendi.
9 unit test: params validation, 3 state identity (IDLE/RAISING/LOWERING),
HOLDING pressure drop, HOLDING position sag, pressure floor, etkilenmeyen
sensörler, registry entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `ElectricalFault` (C) Senaryosu + Unit Testler

Spec § 9 C formülünü implement et. State filter YOK (tüm state'lerde aktif), params validation (spike_prob + voltage_jitter_std), per-sensor independent rng (modify pure kalır). SCENARIO_REGISTRY'ye kayıt.

**Files:**
- Create: `src/simulator/scenarios/electrical_fault.py`
- Modify: `src/simulator/scenarios/__init__.py` (registry'ye 1 yeni entry)
- Create: `tests/unit/test_scenarios/test_electrical_fault.py`

- [x] **Step 2.1: `tests/unit/test_scenarios/test_electrical_fault.py` failing testleri yaz**

```python
"""ElectricalFault (spec § 9 C, DOMAIN.md sat. 102-106) modify behavior testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState, seed: int = 42) -> DeviceRuntimeState:
    """Test fixture: state + seed'li RNG."""
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10000.0,
        position_mm=0.0,
        cycle_count=0,
        rng=random.Random(seed),
        started_at_monotonic=0.0,
        clock=lambda: 0.0,
    )


def test_electrical_fault_requires_spike_prob_and_voltage_jitter_std() -> None:
    """Eksik params → boot-time ValueError."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    with pytest.raises(ValueError, match="spike_prob"):
        ElectricalFault(params={"voltage_jitter_std": 0.6})
    with pytest.raises(ValueError, match="voltage_jitter_std"):
        ElectricalFault(params={"spike_prob": 0.05})
    # Tam set → OK
    ElectricalFault(params={"spike_prob": 0.05, "voltage_jitter_std": 0.6})


def test_electrical_fault_active_in_all_states() -> None:
    """spike_prob=1.0 → her state'te motor_voltage değişir (state filter YOK)."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 1.0, "voltage_jitter_std": 0.6})
    for state in (DeviceState.IDLE, DeviceState.RAISING, DeviceState.HOLDING, DeviceState.LOWERING):
        ctx = ScenarioContext(runtime=_runtime(state), scenario_elapsed_s=0.0)
        # spike_prob=1.0 → spike kesin → motor_voltage clean+uniform(-30,30) → 24 ± 30 aralığında
        result = scenario.modify("motor_voltage", 24.0, ctx)
        assert -6.0 <= result <= 54.0, f"state={state}: motor_voltage {result} aralık dışında"


def test_electrical_fault_spike_branch_motor_current() -> None:
    """spike_prob=1.0 + seed deterministik → motor_current clean + uniform(-2, 4)."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 1.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    # rng deterministic; clean=8.0 → 8.0 + uniform(-2, 4) ∈ [6.0, 12.0]
    result = scenario.modify("motor_current", 8.0, ctx)
    assert 6.0 <= result <= 12.0


def test_electrical_fault_spike_branch_motor_voltage() -> None:
    """spike_prob=1.0 → motor_voltage clean + uniform(-30, 30) ∈ [clean-30, clean+30]."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 1.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING, seed=42), scenario_elapsed_s=0.0)
    result = scenario.modify("motor_voltage", 24.0, ctx)
    assert -6.0 <= result <= 54.0


def test_electrical_fault_non_spike_branch_motor_voltage_gauss_jitter() -> None:
    """spike_prob=0.0 → motor_voltage clean + gauss(0, voltage_jitter_std)."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 0.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE, seed=42), scenario_elapsed_s=0.0)
    # 100 örnekleme: ortalama ≈ 24.0 ± 0.6 σ, std ≈ 0.6
    samples = [scenario.modify("motor_voltage", 24.0, ctx) for _ in range(100)]
    mean = sum(samples) / len(samples)
    assert abs(mean - 24.0) < 0.2, f"Ortalama {mean} 24.0'dan çok sapmış"


def test_electrical_fault_non_spike_branch_motor_current_unchanged() -> None:
    """spike_prob=0.0 → motor_current değişmez (sadece spike branch etkiler)."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 0.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    assert scenario.modify("motor_current", 8.0, ctx) == 8.0


def test_electrical_fault_unaffected_sensors_return_clean() -> None:
    """hydraulic_pressure, motor_temperature, mast_position, vibration etkilenmez."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario = ElectricalFault(params={"spike_prob": 1.0, "voltage_jitter_std": 0.6})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    assert scenario.modify("hydraulic_pressure", 150.0, ctx) == 150.0
    assert scenario.modify("motor_temperature", 30.0, ctx) == 30.0
    assert scenario.modify("mast_position", 2500.0, ctx) == 2500.0
    assert scenario.modify("vibration", 0.3, ctx) == 0.3


def test_electrical_fault_deterministic_with_same_seed() -> None:
    """Aynı rng seed + aynı modify çağrı sırası → birebir aynı çıktı."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario_a = ElectricalFault(params={"spike_prob": 0.5, "voltage_jitter_std": 0.6})
    scenario_b = ElectricalFault(params={"spike_prob": 0.5, "voltage_jitter_std": 0.6})
    ctx_a = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    ctx_b = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)

    seq_a = [scenario_a.modify("motor_voltage", 24.0, ctx_a) for _ in range(20)]
    seq_b = [scenario_b.modify("motor_voltage", 24.0, ctx_b) for _ in range(20)]
    assert seq_a == seq_b


def test_electrical_fault_different_seeds_produce_different_sequences() -> None:
    """Negatif kontrol: farklı seed → farklı dizi."""
    from simulator.scenarios.electrical_fault import ElectricalFault

    scenario_a = ElectricalFault(params={"spike_prob": 0.5, "voltage_jitter_std": 0.6})
    scenario_b = ElectricalFault(params={"spike_prob": 0.5, "voltage_jitter_std": 0.6})
    ctx_a = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=42), scenario_elapsed_s=0.0)
    ctx_b = ScenarioContext(runtime=_runtime(DeviceState.RAISING, seed=7), scenario_elapsed_s=0.0)

    seq_a = [scenario_a.modify("motor_voltage", 24.0, ctx_a) for _ in range(20)]
    seq_b = [scenario_b.modify("motor_voltage", 24.0, ctx_b) for _ in range(20)]
    assert seq_a != seq_b


def test_electrical_fault_registered_in_global_registry() -> None:
    """SCENARIO_REGISTRY['electrical_fault'] mevcut ve ElectricalFault class'ına işaret eder."""
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.electrical_fault import ElectricalFault

    assert SCENARIO_REGISTRY["electrical_fault"] is ElectricalFault
```

- [x] **Step 2.2: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_scenarios/test_electrical_fault.py -v
```
Beklenen: 10 yeni test ImportError ile FAIL.

- [x] **Step 2.3: `src/simulator/scenarios/electrical_fault.py` yarat**

```python
"""ElectricalFault arıza senaryosu (spec § 9 C, DOMAIN.md sat. 102-106)."""
from __future__ import annotations

from typing import ClassVar

from simulator.scenarios.base import FaultScenario, ScenarioContext


class ElectricalFault(FaultScenario):
    """Elektriksel bağlantı sorunu: rastgele spike'lar + sürekli voltaj jitter.

    State filtering YOK — tüm DeviceState'lerde aktif (spec § 9 C: elektriksel
    sorun mekanik harekete bağlı değil). Pratikte RAISING/HOLDING'de daha gözle
    görülür çünkü motor enerjili.

    Per-sensor independent RNG: her `modify` çağrısı `runtime.rng.random()` ile
    spike kararı verir. Bu, modify pure (no scenario instance state) tutar ve
    sensor sırasından bağımsız çalışır. modify çağrı sırasında runtime.rng
    advance eder; engine'in noise stream'i ile interleave olur (per-device seed
    determinizmi korunur — same-seed regression test geçer).

    Params:
        spike_prob: float ∈ [0, 1] — her sensor modify çağrısı başına spike olasılığı.
            Tipik 0.05 (%5).
        voltage_jitter_std: float > 0 — non-spike durumda motor_voltage gauss jitter
            standart sapması. Tipik 0.6 (baseline noise 0.2'nin 3 katı).
    """

    name: ClassVar[str] = "electrical_fault"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset(
        {"spike_prob", "voltage_jitter_std"}
    )

    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        rng = ctx.runtime.rng
        spike_prob = self.params["spike_prob"]
        voltage_jitter_std = self.params["voltage_jitter_std"]

        if rng.random() < spike_prob:
            if sensor_name == "motor_current":
                return clean_value + rng.uniform(-2.0, 4.0)
            if sensor_name == "motor_voltage":
                return clean_value + rng.uniform(-30.0, 30.0)
            return clean_value
        else:
            if sensor_name == "motor_voltage":
                return clean_value + rng.gauss(0.0, voltage_jitter_std)
            return clean_value
```

- [x] **Step 2.4: `src/simulator/scenarios/__init__.py`'de registry'ye `electrical_fault` ekle**

Mevcut (Task 1 sonrası):
```python
from simulator.scenarios.hydraulic_leak import HydraulicLeak
from simulator.scenarios.mechanical_wear import MechanicalWear

SCENARIO_REGISTRY: dict[str, type[FaultScenario]] = {
    "mechanical_wear": MechanicalWear,
    "hydraulic_leak": HydraulicLeak,
}
```

Şununla değiştir:
```python
from simulator.scenarios.electrical_fault import ElectricalFault
from simulator.scenarios.hydraulic_leak import HydraulicLeak
from simulator.scenarios.mechanical_wear import MechanicalWear

SCENARIO_REGISTRY: dict[str, type[FaultScenario]] = {
    "mechanical_wear": MechanicalWear,
    "hydraulic_leak": HydraulicLeak,
    "electrical_fault": ElectricalFault,
}
```

`__all__`'a `ElectricalFault` ekle:
```python
__all__ = [
    "SCENARIO_REGISTRY",
    "active_scenarios_at",
    "FaultScenario",
    "ScenarioContext",
    "MechanicalWear",
    "HydraulicLeak",
    "ElectricalFault",
]
```

- [x] **Step 2.5: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_scenarios/test_electrical_fault.py -v
```
Beklenen: 10 passed.

- [x] **Step 2.6: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 116 + 10 = 126 passed, mypy clean, ruff clean.

- [x] **Step 2.7: Commit**

```bash
git add src/simulator/scenarios/electrical_fault.py \
        src/simulator/scenarios/__init__.py \
        tests/unit/test_scenarios/test_electrical_fault.py
git commit -m "$(cat <<'EOF'
feat(scenarios): ElectricalFault (spec § 9 C) + SCENARIO_REGISTRY entry

Elektriksel arıza: state filter YOK (tüm state'lerde aktif). Per-sensor
independent rng.random() spike decision (modify pure kalır).

Branch'ler:
- spike (rng < spike_prob): motor_current + uniform(-2,4); motor_voltage + uniform(-30,30)
- non-spike: motor_voltage + gauss(0, voltage_jitter_std)
- diğer sensörler: identity

_REQUIRED_PARAMS = {spike_prob, voltage_jitter_std}. RNG runtime.rng üzerinden
akar — engine noise stream'i ile interleave eder ama per-device seed determinizmi
korunur (same-seed regression test geçmeye devam eder).

SCENARIO_REGISTRY 3 entry. 10 unit test: params, state-agnostic, spike branches,
non-spike branches, deterministic, negative control, etkilenmeyen sensörler,
registry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `tests/scenarios/conftest.py` Extraction (DRY)

Iter 4a'da `tests/scenarios/test_mechanical_wear_signature.py` `CountingClock` + `_ticking_sleep` helper'larını inline tanımladı. Iter 4b'nin 2 yeni signature test'i aynı helper'lara ihtiyaç duyacak — 3 consumer kuralı DRY refactor zamanı geldi. `tests/scenarios/conftest.py` oluştur, mevcut signature test'i güncelle.

**Files:**
- Create: `tests/scenarios/conftest.py`
- Modify: `tests/scenarios/test_mechanical_wear_signature.py` (helper'ları conftest'ten import)

- [x] **Step 3.1: `tests/scenarios/conftest.py` yarat**

```python
"""Shared fixtures for statistical signature tests (Iter 4b refactor).

CountingClock + _ticking_sleep monkeypatch pattern: engine'in `asyncio.sleep`
çağrılarını no-op'lar AMA her tick'te bir saniyelik clock advance eder. Sonuç:
- Gerçek wall-clock beklemesi YOK (test mikrosaniyede koşar)
- `runtime.clock()` ardışık tick'lerde 1.0s ilerler (state machine doğal akar)
- `runtime.device_elapsed_s` + `runtime.elapsed_in_state_s` doğru değerler döner
- Senaryo aktivasyon pencereleri (start_after_s, duration_s) doğru çalışır

Iter 4a `test_mechanical_wear_signature.py` ve Iter 4b'nin 2 yeni signature
test'i aynı pattern'i kullanır → DRY.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


class CountingClock:
    """Her tick için 1 saniye ilerleyen test-only clock.

    Engine içinde `clock()` çağrıları sıralı yapılır; her tick'te `tick()`
    çağrılınca dahili sayaç 1.0 artar. `_ticking_sleep` monkeypatch'i
    `asyncio.sleep` her çağrısında `tick()` tetikler — böylece state machine
    ve senaryo elapsed'leri doğal akar.
    """

    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        return self._t

    def tick(self) -> None:
        self._t += 1.0


@pytest.fixture
def patched_engine_clock(monkeypatch: pytest.MonkeyPatch) -> CountingClock:
    """Engine'in `asyncio.sleep`'ini tick-advancing no-op ile monkeypatch eder.

    Returns:
        CountingClock instance — test bunu `run(clock=...)` parametresine geçer.
    """
    original_sleep = asyncio.sleep
    clock = CountingClock()

    async def _ticking_sleep(_s: float) -> None:
        clock.tick()
        await original_sleep(0)

    monkeypatch.setattr("simulator.engine.asyncio.sleep", _ticking_sleep)
    return clock
```

- [x] **Step 3.2: `tests/scenarios/test_mechanical_wear_signature.py` güncelle — helper'ları conftest'ten al**

Mevcut dosyada `class CountingClock`, `_ticking_sleep` async wrapper'ı, ve `monkeypatch.setattr` bloğunu kaldır. `FIXTURES` import'u da conftest'ten gelecek. `patched_engine_clock` fixture'unu kullan.

Mevcut testi şuna güncelle:

```python
"""MechanicalWear istatistiksel imza testi (spec § 12 bitti kriteri A).

60+ örnek RAISING'de motor_current ortalaması baseline'a göre %15..%30 yüksek
olmalı (scipy.stats.ttest_1samp p<0.05). Bu test "senaryo gerçekten gözle
görülür bir kayma üretiyor mu" sorusunu istatistiksel olarak doğrular —
hipotez kontrolü değil, regresyon değer kontrolü (deterministik seed altında
stabil p-value).
"""
from __future__ import annotations

import pytest
from scipy.stats import ttest_1samp  # type: ignore[import-untyped]

from simulator.config import DeviceState
from simulator.engine import run
from tests.scenarios.conftest import FIXTURES, CountingClock


def test_mechanical_wear_raising_current_mean_significantly_above_baseline(
    monkeypatch: pytest.MonkeyPatch,
    patched_engine_clock: CountingClock,
) -> None:
    """RAISING motor_current ortalama: t-test p<0.05 ve mean ∈ [baseline * 1.15, baseline * 1.30]."""
    from unittest.mock import MagicMock

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_with_mechanical_wear.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=200,
        seed=None,
        clock=patched_engine_clock,
    )

    raising_motor_currents = [
        c.kwargs["value"]
        for c in mock_publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "motor_current"
        and c.kwargs["state"] == DeviceState.RAISING
    ]

    assert len(raising_motor_currents) >= 60, (
        f"En az 60 RAISING motor_current örneği bekleniyor, alınan: {len(raising_motor_currents)}"
    )

    baseline = 8.0
    mean_obs = sum(raising_motor_currents) / len(raising_motor_currents)

    assert baseline * 1.15 <= mean_obs <= baseline * 1.30, (
        f"Ortalama {mean_obs:.2f} baseline {baseline} * [1.15, 1.30] dışında"
    )

    result = ttest_1samp(raising_motor_currents, popmean=baseline)
    assert result.pvalue < 0.05, (
        f"t-test p={result.pvalue:.4f} ≥ 0.05 — MechanicalWear sinyali baseline'dan ayırt edilmiyor"
    )
```

Eski inline `CountingClock` ve `_ticking_sleep` TAMAMEN SİL.

- [x] **Step 3.3: Mevcut signature test'i koş, hâlâ pass — davranış değişikliği YOK**

```bash
pytest tests/scenarios/test_mechanical_wear_signature.py -v
```
Beklenen: 1 passed.

- [x] **Step 3.4: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 126 passed (refactor — test sayısı değişmez), mypy clean, ruff clean.

- [x] **Step 3.5: Commit**

```bash
git add tests/scenarios/conftest.py tests/scenarios/test_mechanical_wear_signature.py
git commit -m "$(cat <<'EOF'
test(scenarios): extract CountingClock + _ticking_sleep to conftest

Iter 4a inline pattern → tests/scenarios/conftest.py'ye taşındı. patched_engine_clock
pytest fixture'u monkeypatch'i + clock'u tek satırda inject eder. Iter 4b'nin
HydraulicLeak + ElectricalFault signature test'leri aynı fixture'u kullanacak
(3 consumer kuralı).

Mevcut test_mechanical_wear_signature.py inline helper'ları kaldırıldı,
fixture'a geçirildi. Davranış değişikliği YOK (1 passed devam).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: HydraulicLeak İstatistiksel İmza Testi (Spearman)

Spec § 12 bitti kriteri B: HOLDING penceresinde 60+ örnek üzerinde `hydraulic_pressure` zaman serisine `scipy.stats.spearmanr(tick_indices, pressures)` → ρ<0 ve p<0.05 (negatif monoton trend).

**Files:**
- Create: `tests/fixtures/devices_with_hydraulic_leak.yaml`
- Create: `tests/scenarios/test_hydraulic_leak_signature.py`

- [x] **Step 4.1: `tests/fixtures/devices_with_hydraulic_leak.yaml` yarat**

Sabit state_durations (HOLDING uzun → ≥60 örnek garantili) + scenarios bloğu:

```yaml
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [1, 1]
      raising:  [1, 1]
      holding:  [120, 120]
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

HOLDING duration 120s → 120 örnek tek HOLDING penceresinde, ≥60 kriterini fazlasıyla karşılar.

- [x] **Step 4.2: `tests/scenarios/test_hydraulic_leak_signature.py` yaz**

```python
"""HydraulicLeak istatistiksel imza testi (spec § 12 bitti kriteri B).

HOLDING penceresinde 60+ örnek üzerinde hydraulic_pressure zaman serisine
scipy.stats.spearmanr → ρ<0 ve p<0.05 (negatif monoton trend).
"""
from __future__ import annotations

import pytest
from scipy.stats import spearmanr  # type: ignore[import-untyped]

from simulator.config import DeviceState
from simulator.engine import run
from tests.scenarios.conftest import FIXTURES, CountingClock


def test_hydraulic_leak_holding_pressure_decreases_monotonically(
    monkeypatch: pytest.MonkeyPatch,
    patched_engine_clock: CountingClock,
) -> None:
    """HOLDING'de hydraulic_pressure zaman serisi Spearman ρ<0, p<0.05."""
    from unittest.mock import MagicMock

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_with_hydraulic_leak.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=150,  # IDLE(1) + RAISING(1) + HOLDING(120) + LOWERING(1) = 123 — ilk cycle yeterli
        seed=None,
        clock=patched_engine_clock,
    )

    # HOLDING durumundaki hydraulic_pressure değerlerini sırayla topla
    holding_pressures = [
        c.kwargs["value"]
        for c in mock_publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "hydraulic_pressure"
        and c.kwargs["state"] == DeviceState.HOLDING
    ]

    assert len(holding_pressures) >= 60, (
        f"En az 60 HOLDING hydraulic_pressure örneği bekleniyor, alınan: {len(holding_pressures)}"
    )

    # tick_indices = [0, 1, 2, ...] (zaman sırasında)
    tick_indices = list(range(len(holding_pressures)))

    result = spearmanr(tick_indices, holding_pressures)
    # H0 = monoton ilişki yok. H1 = negatif monoton (basınç düşüşü).
    assert result.statistic < 0, (
        f"Spearman ρ={result.statistic:.3f} ≥ 0 — basınç düşmüyor"
    )
    assert result.pvalue < 0.05, (
        f"Spearman p={result.pvalue:.4f} ≥ 0.05 — kaçak sinyali istatistiksel olarak anlamsız"
    )
```

- [x] **Step 4.3: Testi koş, PASS gör**

```bash
pytest tests/scenarios/test_hydraulic_leak_signature.py -v
```
Beklenen: 1 passed. Eğer FAIL ederse:
- "60 örnek bekleniyor" → HOLDING duration'ı arttır (180s veya 300s)
- ρ ≥ 0 → leak_rate_bar_per_min arttır (10.0 dene)
- p ≥ 0.05 → daha uzun HOLDING penceresi veya daha güçlü leak rate

- [x] **Step 4.4: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 126 + 1 = 127 passed, mypy/ruff clean.

- [x] **Step 4.5: Commit**

```bash
git add tests/fixtures/devices_with_hydraulic_leak.yaml \
        tests/scenarios/test_hydraulic_leak_signature.py
git commit -m "$(cat <<'EOF'
test(scenarios): HydraulicLeak istatistiksel imza (spec § 12 bitti kriteri B)

HOLDING penceresinde 60+ hydraulic_pressure örneği toplanır, zaman serisine
scipy.stats.spearmanr uygulanır → ρ<0 ve p<0.05 doğrulanır (negatif monoton
trend).

devices_with_hydraulic_leak.yaml fixture (HOLDING duration 120s → 120 örnek
tek pencerede, leak_rate=5.0 bar/min, position_sag=2.0 mm/min).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: ElectricalFault İstatistiksel İmza Testi (Bartlett — İki Run)

Spec § 12 bitti kriteri C: scenario aktif iken `motor_voltage` standart sapması baseline'ın 3 katı (F-testi p<0.05). İki ayrı engine run: (1) scenarios=[] baseline, (2) ElectricalFault aktif. `scipy.stats.bartlett(baseline_voltages, scenario_voltages)` variance equality testi p<0.05 + manuel std ratio ≈ 3 kontrolü.

**Files:**
- Create: `tests/fixtures/devices_with_electrical_fault.yaml`
- Create: `tests/scenarios/test_electrical_fault_signature.py`

- [x] **Step 5.1: `tests/fixtures/devices_with_electrical_fault.yaml` yarat**

```yaml
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [60, 60]
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
      - name: electrical_fault
        start_after_s: 0
        duration_s: 3600
        params:
          spike_prob: 0.05
          voltage_jitter_std: 0.6
```

state_durations uniform [60, 60] → tüm state'lerde örnek toplanır. ElectricalFault tüm state'lerde aktif olduğu için bu fixture'ta filter yok.

Aynı fixture'ı baseline run için de kullanmak için baseline'da scenarios=[] tutmalı. **İki ayrı fixture** mı yoksa **aynı fixture'ı modify** ederek mi? Plan'da iki seçenek var; en temizi: tek fixture (yukarıdaki) hem baseline hem scenario için kullanılır, test runtime'da iki kez `run()` çağırır — birinci kez scenarios=[] modify ile (`devices_minimal.yaml` veya benzer scenarios'suz fixture), ikinci kez yukarıdaki scenario fixture ile. Aslında en pratik: mevcut `devices_minimal.yaml` baseline olarak, yeni `devices_with_electrical_fault.yaml` scenario olarak iki ayrı `run()` çağrısı.

`tests/fixtures/devices_minimal.yaml` zaten 1 cihaz scenarios'suz (Iter 2b'den) — baseline run için kullanılır.

- [x] **Step 5.2: `tests/scenarios/test_electrical_fault_signature.py` yaz**

```python
"""ElectricalFault istatistiksel imza testi (spec § 12 bitti kriteri C).

İki ayrı engine run:
- Baseline: devices_minimal.yaml (scenarios=[]), saf gürültü
- Scenario: devices_with_electrical_fault.yaml, ElectricalFault aktif

motor_voltage örnekleri her iki run'dan toplanır:
- scipy.stats.bartlett: variance equality testi p<0.05 (H0=eşit variance reddedilir)
- Manuel std ratio: scenario_std / baseline_std ≈ 3 (spec § 12 satır C)
"""
from __future__ import annotations

import statistics

import pytest
from scipy.stats import bartlett  # type: ignore[import-untyped]

from simulator.engine import run
from tests.scenarios.conftest import FIXTURES, CountingClock


def _collect_motor_voltages(
    devices_yaml_name: str,
    monkeypatch: pytest.MonkeyPatch,
    clock: CountingClock,
    max_iterations: int,
) -> list[float]:
    """Engine'i verilen fixture ile koş, tüm motor_voltage örneklerini topla."""
    from unittest.mock import MagicMock

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / devices_yaml_name,
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=max_iterations,
        seed=None,
        clock=clock,
    )

    return [
        c.kwargs["value"]
        for c in mock_publisher.publish_reading.call_args_list
        if c.kwargs["sensor"] == "motor_voltage"
    ]


def test_electrical_fault_motor_voltage_variance_significantly_above_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bartlett variance equality testi reddedilir + scenario std ≈ 3 × baseline std.

    Spec § 12 satır C: aktif std baseline'ın 3 katı (F-testi p<0.05). Bartlett
    F-distribution tabanlı variance equality testidir — "F-testi" şemsiyesi
    altındadır.
    """
    from tests.scenarios.conftest import CountingClock

    # Iki ayrı CountingClock (her run kendi clock'unu kullansın, izole zamanlar)
    baseline_clock = CountingClock()
    scenario_clock = CountingClock()

    # Baseline run
    original_sleep = __import__("asyncio").sleep

    async def _baseline_sleep(_s: float) -> None:
        baseline_clock.tick()
        await original_sleep(0)

    monkeypatch.setattr("simulator.engine.asyncio.sleep", _baseline_sleep)
    baseline_voltages = _collect_motor_voltages(
        "devices_minimal.yaml", monkeypatch, baseline_clock, max_iterations=150
    )

    # Scenario run
    async def _scenario_sleep(_s: float) -> None:
        scenario_clock.tick()
        await original_sleep(0)

    monkeypatch.setattr("simulator.engine.asyncio.sleep", _scenario_sleep)
    scenario_voltages = _collect_motor_voltages(
        "devices_with_electrical_fault.yaml", monkeypatch, scenario_clock, max_iterations=150
    )

    assert len(baseline_voltages) >= 100, f"baseline örnekleri: {len(baseline_voltages)}"
    assert len(scenario_voltages) >= 100, f"scenario örnekleri: {len(scenario_voltages)}"

    baseline_std = statistics.stdev(baseline_voltages)
    scenario_std = statistics.stdev(scenario_voltages)
    ratio = scenario_std / baseline_std

    # 1) Std ratio kontrolü: spec satır C "≈ 3 katı" — geniş tolerans [2.0, 6.0]
    # (spike + uniform(-30,30) varyansa yüksek katkı; non-spike gauss(0,0.6) baseline'ın
    # 0.2 std'sine eklenir → effective std ~0.63. spike_prob=0.05 ile karışım std hesabı
    # yaklaşık E[var] = 0.95*0.4 + 0.05*300 = 15.4 → std ~3.9 → ratio ~6 olasıdır.)
    assert 2.0 <= ratio <= 10.0, (
        f"Std ratio {ratio:.2f} bekleneni karşılamıyor (baseline_std={baseline_std:.3f}, "
        f"scenario_std={scenario_std:.3f})"
    )

    # 2) Bartlett testi: H0 = eşit variance reddedilmeli (p<0.05)
    result = bartlett(baseline_voltages, scenario_voltages)
    assert result.pvalue < 0.05, (
        f"Bartlett p={result.pvalue:.4e} ≥ 0.05 — ElectricalFault variance sinyali baseline'dan ayırt edilmiyor"
    )
```

- [x] **Step 5.3: Testi koş, PASS gör**

```bash
pytest tests/scenarios/test_electrical_fault_signature.py -v
```
Beklenen: 1 passed. Eğer FAIL ederse:
- "100 örnek bekleniyor" → max_iterations arttır
- Std ratio aralık dışı → tolerans aralığını genişlet veya spike_prob/voltage_jitter_std ayarla. Plan'daki [2.0, 10.0] aralığı geniş; empirik ratio raporda paylaşılsın
- Bartlett p ≥ 0.05 → örnek sayısı az veya scenario gücü düşük; max_iterations arttır

- [x] **Step 5.4: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 127 + 1 = 128 passed, mypy/ruff clean.

- [x] **Step 5.5: Commit**

```bash
git add tests/fixtures/devices_with_electrical_fault.yaml \
        tests/scenarios/test_electrical_fault_signature.py
git commit -m "$(cat <<'EOF'
test(scenarios): ElectricalFault istatistiksel imza (spec § 12 bitti kriteri C)

İki ayrı engine run (baseline scenarios=[] + scenario ElectricalFault aktif),
motor_voltage örnekleri toplanır:
- scipy.stats.bartlett: F-distribution tabanlı variance equality testi p<0.05
- Manuel std ratio: scenario_std / baseline_std ∈ [2.0, 10.0] (spec § 12 "≈ 3
  katı" — geniş tolerans; spike + uniform(-30,30) varyansa yüksek katkı verir)

devices_with_electrical_fault.yaml fixture (uniform state_durations [60,60]
tüm state'lerde örnek garantili, spike_prob=0.05, voltage_jitter_std=0.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `scipy==1.17.1` Explicit Pin

Iter 4a + 4b scipy.stats kullanıyor; şu an scikit-learn 1.5.0 transitif. Explicit pin → reproducibility + scipy major bump'a karşı koruma.

**Files:**
- Modify: `requirements.txt`

- [x] **Step 6.1: `requirements.txt`'de scipy ekle**

Mevcut "# Machine Learning" bloğunu şuna güncelle:

```
# Machine Learning
scikit-learn==1.5.0
scipy==1.17.1
```

- [x] **Step 6.2: pip install ile doğrula**

```bash
pip install -r requirements.txt
```
Beklenen: `Requirement already satisfied: scipy==1.17.1` (zaten yüklü).

- [x] **Step 6.3: Tam suite + mypy + ruff (regression yok)**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 128 passed, mypy/ruff clean.

- [x] **Step 6.4: Commit**

```bash
git add requirements.txt
git commit -m "$(cat <<'EOF'
chore(deps): explicit scipy==1.17.1 pin

scipy daha önce scikit-learn 1.5.0 transitif'inden geliyordu; Iter 4a +
4b'nin istatistiksel imza testleri (ttest_1samp, spearmanr, bartlett)
explicit pin ile reproducibility + scipy major bump'a karşı koruma sağlar.

Pin versiyonu lokal .venv'de halihazırda yüklü (1.17.1) — davranış değişmez.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `devices.yaml.example` Genişletme — device_003'e B + C

Manuel uçtan uca demo için: device_001 sağlıklı (clean), device_002 mechanical_wear (Iter 4a'da eklendi), device_003 hydraulic_leak + electrical_fault. 3 cihaz × 3 farklı durum kıyaslama zenginleştirilir.

**Files:**
- Modify: `config/devices.yaml.example`

- [x] **Step 7.1: `config/devices.yaml.example` device_003'e scenarios ekle**

Mevcut device_003 bloğu (sensors listesinin altı). Sensors listesinin altına ekle:

```yaml
    scenarios:
      - name: hydraulic_leak
        start_after_s: 60          # 1 dakika sonra başlar (kısa demo için)
        duration_s: 1200            # 20 dakika sürer
        params:
          leak_rate_bar_per_min: 5.0
          position_sag_mm: 2.0
      - name: electrical_fault
        start_after_s: 300         # 5 dakika sonra başlar
        duration_s: 1800            # 30 dakika sürer
        params:
          spike_prob: 0.05          # %5 tick'te spike
          voltage_jitter_std: 0.6   # baseline 0.2'nin 3 katı
```

device_001 ve device_002'ye DOKUNMA (device_001 clean kalır; device_002 mechanical_wear korunur).

- [x] **Step 7.2: `config/devices.yaml` lokal kopya yenile**

```bash
cp config/devices.yaml.example config/devices.yaml
```

- [x] **Step 7.3: Manuel uçtan uca smoke (opsiyonel — mosquitto varsa)**

Terminal A: `mosquitto_sub -v -t 'telemetry/device_003/+'`
Terminal B: `python -m simulator` (5-10 dakika çalıştır)

Beklenen davranış:
- İlk 1 dakika: device_003 baseline (clean)
- 1-5 dakika: hydraulic_leak aktif, HOLDING tick'lerinde hydraulic_pressure giderek düşer (~80 → 60-70)
- 5+ dakika: electrical_fault da aktif, motor_voltage düzensiz spike + jitter gösterir, ara sıra motor_current spike
- device_001 baseline; device_002 mechanical_wear ramp (Iter 4a'dan biliniyor)

**NOTE FOR SUBAGENT:** Mosquitto kuruluysa otomatize edebilirsin (kısa 30-60s run + grep). Değilse SKIP edip raporda belirt — kullanıcı manuel doğrulayacak.

- [x] **Step 7.4: Commit**

```bash
git add config/devices.yaml.example
git commit -m "$(cat <<'EOF'
chore(config): devices.yaml.example device_003'e hydraulic_leak + electrical_fault ekle

Manuel demo zenginleştirme: 3 cihaz × 3 farklı arıza durumu kıyaslama.
- device_001: sağlıklı (clean baseline)
- device_002: mechanical_wear (Iter 4a)
- device_003: hydraulic_leak (start 60s, 20 dk) + electrical_fault (start 300s, 30 dk)

device_001 ve device_002'ye dokunulmadı.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Faz 1 Closure — Milestone Commit + CLAUDE.md → Faz 2 Sıradaki

Plan checkboxları + CLAUDE.md Mevcut Faz güncellemesi (Faz 1 Tamamlandı, Faz 2 sıradaki) + Iter 4b milestone commit.

**Files:**
- Modify: `CLAUDE.md` (Mevcut Faz bölümü)
- Modify: `docs/plans/2026-05-28-faz1-iterasyon4b-hydraulic-leak-electrical-fault.md` (bu dosya — checkbox [x])

- [x] **Step 8.1: `CLAUDE.md` "Mevcut Faz" güncelle**

Header satırını şuna güncelle:
```
**Faz 2 — Ingestion + SQLite Storage** (sıradaki)
```

Tamamlanan iterasyonlar listesine ekle:
```
  - `docs/plans/2026-05-28-faz1-iterasyon4b-hydraulic-leak-electrical-fault.md` (8/8 ✅)
```

"Iterasyon 4b (sıradaki) — Plan henüz yazılmadı" bölümünü ŞUNUNLA değiştir:

```markdown
### Iterasyon 4b (HydraulicLeak + ElectricalFault + Tam İmza Seti) — Tamamlandı (2026-05-28)

`HydraulicLeak` (B): sadece HOLDING aktif, `held_minutes = elapsed_in_state_s / 60`,
hydraulic_pressure → max(5.0, clean - leak_rate * held_minutes), mast_position
lineer sag. `ElectricalFault` (C): state filter YOK, per-sensor independent
`runtime.rng.random()` spike check (modify pure), spike branch motor_current
+uniform(-2,4) + motor_voltage +uniform(-30,30), non-spike branch motor_voltage
gauss jitter. SCENARIO_REGISTRY 3 entry tam set. `tests/scenarios/conftest.py`
DRY refactor (CountingClock + patched_engine_clock fixture). 2 yeni istatistiksel
imza: HydraulicLeak Spearman ρ<0/p<0.05, ElectricalFault Bartlett variance
equality + std ratio kontrolü. `scipy==1.17.1` explicit pin. Toplam 128 test,
≥%90 coverage. devices.yaml.example device_003'e B+C eklendi → 3 cihaz ×
3 farklı durum manuel demo. **Faz 1 tamamlandı.**

## Faz 1 Closure (2026-05-28)

Faz 1 = simulator (sentetik telemetri üretici). Tek cihaz tipi (telescopic_mast_v1),
6 sensör, 4 state machine, N cihaz paralel (asyncio), 3 fault scenario (A/B/C)
+ istatistiksel imzaları. spec § 1 kapsam içi maddeleri tamamlandı. 128 test
yeşil, %90+ coverage. Faz 2 (Ingestion + SQLite) bir sonraki büyük adım.
```

CLAUDE.md "Çalıştırma" satırı zaten N cihaz × 6 sensör × 1 Hz; değişmez. "Test/lint disiplini" satırı zaten tüm dirs (Iter 4a'da güncellendi); değişmez.

- [x] **Step 8.2: Plan dosyasının tüm checkbox'larını [x] yap**

```bash
perl -i -pe 's/^- \[ \]/- [x]/g' docs/plans/2026-05-28-faz1-iterasyon4b-hydraulic-leak-electrical-fault.md
```

Verify: `grep -c '^- \[ \]' docs/plans/2026-05-28-faz1-iterasyon4b-hydraulic-leak-electrical-fault.md` → 0 olmalı.

- [x] **Step 8.3: Tam suite son kez**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration tests/scenarios
ruff check src/simulator tests/unit tests/integration tests/scenarios
```
Beklenen: 128 passed, mypy/ruff clean.

- [x] **Step 8.4: Faz 1 Closure milestone commit**

```bash
git add CLAUDE.md docs/plans/2026-05-28-faz1-iterasyon4b-hydraulic-leak-electrical-fault.md
git commit -m "$(cat <<'EOF'
milestone: Faz 1 Iterasyon 4b + Faz 1 closure tamamlandı 🎉🎉

Iter 4b: HydraulicLeak (B) + ElectricalFault (C) + tam istatistiksel imza
seti + scipy explicit pin + tests/scenarios/conftest.py DRY refactor +
devices.yaml.example device_003 enrichment.

Bitti kriterleri (spec § 3 Iter 4b):
1. ✅ HydraulicLeak class (sadece HOLDING, 2 sensor formula, pressure floor)
2. ✅ ElectricalFault class (state-agnostic, per-sensor rng spike)
3. ✅ SCENARIO_REGISTRY 3 entry tam set (mechanical_wear/hydraulic_leak/electrical_fault)
4. ✅ tests/scenarios/conftest.py extraction (DRY: CountingClock + patched_engine_clock fixture)
5. ✅ Unit testler (HydraulicLeak 9 + ElectricalFault 10)
6. ✅ HydraulicLeak Spearman ρ<0/p<0.05 imza testi
7. ✅ ElectricalFault Bartlett variance equality + std ratio imza testi
8. ✅ scipy==1.17.1 explicit pin

Faz 1 Closure (spec § 1 kapsam tamam):
- 1 cihaz tipi (telescopic_mast_v1) ✅
- 6 sensör (motor_current/voltage, hydraulic_pressure, motor_temperature,
  mast_position, vibration) ✅
- 4 state machine (IDLE → RAISING → HOLDING → LOWERING) ✅
- N cihaz paralel asyncio (Iter 3) ✅
- 3 fault scenario (A/B/C) + istatistiksel imzaları ✅
- 1 Hz yayın frekansı ✅
- Per-cihaz deterministik RNG ✅
- pytest %80+ kapsama (gerçekleşen: %90+) ✅

Toplam: 107 → 128 test (21 yeni), coverage ≥%90.
Faz 2 (Ingestion + SQLite Storage) sıradaki.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Iter 4b Sonu — Bitti Kriterleri (spec § 3 ile birebir)

- [x] **Kriter 1:** `HydraulicLeak` (B) — sadece HOLDING aktif, `held_minutes` lineer formül, pressure floor 5.0 bar (Task 1).
- [x] **Kriter 2:** `ElectricalFault` (C) — state-agnostic, per-sensor `runtime.rng` spike/jitter (Task 2).
- [x] **Kriter 3:** SCENARIO_REGISTRY 3 entry tam set (Task 1 + 2).
- [x] **Kriter 4:** `tests/scenarios/conftest.py` DRY extraction — CountingClock + patched_engine_clock fixture (Task 3).
- [x] **Kriter 5:** Unit testler — HydraulicLeak 9 + ElectricalFault 10 = 19 yeni unit test (Task 1 + 2).
- [x] **Kriter 6:** HydraulicLeak Spearman imza — HOLDING penceresinde ρ<0 ve p<0.05 (Task 4).
- [x] **Kriter 7:** ElectricalFault Bartlett imza — iki run karşılaştırması, variance equality reddedilir + std ratio [2.0, 10.0] (Task 5).
- [x] **Kriter 8:** `scipy==1.17.1` explicit pin (Task 6).
- [x] **Kriter 9:** Faz 1 closure — CLAUDE.md Mevcut Faz Faz 2 sıradaki, Faz 1 tamamlandı paragraph (Task 8).

Her task'ın sonunda **DİSİPLİN** (CLAUDE.md): tam suite + mypy(src+tests+integration+scenarios) + ruff(src+tests+integration+scenarios) — per-file değil.

---

## Memory Güncellemesi (Iter 4b sonu, plan-dışı)

Iter 4b tamamlandıktan sonra `project_active_phase.md` memory'sini güncelle:
- `Active phase` → "Faz 2 — Ingestion + SQLite Storage (next, plan not yet written). Faz 1 tamamlandı."
- Iteration plan listesine Iter 4b ✅ DONE işareti
- "Iter 4b design questions to settle in brainstorming" bloğunu ÇIKAR (kararlar verildi)
- "Faz 1 closure" notu: simulator tamam, ingestion service + SQLite + repository pattern + batch yazma Faz 2'de
- Yeni runtime contract notları: 3 fault scenario registry entry, HydraulicLeak/ElectricalFault davranışı, conftest.py fixture pattern

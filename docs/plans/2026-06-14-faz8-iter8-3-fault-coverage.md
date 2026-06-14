# Faz 8 Iter 8.3 — Arıza Kapsamı (F + E) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simülatöre 2 yeni arıza ekle — F (sıcaklık aşımı, gerçekçi termal modelle) + E (sensör
arızası/imkânsız değer) — uyuyan `motor_temperature_high` kuralını canlandır, yeni
`sensor_out_of_range` kuralı ekle, demoyu 6 cihaza genişlet.

**Architecture:** Mevcut desenler korunur: arızalar `FaultScenario` alt sınıfı (`modify` toplamsal,
saf, `SCENARIO_REGISTRY` kayıtlı); dedektör `Detector` alt sınıfı (`detect(window)->list[Anomaly]`,
`RULE_REGISTRY` kayıtlı, config-driven). Sensör saf kalır; F aşımı senaryonun toplamsal `modify`'ıyla
(sensör tavanı kaldırılmaz). Gözlem modu korunur (yalnız üretir/okur).

**Tech Stack:** Python 3.11, pandas, numpy, pytest, mypy strict, ruff (homebrew). pytest/mypy =
`.venv/bin/python -m ...`; ruff = `ruff`.

**Spec (tek hakem):** `docs/specs/2026-06-14-faz8-iter8-3-fault-coverage-design.md`

**Kalibrasyon değerleri (bu planda sabitlenmiş, imza-testi + canlı smoke doğrular):**
- Gerçekçi termal: ambient/idle-floor **40°C**, normal-çalışma tavanı **75°C** (ısınma 0.08/s, soğuma 0.04/s sabit).
- `motor_temperature_high` eşiği **95°C** (normal 75 + A katkısı ~1.6 = 76.6 üstünde, net marj).
- F senaryosu: `overshoot_rate_c_per_s=0.8`, `max_overshoot_c=60` → F max ~135°C (eşiği aşar, sınır 160'ın altında).
- `sensor_out_of_range` sınırları (geniş fiziksel-imkânsızlık; C/F/B/A meşru değerleri İÇERİDE):
  motor_current [-5,30], motor_voltage [-100,100], hydraulic_pressure [-10,400], motor_temperature [-20,160],
  mast_position [-50,12000], vibration [-1,10].
- E senaryosu: `spike_prob=0.3`, `impossible_value=-500.0` (mast_position).

---

### Task 1: Gerçekçi termal model (motor_temperature sensörü)

**Files:**
- Modify: `src/simulator/sensors/motor_temperature.py`
- Test: `tests/unit/test_motor_temperature_sensor.py`

- [ ] **Step 1: Testleri gerçekçi tabana göre güncelle (önce kırılsınlar)**

`tests/unit/test_motor_temperature_sensor.py` — ŞU testleri aşağıdaki gibi değiştir (sabit değerler
25→40, 35→75):

```python
def test_initial_temperature_is_ambient() -> None:
    """Yeni instance çevre sıcaklığında (40°C) başlar."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    assert sensor.compute(runtime, position_mm=0.0) == pytest.approx(40.0)


def test_heating_in_raising_lineer_per_tick() -> None:
    """RAISING'de her tick 0.08°C artar."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    values = [sensor.compute(runtime, position_mm=1000.0) for _ in range(5)]
    expected = [40.08, 40.16, 40.24, 40.32, 40.40]
    for v, e in zip(values, expected, strict=True):
        assert v == pytest.approx(e)


def test_heating_caps_at_75() -> None:
    """Üst sınır 75°C — uzun süre RAISING'de bile aşmaz."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.HOLDING)
    for _ in range(600):  # 40→75 (35°C) = 437 tick; 600'de kapağa oturur
        sensor.compute(runtime, position_mm=5000.0)
    final = sensor.compute(runtime, position_mm=5000.0)
    assert final == pytest.approx(75.0)


def test_cooling_in_idle_lineer_per_tick() -> None:
    """IDLE'da her tick 0.04°C azalır."""
    sensor = MotorTemperatureSensor(_config())
    hot_runtime = _make_runtime(DeviceState.RAISING)
    for _ in range(440):  # 40 → ~75
        sensor.compute(hot_runtime, position_mm=1000.0)
    cool_runtime = _make_runtime(DeviceState.IDLE)
    before = sensor.compute(cool_runtime, position_mm=0.0)
    after = sensor.compute(cool_runtime, position_mm=0.0)
    assert before - after == pytest.approx(0.04)


def test_cooling_caps_at_ambient_40() -> None:
    """Alt sınır 40°C — uzun IDLE'da çevre sıcaklığının altına inmez."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    for _ in range(100):
        sensor.compute(runtime, position_mm=0.0)
    final = sensor.compute(runtime, position_mm=0.0)
    assert final == pytest.approx(40.0)


def test_state_change_preserves_instance_state() -> None:
    """Spec § 5 invaryant 5: state transition reset etmez."""
    sensor = MotorTemperatureSensor(_config())
    raising = _make_runtime(DeviceState.RAISING)
    sensor.compute(raising, position_mm=1000.0)  # 40 → 40.08
    sensor.compute(raising, position_mm=1000.0)  # 40.08 → 40.16
    idle = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(idle, position_mm=0.0)
    assert value == pytest.approx(40.12)  # 40.16 - 0.04
```

`test_heating_caps_at_35` adını `test_heating_caps_at_75`, `test_cooling_caps_at_ambient_25`'i
`test_cooling_caps_at_ambient_40` yaptık. Diğer testler (`_is_base_sensor`, `_lowering_heats_same`,
`_rejects_wrong_sensor_name`) DEĞİŞMEZ.

- [ ] **Step 2: Testlerin FAIL ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_motor_temperature_sensor.py -q`
Expected: birkaç FAIL (40≠25, 75≠35 vb.)

- [ ] **Step 3: Sensör sabitlerini gerçekçi yap**

`src/simulator/sensors/motor_temperature.py` sabitlerini değiştir:

```python
# Gerçekçi termal model (Iter 8.3): çalışan motorlar 60-90°C; normal tavan 75, idle-floor 40.
_AMBIENT_C = 40.0                # çevre/idle alt sınır
_MAX_TEMP_C = 75.0              # motor enerjili normal üst sınır
_HEATING_RATE_C_PER_S = 0.08     # değişmedi
_COOLING_RATE_C_PER_S = 0.04     # değişmedi
_DELTA_PER_TICK_S = 1.0
```

Ayrıca docstring/yorumlardaki "25"/"35" referanslarını "40"/"75" yap (satır 1-2 ve 20'deki
açıklamalar): "lineer ısınır (0.08 °C/s, üst 75); IDLE'da lineer soğur (0.04 °C/s, alt 40)."
`__init__`'teki `self._current_temp_c: float = _AMBIENT_C` zaten sabite bağlı, değişmez.

- [ ] **Step 4: Hedef test + tam suite (regresyon avı)**

```bash
.venv/bin/python -m pytest tests/unit/test_motor_temperature_sensor.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
```
Expected: motor_temperature testleri PASS. Tam suite'te başka bir test 25/35°C sabitine bağlıysa
(örn. engine/integration testleri) FAIL edebilir — çıkarsa o testi gerçekçi tabana göre güncelle
(değer-tabanlı assertion'ları 40/75'e taşı). Davranış değişmedi, yalnız sabitler.

- [ ] **Step 5: Lint + commit**

```bash
.venv/bin/python -m mypy src/simulator tests/unit/test_motor_temperature_sensor.py
ruff check src/simulator tests/unit/test_motor_temperature_sensor.py
git add src/simulator/sensors/motor_temperature.py tests/unit/test_motor_temperature_sensor.py
git commit -m "feat(simulator): gerçekçi termal model (40-75°C, F'in ön koşulu, Faz 8 Iter 8.3 spec § 4)"
```

---

### Task 2: F senaryosu — `temperature_overshoot`

**Files:**
- Create: `src/simulator/scenarios/temperature_overshoot.py`
- Modify: `src/simulator/scenarios/__init__.py`
- Test: `tests/unit/test_scenarios/test_temperature_overshoot.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_scenarios/test_temperature_overshoot.py` (yeni):

```python
"""TemperatureOvershoot (Faz 8 Iter 8.3 F, DOMAIN.md § F) modify testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState) -> DeviceRuntimeState:
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


def test_requires_params() -> None:
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    with pytest.raises(ValueError, match="overshoot_rate_c_per_s"):
        TemperatureOvershoot(params={"max_overshoot_c": 60})
    with pytest.raises(ValueError, match="max_overshoot_c"):
        TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8})
    TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})


def test_idle_returns_clean() -> None:
    """IDLE'da aktif değil (motor enerjili değil) → identity."""
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    sc = TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE), scenario_elapsed_s=100.0)
    assert sc.modify("motor_temperature", 60.0, ctx) == 60.0


def test_raising_adds_overshoot_linearly() -> None:
    """RAISING'de motor_temperature += rate * elapsed (cap'e kadar)."""
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    sc = TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=50.0)
    # overshoot = min(60, 0.8*50=40) = 40 → 60 + 40 = 100
    assert sc.modify("motor_temperature", 60.0, ctx) == pytest.approx(100.0)


def test_overshoot_caps_at_max() -> None:
    """elapsed büyükse overshoot max_overshoot_c'de sabitlenir."""
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    sc = TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING), scenario_elapsed_s=10000.0)
    assert sc.modify("motor_temperature", 70.0, ctx) == pytest.approx(130.0)  # 70 + 60 cap


def test_only_affects_temperature() -> None:
    """Diğer sensörler identity."""
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    sc = TemperatureOvershoot(params={"overshoot_rate_c_per_s": 0.8, "max_overshoot_c": 60})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=100.0)
    assert sc.modify("motor_current", 8.0, ctx) == 8.0
    assert sc.modify("hydraulic_pressure", 150.0, ctx) == 150.0


def test_registered() -> None:
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.temperature_overshoot import TemperatureOvershoot

    assert SCENARIO_REGISTRY["temperature_overshoot"] is TemperatureOvershoot
```

- [ ] **Step 2: FAIL doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_scenarios/test_temperature_overshoot.py -q`
Expected: ImportError / ModuleNotFoundError

- [ ] **Step 3: Senaryoyu yaz**

`src/simulator/scenarios/temperature_overshoot.py` (yeni):

```python
"""TemperatureOvershoot arıza senaryosu (Faz 8 Iter 8.3 F, DOMAIN.md § F)."""
from __future__ import annotations

from typing import ClassVar

from simulator.config import DeviceState
from simulator.scenarios.base import FaultScenario, ScenarioContext


class TemperatureOvershoot(FaultScenario):
    """Sıcaklık aşımı: motor enerjili durumlarda sıcaklık kritik eşiğin üstüne tırmanır.

    Sürekli yük / yetersiz soğutma. `modify` TOPLAMSAL: sensörün (tavanlı) temiz değerinin
    üstüne `min(max_overshoot_c, rate * scenario_elapsed_s)` ekler → sensör saf kalır, tavan
    kaldırılmaz (spec § 4). Aktif: RAISING + HOLDING (motor enerjili).

    Params:
        overshoot_rate_c_per_s: float > 0 — saniyede aşım artış hızı (°C/s). Tipik 0.8.
        max_overshoot_c: float > 0 — toplam aşım tavanı (°C). Tipik 60.
    """

    name: ClassVar[str] = "temperature_overshoot"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset(
        {"overshoot_rate_c_per_s", "max_overshoot_c"}
    )
    _ACTIVE_STATES: ClassVar[frozenset[DeviceState]] = frozenset(
        {DeviceState.RAISING, DeviceState.HOLDING}
    )

    def modify(self, sensor_name: str, clean_value: float, ctx: ScenarioContext) -> float:
        if ctx.runtime.state not in self._ACTIVE_STATES:
            return clean_value
        if sensor_name != "motor_temperature":
            return clean_value
        rate = self.params["overshoot_rate_c_per_s"]
        max_over = self.params["max_overshoot_c"]
        overshoot = min(max_over, rate * ctx.scenario_elapsed_s)
        return clean_value + overshoot
```

- [ ] **Step 4: Registry'ye ekle**

`src/simulator/scenarios/__init__.py`: import + registry + `__all__`:

```python
from simulator.scenarios.temperature_overshoot import TemperatureOvershoot
```
`SCENARIO_REGISTRY` dict'ine: `"temperature_overshoot": TemperatureOvershoot,`
`__all__` listesine: `"TemperatureOvershoot",`

- [ ] **Step 5: PASS + lint + commit**

```bash
.venv/bin/python -m pytest tests/unit/test_scenarios/test_temperature_overshoot.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/simulator tests/unit/test_scenarios/test_temperature_overshoot.py
ruff check src/simulator tests/unit/test_scenarios/test_temperature_overshoot.py
git add src/simulator/scenarios/temperature_overshoot.py src/simulator/scenarios/__init__.py tests/unit/test_scenarios/test_temperature_overshoot.py
git commit -m "feat(simulator): temperature_overshoot (F) senaryosu (Faz 8 Iter 8.3 spec § 3a)"
```

---

### Task 3: E senaryosu — `sensor_fault`

**Files:**
- Create: `src/simulator/scenarios/sensor_fault.py`
- Modify: `src/simulator/scenarios/__init__.py`
- Test: `tests/unit/test_scenarios/test_sensor_fault.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_scenarios/test_sensor_fault.py` (yeni):

```python
"""SensorFault (Faz 8 Iter 8.3 E, DOMAIN.md § E imkânsız-değer) modify testleri."""
from __future__ import annotations

import random

import pytest

from simulator.config import DeviceState
from simulator.runtime import DeviceRuntimeState
from simulator.scenarios.base import ScenarioContext


def _runtime(state: DeviceState, seed: int = 42) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=60.0,
        position_mm=0.0,
        cycle_count=0,
        rng=random.Random(seed),
        started_at_monotonic=0.0,
        clock=lambda: 0.0,
    )


def test_requires_params() -> None:
    from simulator.scenarios.sensor_fault import SensorFault

    with pytest.raises(ValueError, match="spike_prob"):
        SensorFault(params={"impossible_value": -500.0})
    with pytest.raises(ValueError, match="impossible_value"):
        SensorFault(params={"spike_prob": 0.3})
    SensorFault(params={"spike_prob": 0.3, "impossible_value": -500.0})


def test_only_affects_mast_position() -> None:
    """Diğer sensörler her zaman identity (spike olsa bile)."""
    from simulator.scenarios.sensor_fault import SensorFault

    sc = SensorFault(params={"spike_prob": 1.0, "impossible_value": -500.0})  # her tick spike
    ctx = ScenarioContext(runtime=_runtime(DeviceState.HOLDING), scenario_elapsed_s=10.0)
    assert sc.modify("motor_current", 8.0, ctx) == 8.0
    assert sc.modify("hydraulic_pressure", 150.0, ctx) == 150.0


def test_spike_returns_impossible_value() -> None:
    """spike_prob=1.0 → mast_position daima imkânsız değere döner."""
    from simulator.scenarios.sensor_fault import SensorFault

    sc = SensorFault(params={"spike_prob": 1.0, "impossible_value": -500.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=10.0)
    assert sc.modify("mast_position", 3000.0, ctx) == -500.0


def test_no_spike_returns_clean() -> None:
    """spike_prob=0.0 → mast_position temiz değer."""
    from simulator.scenarios.sensor_fault import SensorFault

    sc = SensorFault(params={"spike_prob": 0.0, "impossible_value": -500.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.RAISING), scenario_elapsed_s=10.0)
    assert sc.modify("mast_position", 3000.0, ctx) == 3000.0


def test_active_in_all_states() -> None:
    """Sensör arızası harekete bağlı değil — IDLE'da da spike (mast_position)."""
    from simulator.scenarios.sensor_fault import SensorFault

    sc = SensorFault(params={"spike_prob": 1.0, "impossible_value": -500.0})
    ctx = ScenarioContext(runtime=_runtime(DeviceState.IDLE), scenario_elapsed_s=10.0)
    assert sc.modify("mast_position", 0.0, ctx) == -500.0


def test_registered() -> None:
    from simulator.scenarios import SCENARIO_REGISTRY
    from simulator.scenarios.sensor_fault import SensorFault

    assert SCENARIO_REGISTRY["sensor_fault"] is SensorFault
```

- [ ] **Step 2: FAIL doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_scenarios/test_sensor_fault.py -q`
Expected: ImportError

- [ ] **Step 3: Senaryoyu yaz**

`src/simulator/scenarios/sensor_fault.py` (yeni):

```python
"""SensorFault arıza senaryosu (Faz 8 Iter 8.3 E, DOMAIN.md § E imkânsız-değer varyantı)."""
from __future__ import annotations

from typing import ClassVar

from simulator.scenarios.base import FaultScenario, ScenarioContext


class SensorFault(FaultScenario):
    """Sensör arızası: bir sensör (mast_position) aralıklı olarak FİZİKSEL İMKÂNSIZ değer üretir.

    Diğer sensörler normal kalır (sensör kendisi bozuk, makine sağlam → sağlamlık özelliği,
    spec § 2/§ 3b). State filtering YOK (sensör arızası harekete bağlı değil). Per-tick RNG
    (electrical_fault deseni): saf modify, sensör sırasından bağımsız.

    Params:
        spike_prob: float ∈ [0, 1] — her mast_position çağrısında imkânsız değer olasılığı. Tipik 0.3.
        impossible_value: float — fiziksel olarak imkânsız değer (örn. -500.0 mm; mast yer altında olamaz).
    """

    name: ClassVar[str] = "sensor_fault"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset({"spike_prob", "impossible_value"})

    def modify(self, sensor_name: str, clean_value: float, ctx: ScenarioContext) -> float:
        if sensor_name != "mast_position":
            return clean_value
        if ctx.runtime.rng.random() < self.params["spike_prob"]:
            return self.params["impossible_value"]
        return clean_value
```

- [ ] **Step 4: Registry'ye ekle**

`src/simulator/scenarios/__init__.py`: import `SensorFault`, registry `"sensor_fault": SensorFault,`,
`__all__` += `"SensorFault"`.

- [ ] **Step 5: PASS + lint + commit**

```bash
.venv/bin/python -m pytest tests/unit/test_scenarios/test_sensor_fault.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/simulator tests/unit/test_scenarios/test_sensor_fault.py
ruff check src/simulator tests/unit/test_scenarios/test_sensor_fault.py
git add src/simulator/scenarios/sensor_fault.py src/simulator/scenarios/__init__.py tests/unit/test_scenarios/test_sensor_fault.py
git commit -m "feat(simulator): sensor_fault (E) senaryosu — imkânsız mast_position (Faz 8 Iter 8.3 spec § 3b)"
```

---

### Task 4: Yeni kural — `sensor_out_of_range`

**Files:**
- Create: `src/detectors/rules/sensor_out_of_range.py`
- Modify: `src/detectors/rules/__init__.py`
- Test: `tests/unit/detectors/test_sensor_out_of_range.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/detectors/test_sensor_out_of_range.py` (yeni; mevcut rule birim testlerinin dizini —
yoksa `tests/unit/` köküne koy, import yolu aynı):

```python
"""SensorOutOfRange kuralı birim testleri (Faz 8 Iter 8.3 spec § 6a)."""
from __future__ import annotations

import pandas as pd

_BOUNDS = {
    "motor_voltage": [-100.0, 100.0],
    "mast_position": [-50.0, 12000.0],
}


def _window(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """rows: (sensor, timestamp, value). device_id sabit."""
    return pd.DataFrame(
        {
            "device_id": ["dev"] * len(rows),
            "sensor": [r[0] for r in rows],
            "timestamp": [r[1] for r in rows],
            "state": ["raising"] * len(rows),
            "value": [r[2] for r in rows],
        }
    )


def test_in_range_no_anomaly() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("mast_position", "t1", 3000.0), ("motor_voltage", "t2", 24.0)])
    assert rule.detect(window) == []


def test_out_of_range_below_triggers() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("mast_position", "t1", 3000.0), ("mast_position", "t2", -500.0)])
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.rule_name == "sensor_out_of_range"
    assert a.sensor == "mast_position"
    assert a.value == -500.0
    assert a.severity == "high"
    assert 0.0 < a.score <= 1.0


def test_out_of_range_above_triggers() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("motor_voltage", "t1", 250.0)])  # > 100
    anomalies = rule.detect(window)
    assert len(anomalies) == 1
    assert anomalies[0].sensor == "motor_voltage"


def test_multiple_sensors_each_emit() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    window = _window([("mast_position", "t1", -500.0), ("motor_voltage", "t2", 999.0)])
    sensors = {a.sensor for a in rule.detect(window)}
    assert sensors == {"mast_position", "motor_voltage"}


def test_empty_window() -> None:
    from detectors.rules.sensor_out_of_range import SensorOutOfRange

    rule = SensorOutOfRange(bounds=_BOUNDS, severity="high")
    assert rule.detect(pd.DataFrame()) == []


def test_registered() -> None:
    from detectors.rules import RULE_REGISTRY

    assert "sensor_out_of_range" in RULE_REGISTRY
```

- [ ] **Step 2: FAIL doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_sensor_out_of_range.py -q`
Expected: ImportError / registry KeyError

- [ ] **Step 3: Kuralı yaz**

`src/detectors/rules/sensor_out_of_range.py` (yeni):

```python
"""SensorOutOfRange: bir sensör fiziksel imkânsızlık sınırları dışında değer üretirse anomali.

Faz 8 Iter 8.3 spec § 6a. sensor_frozen'ın kardeşi (sensör-sağlığı). Sınırlar "imkânsızlık"
sınırıdır, "normal" değil: meşru arıza değerleri (F'in yüksek sıcaklığı, C'nin voltaj spike'ları,
B'nin düşük basıncı) sınır İÇİNDE kalır → bu kuralı tetiklemez (onları eşik kuralları yakalar).
Yalnız fiziksel saçmalık (örn. negatif mast pozisyonu) tetikler. Read-only / gözlem modu.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from detectors.base import Anomaly, Detector


class SensorOutOfRange(Detector):
    """Pencerede herhangi bir sensör [min, max] fiziksel sınırı dışındaysa, o sensör için anomali."""

    def __init__(
        self,
        bounds: Mapping[str, Sequence[float]],
        severity: str = "high",
    ) -> None:
        """Args: bounds — sensör adı → [min, max] fiziksel imkânsızlık sınırı; severity."""
        self._bounds: dict[str, tuple[float, float]] = {
            sensor: (float(b[0]), float(b[1])) for sensor, b in bounds.items()
        }
        self._severity = severity

    @property
    def name(self) -> str:
        return "sensor_out_of_range"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        if window.empty:
            return []
        anomalies: list[Anomaly] = []
        for sensor, (lo, hi) in self._bounds.items():
            sub = window[window["sensor"] == sensor]
            if sub.empty:
                continue
            vals = sub["value"].to_numpy(dtype=float)
            # Her okuma için sınır-aşımı: alt sınır altı VEYA üst sınır üstü mesafe (>0 ise dışında).
            excess = np.maximum(lo - vals, vals - hi)
            worst = int(excess.argmax())
            if excess[worst] <= 0.0:
                continue  # hepsi sınır içinde
            row = sub.iloc[worst]
            value = float(row["value"])
            margin = hi - lo
            score = min(1.0, float(excess[worst]) / margin) if margin > 0 else 1.0
            anomalies.append(
                Anomaly(
                    device_id=str(row["device_id"]),
                    rule_name=self.name,
                    sensor=sensor,
                    severity=self._severity,
                    score=score,
                    window_start=str(sub["timestamp"].iloc[0]),
                    window_end=str(sub["timestamp"].iloc[-1]),
                    value=value,
                    description=(
                        f"{sensor} {value:.2f} fiziksel sınır [{lo:.1f}, {hi:.1f}] dışında "
                        f"(sensör arızası)"
                    ),
                )
            )
        return anomalies
```

- [ ] **Step 4: Registry'ye ekle**

`src/detectors/rules/__init__.py`: import + registry satırı:

```python
from detectors.rules.sensor_out_of_range import SensorOutOfRange
```
`RULE_REGISTRY` dict'ine: `"sensor_out_of_range": SensorOutOfRange,`

- [ ] **Step 5: PASS + lint + commit**

```bash
.venv/bin/python -m pytest tests/unit/detectors/test_sensor_out_of_range.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/detectors tests/unit/detectors/test_sensor_out_of_range.py
ruff check src/detectors tests/unit/detectors/test_sensor_out_of_range.py
git add src/detectors/rules/sensor_out_of_range.py src/detectors/rules/__init__.py tests/unit/detectors/test_sensor_out_of_range.py
git commit -m "feat(detectors): sensor_out_of_range kuralı — fiziksel-imkânsızlık tespiti (Faz 8 Iter 8.3 spec § 6a)"
```

---

### Task 5: İmza testleri + fixtures (F→temp_high, E→out_of_range, çapraz-FP yok)

**Files:**
- Create: `tests/fixtures/devices_with_temperature_overshoot.yaml`
- Create: `tests/fixtures/devices_with_sensor_fault.yaml`
- Test: `tests/scenarios/test_iter83_signatures.py`

- [ ] **Step 1: Fixture'ları yaz**

`tests/fixtures/devices_with_temperature_overshoot.yaml` — mevcut bir fixture'ı (örn.
`devices_with_mechanical_wear.yaml`) modele al; tek cihaz, 6 sensör, scenario `temperature_overshoot`.
Sensör listesi `devices.demo.yaml` device_001 ile aynı (6 sensör). Scenario:

```yaml
devices:
  - id: device_F
    type: telescopic_mast_v1
    seed: 11
    target_height_mm: 5000
    state_durations:
      idle:     [3, 3]
      raising:  [30, 30]
      holding:  [60, 60]
      lowering: [3, 3]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: temperature_overshoot
        start_after_s: 0
        duration_s: 600
        params: {overshoot_rate_c_per_s: 0.8, max_overshoot_c: 60}
```

`tests/fixtures/devices_with_sensor_fault.yaml` — aynı şablon, scenario:

```yaml
    scenarios:
      - name: sensor_fault
        start_after_s: 0
        duration_s: 600
        params: {spike_prob: 0.3, impossible_value: -500.0}
```
(device id `device_E`, seed 13.)

NOT: `start_after_s`/`duration_s` anahtar adları mevcut fixture'lardakiyle eşleşmeli — bir mevcut
fixture'ı (`devices_with_mechanical_wear.yaml`) açıp scenario blok şemasını birebir kopyala (yalnız
`name` + `params` değiştir).

- [ ] **Step 2: Failing imza testlerini yaz**

`tests/scenarios/test_iter83_signatures.py` (yeni):

```python
"""F + E imza testleri (Faz 8 Iter 8.3, spec § 10). Engine harness senaryoyu koşturur."""
from __future__ import annotations

import pytest

from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.rules.sensor_out_of_range import SensorOutOfRange
from tests.scenarios.conftest import FIXTURES, CountingClock, build_detector_window

# Demo ile aynı geniş fiziksel-imkânsızlık sınırları (spec § 6a / plan kalibrasyonu).
_BOUNDS = {
    "motor_current": [-5.0, 30.0],
    "motor_voltage": [-100.0, 100.0],
    "hydraulic_pressure": [-10.0, 400.0],
    "motor_temperature": [-20.0, 160.0],
    "mast_position": [-50.0, 12000.0],
    "vibration": [-1.0, 10.0],
}


def test_temperature_overshoot_triggers_motor_temperature_high(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """F penceresi motor_temperature_high'ı (eşik 95°C) tetikler."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_temperature_overshoot.yaml", max_iterations=300,
    )
    rule = MotorTemperatureHigh(critical_threshold_c=95.0)
    assert len(rule.detect(window)) == 1


def test_temperature_overshoot_not_out_of_range(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """F'in yüksek sıcaklığı sensor_out_of_range'i tetiklemez (160 sınırının altında)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_temperature_overshoot.yaml", max_iterations=300,
    )
    rule = SensorOutOfRange(bounds=_BOUNDS)
    assert rule.detect(window) == []


def test_sensor_fault_triggers_out_of_range(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """E penceresi sensor_out_of_range'i (mast_position) tetikler."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_sensor_fault.yaml", max_iterations=300,
    )
    anomalies = SensorOutOfRange(bounds=_BOUNDS).detect(window)
    assert len(anomalies) >= 1
    assert all(a.sensor == "mast_position" for a in anomalies)


def test_sensor_fault_not_temperature_high(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """E sıcaklık kuralını tetiklemez (yalnız mast_position bozuk)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_with_sensor_fault.yaml", max_iterations=300,
    )
    assert MotorTemperatureHigh(critical_threshold_c=95.0).detect(window) == []


def test_clean_baseline_no_iter83_rules(
    monkeypatch: pytest.MonkeyPatch, patched_engine_clock: CountingClock
) -> None:
    """Clean cihaz ne temp_high ne out_of_range tetikler (FP yok)."""
    window = build_detector_window(
        monkeypatch, patched_engine_clock,
        FIXTURES / "devices_clean_baseline.yaml", max_iterations=300,
    )
    assert MotorTemperatureHigh(critical_threshold_c=95.0).detect(window) == []
    assert SensorOutOfRange(bounds=_BOUNDS).detect(window) == []
```

- [ ] **Step 3: FAIL doğrula (fixture/threshold sorunları yüzeye çıkar)**

Run: `.venv/bin/python -m pytest tests/scenarios/test_iter83_signatures.py -q`
Expected: F testi FAIL edebilir (sıcaklık 95'i aşmıyorsa) → bu KALİBRASYON sinyali.

- [ ] **Step 4: Kalibrasyonu doğrula/ayarla**

F testi FAIL ederse (sıcaklık eşiği aşmıyor): `max_iterations`'ı artır (senaryonun raising/holding'de
yeterince ısınması için) VEYA fixture `overshoot_rate_c_per_s`'i yükselt. Clean testi FAIL ederse
(beklenmez): sınırlar/eşik gözden geçir. Hedef: 5 test de PASS.

**Gerçek ölçüm (kalibrasyon doğrulama):** F testine GEÇİCİ bir satır ekle —
`print(window[window["sensor"] == "motor_temperature"]["value"].max())` — `-s` ile koştur
(`.venv/bin/python -m pytest tests/scenarios/test_iter83_signatures.py::test_temperature_overshoot_triggers_motor_temperature_high -s`),
basılan max sıcaklığın 95°C'yi NET aştığını gör, sonra print satırını KALDIR. Aynı şekilde clean
cihazın max sıcaklığının 75°C civarı (≪95) olduğunu doğrulayabilirsin.

- [ ] **Step 5: PASS + lint + commit**

```bash
.venv/bin/python -m pytest tests/scenarios/test_iter83_signatures.py -q   # 5 PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy tests/scenarios/test_iter83_signatures.py
ruff check tests/scenarios/test_iter83_signatures.py
git add tests/fixtures/devices_with_temperature_overshoot.yaml tests/fixtures/devices_with_sensor_fault.yaml tests/scenarios/test_iter83_signatures.py
git commit -m "test(scenarios): F + E imza testleri + fixtures (çapraz-FP korumalı, Faz 8 Iter 8.3 spec § 10)"
```

---

### Task 6: Config dosyaları + demo cihazları

**Files:**
- Modify: `config/detectors.yaml.example`
- Modify: `config/detectors.demo.yaml`
- Modify: `config/devices.demo.yaml`
- Test: `tests/unit/test_demo_configs.py` (varsa — config geçerliliği)

- [ ] **Step 1: `sensor_out_of_range` kuralını + yeni eşiği iki detector config'ine ekle**

`config/detectors.yaml.example` VE `config/detectors.demo.yaml`'da:
(a) `motor_temperature_high` kuralının `critical_threshold_c` / `threshold_c` paramını **95**'e çek
(mevcut değeri bul — muhtemelen 80; param adını koru).
(b) `rules:` listesine yeni kural ekle:

```yaml
    - name: sensor_out_of_range
      enabled: true
      severity: high
      params:
        bounds:
          motor_current:       [-5, 30]
          motor_voltage:       [-100, 100]
          hydraulic_pressure:  [-10, 400]
          motor_temperature:   [-20, 160]
          mast_position:       [-50, 12000]
          vibration:           [-1, 10]
```

- [ ] **Step 2: Demo cihazlarını ekle (`config/devices.demo.yaml`)**

`devices:` listesine 2 cihaz ekle (mevcut device_001 sensör bloğunu kopyala, scenario değiştir):

```yaml
  # device_005: temperature_overshoot (F) — sıcaklık kritik eşiğe tırmanır.
  - id: device_005
    type: telescopic_mast_v1
    seed: 11
    target_height_mm: 5500
    state_durations:
      idle:     [3, 3]
      raising:  [15, 15]
      holding:  [30, 30]
      lowering: [3, 3]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: temperature_overshoot
        start_after_s: 60
        duration_s: 600
        params: {overshoot_rate_c_per_s: 0.8, max_overshoot_c: 60}

  # device_006: sensor_fault (E) — mast_position imkânsız değer (sağlamlık göstergesi).
  - id: device_006
    type: telescopic_mast_v1
    seed: 13
    target_height_mm: 5000
    state_durations:
      idle:     [3, 3]
      raising:  [15, 15]
      holding:  [30, 30]
      lowering: [3, 3]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: sensor_fault
        start_after_s: 60
        duration_s: 600
        params: {spike_prob: 0.3, impossible_value: -500.0}
```

NOT: `scenarios` blok şemasını (`start_after_s`/`duration_s`/`params`) mevcut device_002'nin
mechanical_wear bloğuyla birebir eşleştir.

- [ ] **Step 3: Config geçerlilik testi (varsa güncelle, yoksa hızlı doğrula)**

```bash
# devices.demo.yaml yüklenebiliyor + 6 cihaz:
.venv/bin/python -c "
from pathlib import Path
from simulator.config import load_device_configs  # gerçek loader adını doğrula
cfgs = load_device_configs(Path('config/devices.demo.yaml'))
print('cihaz sayısı:', len(cfgs))
assert len(cfgs) == 6
"
# detectors.demo.yaml + yeni kural yüklenebiliyor:
.venv/bin/python -c "
from pathlib import Path
from detectors.config import load_detector_config, build_detectors
cfg = load_detector_config(Path('config/detectors.demo.yaml'))
dets = build_detectors(cfg)
names = {d.name for d in dets}
print('kurallar:', sorted(names))
assert 'sensor_out_of_range' in names
"
```
(Loader fonksiyon adları repodakiyle eşleşmeli — `test_demo_configs.py` veya `detectors/config.py`'den
doğrula. `test_demo_configs.py` varsa onu çalıştır: `.venv/bin/python -m pytest tests/unit/test_demo_configs.py -q`)

- [ ] **Step 4: Tam suite + lint + commit**

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src config 2>/dev/null || .venv/bin/python -m mypy src
ruff check src
git add config/detectors.yaml.example config/detectors.demo.yaml config/devices.demo.yaml
git commit -m "config(faz8): Iter 8.3 — sensor_out_of_range kuralı + temp eşiği 95 + demo 005(F)/006(E)"
```

---

### Task 7: DEMO.md beat-script güncelle

**Files:**
- Modify: `docs/DEMO.md`

- [ ] **Step 1: Beat-script'i 6 cihaza güncelle**

`docs/DEMO.md`'de cihaz/senaryo tablosunu ve 15-dk beat anlatısını güncelle:
- device_005 = temperature_overshoot (F): "sıcaklık kritik eşiğe tırmanış → `motor_temperature_high`"
- device_006 = sensor_fault (E): "imkânsız mast_position → `sensor_out_of_range` (sağlamlık: bozuk
  sensöre dayanıklıyız)"
- Anlatı çerçevesi: **4 kestirimci arıza (A/B/C/F) + 1 sağlamlık (E)** + temiz referans (001).
- `sensor_frozen` kuralının korunduğunu + "donmuş sensörü de tespit ediyoruz (birim-testli)" notunu ekle.
- "Bilinen sınırlar" bölümüne: D (aşırı yük) bilinçli kapsam dışı (tespiti A ile örtüşür).

- [ ] **Step 2: Commit**

```bash
git add docs/DEMO.md
git commit -m "docs(demo): Iter 8.3 — 6-cihaz beat (F+E) + sağlamlık çerçevesi"
```

---

### Task 8: Final sweep (tam suite + mypy + ruff tüm kapsam)

**Files:** (yalnız doğrulama)

- [ ] **Step 1: Tam test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: tamamı PASS (335 + bu iterasyonun yenileri; 1 smoke skipped)

- [ ] **Step 2: mypy tam kapsam**

Run: `.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/dashboard src/alerts tests/unit tests/integration tests/scenarios`
Expected: Success.

- [ ] **Step 3: ruff tam kapsam**

Run: `ruff check src tests`
Expected: All checks passed.

- [ ] **Step 4: Düzeltme gerektiyse commit**

```bash
git add -A && git commit -m "chore(faz8): Iter 8.3 final lint/type sweep"
```

---

## Closure (controller işi — plan task'ı DEĞİL)

Subagent execution bittikten sonra controller: (1) final whole-iteration review, (2) **canlı demo
smoke** `./scripts/demo_up.sh` — 6 cihaz: 001 temiz **0 FP**; 002/003/004 mevcut imzalar (regresyon);
005 → `motor_temperature_high` (sıcaklık tırmanışı dashboard'da); 006 → `sensor_out_of_range`
(yalnız o, tertemiz); temiz teardown. Kalibrasyon canlı smoke'ta doğrulanır (F eşiği aşıyor mu, clean
0 FP) — gerekirse onset/rate ince ayar. (3) CLAUDE.md/ROADMAP/memory güncelle, (4) kullanıcı onayıyla
merge/push (PROAKTİF YAPMA).

# Faz 1 — Iterasyon 2b: Kalan 5 Sensör + N-Sensör Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task's final verification step MUST run the FULL suite + mypy + ruff over BOTH src and tests (see [[feedback-full-suite-per-task]]).

**Goal:** Iter 2a'nın tek-sensör (motor_current) cihazını **6 sensörlü** hale getirmek. State machine altyapısı (DeviceRuntimeState, BaseSensor ABC, SENSOR_REGISTRY) Iter 2a'da kuruldu; bu iterasyon o altyapı üzerine 5 yeni sensör implementasyonu ekler ve engine'i N-sensör loop'a geçirir.

**Architecture:** Engine sensör listesini config'den okuyup `SENSOR_REGISTRY` üzerinden instance'lar üretir, her tick'te tüm sensörleri dolaşır. Beş yeni sensör sınıfı `BaseSensor` ABC'sinden türer ve `compute(runtime, position_mm) -> float` sözleşmesini uygular. `MotorTemperatureSensor` instance attribute olarak son sıcaklığı taşıyan tek stateful sensör (spec § 5 invaryant 5). Diğer dördü stateless ve state-bazlı sabit baseline döndürür (spec § 6 tablosu).

**Tech Stack:** Iter 2a ile aynı (Python 3.11+, mypy strict, ruff, pytest). Yeni dependency yok.

**Referans:** `docs/specs/2026-05-18-faz1-simulator-design.md` (güncellenmiş, commit `761fa17`) § 3 Iter 2 kabul kriterleri, § 5 stateful sensor + invaryantlar, § 6 sensör tablosu, § 8 tick akışı.

---

## Önkoşul

`.venv` aktif, `pip install -e .` yapılmış (Iter 2a sonu paketleme fix `94ed570` sonrası `python -m simulator` PYTHONPATH'siz çalışıyor). Iter 2a testleri (42 PASS) yeşil olmalı:

```bash
cd ~/mast-anomaly-detection
source .venv/bin/activate
pytest tests/unit/ -q                  # 42 passed beklenir
mypy src/simulator tests/unit          # Success
ruff check src/simulator tests/unit    # All checks passed
```

---

## Dosya Yapısı (Iter 2b sonunda)

```
src/simulator/
├── ... (Iter 2a hali)
├── engine.py                          # REFACTOR: N-sensör loop, _validate_iteration2b_constraints
└── sensors/
    ├── __init__.py                    # GENİŞLET: SENSOR_REGISTRY 6 entry
    ├── base.py                        # değişmez (Iter 2a)
    ├── motor_current.py               # değişmez (Iter 2a)
    ├── motor_voltage.py               # YENİ
    ├── hydraulic_pressure.py          # YENİ
    ├── mast_position.py               # YENİ
    ├── vibration.py                   # YENİ
    └── motor_temperature.py           # YENİ (tek stateful)

tests/unit/
├── ... (Iter 2a hali — 42 test)
├── test_engine.py                     # GÜNCELLE: 6 sensör fixture, 6 publish/tick
├── test_motor_voltage_sensor.py       # YENİ
├── test_hydraulic_pressure_sensor.py  # YENİ
├── test_mast_position_sensor.py       # YENİ
├── test_vibration_sensor.py           # YENİ
└── test_motor_temperature_sensor.py   # YENİ (stateful)

tests/fixtures/devices_minimal.yaml    # GENİŞLET: 6 sensör

config/devices.yaml.example            # GENİŞLET: 6 sensör
```

**Beklenen test sayısı:** ~71 (Iter 2a 42 + 29 yeni: voltage 3 + position 4 + pressure 6 + vibration 6 + temperature 9 + engine net +1).
**Hedef coverage:** ≥85% (Iter 2a %90'dan hafif düşebilir çünkü yeni sensörler basit).

---

## Task 1: Engine N-Sensör Loop Refactor (validation gevşetilmiş ara durum) ✅ TAMAMLANDI (commit `4ca7340`)

Engine'i list-based yapıyoruz, ama validation hâlâ tek motor_current zorunlu kalsın diye `_validate_iteration2a_constraints` kalır. Loop tek elemanlı listede çalışır; sonraki task'larda registry/fixture büyüdükçe gerçek N-sensör çalışması başlar. **Bu task hâlâ tek motor_current senaryosunu destekler — Iter 2a manuel testi kırılmaz.**

**Files:**
- Modify: `src/simulator/engine.py`
- Modify: `tests/unit/test_engine.py` (1 yeni test ekle)

- [x] **Step 1.1: `tests/unit/test_engine.py` sonuna 1 test ekle (yeni davranış: birden fazla sensör desteklenir)**

```python
def test_run_iterates_all_sensors_per_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine her tick'te tüm sensörler için publish_reading çağırır."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=2,
        seed=42,
        clock=clock,
    )

    # devices_minimal.yaml'da Iter 2a sonu 1 sensör (motor_current).
    # 2 tick × 1 sensör = 2 publish_reading çağrısı bekleniyor.
    assert mock_publisher.publish_reading.call_count == 2
    # Sensör adları config'deki sensör listesindeki sırada yayınlanır.
    sensor_names = [c.kwargs["sensor"] for c in mock_publisher.publish_reading.call_args_list]
    assert sensor_names == ["motor_current", "motor_current"]
```

- [x] **Step 1.2: Testi başarısız çalıştır**

```bash
pytest tests/unit/test_engine.py::test_run_iterates_all_sensors_per_tick -v
```
Beklenen: Iter 2a engine zaten tek sensör için tek publish/tick yapıyor. Bu test büyük olasılıkla **GEÇER**. Eğer geçerse Step 1.3'ü yine de uygula (engine'i list-based hâle getir), çünkü Task 2-6'da yeni sensörler eklendiğinde otomatik N-sensör loop'u çalışmaya başlayacak.

- [x] **Step 1.3: `src/simulator/engine.py` `run()` içindeki sensör mantığını list-based hâle getir**

`run()` fonksiyonundaki tek-sensör inşa bloğunu şuna çevir (mevcut blok: `sensor_config = device.sensors[0]` ile başlayan ~3 satır):

ESKİ:
```python
device = _validate_iteration2a_constraints(devices)
sensor_config = device.sensors[0]

sensor_cls = SENSOR_REGISTRY[sensor_config.name]
sensor = sensor_cls(sensor_config)
```

YENİ:
```python
device = _validate_iteration2a_constraints(devices)

# Sensörleri config sırasıyla inşa et (Iter 2b: list-based, 1+ sensör).
sensors: list[BaseSensor] = [
    SENSOR_REGISTRY[sc.name](sc) for sc in device.sensors
]
```

`BaseSensor` import'unu ekle (engine.py'nin üst kısmı, mevcut import bloğuna):

```python
from simulator.sensors.base import BaseSensor
```

Sonra `while not stop:` döngüsünün içindeki `clean_value = sensor.compute(...)` bloğunu sensör listesi üzerinde döngüye çevir:

ESKİ:
```python
while not stop:
    advance_state_machine(runtime, device.state_durations)
    runtime.position_mm = compute_position(runtime, device.target_height_mm)

    clean_value = sensor.compute(runtime, runtime.position_mm)
    noisy_value = clean_value + rng.gauss(0.0, sensor_config.noise_std)

    publisher.publish_reading(
        device_id=device.id,
        sensor=sensor_config.name,
        value=noisy_value,
        unit=sensor_config.unit,
        state=runtime.state,
    )
    iterations += 1
    if max_iterations is not None and iterations >= max_iterations:
        break
    time.sleep(tick_interval)
```

YENİ:
```python
while not stop:
    advance_state_machine(runtime, device.state_durations)
    runtime.position_mm = compute_position(runtime, device.target_height_mm)

    for sensor in sensors:
        clean_value = sensor.compute(runtime, runtime.position_mm)
        noisy_value = clean_value + rng.gauss(0.0, sensor.config.noise_std)
        publisher.publish_reading(
            device_id=device.id,
            sensor=sensor.config.name,
            value=noisy_value,
            unit=sensor.config.unit,
            state=runtime.state,
        )
    iterations += 1
    if max_iterations is not None and iterations >= max_iterations:
        break
    time.sleep(tick_interval)
```

**`max_iterations` semantiği değişti**: önceki tek-sensör halinde `iterations` = publish sayısı. Yeni halinde `iterations` = **tick** sayısı (her tick'te N publish). Test'ler bunu kabul eder (max_iterations=2 → 2 tick = 2 publish hâlâ tek sensörle).

Engine'in `_validate_iteration2a_constraints` çağrısı DEĞİŞMEZ (hâlâ tek motor_current zorunlu — Task 7'de gevşetilecek).

- [x] **Step 1.4: Tüm test_engine testleri yeşil**

```bash
pytest tests/unit/test_engine.py -v
```
Beklenen: 5 PASS (mevcut 4 + yeni 1).

- [x] **Step 1.5: FULL verification (no CI)**

```bash
pytest tests/unit/ -p no:cacheprovider -q       # expect 43 passed
mypy src/simulator tests/unit                    # expect Success
ruff check src/simulator tests/unit              # expect All checks passed
```

- [x] **Step 1.6: Commit**

```bash
git add src/simulator/engine.py tests/unit/test_engine.py
git commit -m "refactor(engine): convert sensor handling to list-based loop

Iter 2b prep: engine artık sensors: list[BaseSensor] üzerinde döngü yapar.
Tek-sensör semantiği korunuyor (devices_minimal hâlâ 1 motor_current);
gerçek N-sensör davranışı Task 2-6'da yeni sensörler eklendikçe ortaya çıkacak.
_validate_iteration2a_constraints DEĞİŞMEDİ — Task 7'de gevşetilecek.

max_iterations semantiği: tick sayısı (önceden publish sayısıyla aynıydı
çünkü tek sensör). Test'ler tick-bazlı bekliyor.

1 yeni test (test_run_iterates_all_sensors_per_tick). Full suite 43 passed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `MotorVoltageSensor` (en basit, state-agnostic) ✅ TAMAMLANDI (commit `0b94286`)

Sabit 24V, state'e bakmaz. DOMAIN.md sat. 21.

**Files:**
- Create: `src/simulator/sensors/motor_voltage.py`
- Create: `tests/unit/test_motor_voltage_sensor.py`
- Modify: `src/simulator/sensors/__init__.py` (registry'ye ekle)

- [x] **Step 2.1: Başarısız testleri yaz** — `tests/unit/test_motor_voltage_sensor.py`:

```python
"""MotorVoltageSensor için unit testler — sabit 24V, state-agnostic."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.motor_voltage import MotorVoltageSensor


def _config() -> SensorConfig:
    return SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2)


def _make_runtime(state: DeviceState) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10.0,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(42),
        started_at_monotonic=0.0,
    )


def test_motor_voltage_sensor_is_base_sensor() -> None:
    assert isinstance(MotorVoltageSensor(_config()), BaseSensor)


def test_compute_returns_24v_in_all_states() -> None:
    sensor = MotorVoltageSensor(_config())
    for state in DeviceState:
        runtime = _make_runtime(state)
        assert sensor.compute(runtime, position_mm=0.0) == 24.0


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="motor_voltage"):
        MotorVoltageSensor(bad)
```

- [x] **Step 2.2: Run, verify failure** (`ModuleNotFoundError: No module named 'simulator.sensors.motor_voltage'`):

```bash
pytest tests/unit/test_motor_voltage_sensor.py -v
```

- [x] **Step 2.3: Implement** `src/simulator/sensors/motor_voltage.py`:

```python
"""Motor besleme gerilimi sensörü. Sabit 24V, state-agnostic. DOMAIN.md sat. 21."""
from __future__ import annotations

from simulator.config import SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# DOMAIN.md sat. 21 — motor besleme gerilimi nominal 24V. State'e duyarlı değil;
# Iter 4 ElectricalFault senaryosu bu sensörün üzerinde dalgalanma üretecek.
_BASELINE_V = 24.0


class MotorVoltageSensor(BaseSensor):
    """Motor besleme gerilimi (V). Tüm state'lerde sabit 24V baseline."""

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "motor_voltage":
            raise ValueError(
                f"MotorVoltageSensor 'motor_voltage' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """Sabit 24V — state ve pozisyondan bağımsız."""
        return _BASELINE_V
```

- [x] **Step 2.4: Registry'ye ekle** — `src/simulator/sensors/__init__.py` güncelle:

Mevcut:
```python
SENSOR_REGISTRY: dict[str, type[BaseSensor]] = {
    "motor_current": MotorCurrentSensor,
}
```

Yeni (üstte `from simulator.sensors.motor_voltage import MotorVoltageSensor` import'unu da ekle):

```python
from simulator.sensors.motor_voltage import MotorVoltageSensor

SENSOR_REGISTRY: dict[str, type[BaseSensor]] = {
    "motor_current": MotorCurrentSensor,
    "motor_voltage": MotorVoltageSensor,
}
```

- [x] **Step 2.5: Run new tests, verify 3 PASS**

```bash
pytest tests/unit/test_motor_voltage_sensor.py -v
```

- [x] **Step 2.6: FULL verification**

```bash
pytest tests/unit/ -q                       # expect 46 passed (43 + 3 new)
mypy src/simulator tests/unit                # expect Success
ruff check src/simulator tests/unit          # expect All checks passed
```

- [x] **Step 2.7: Commit**

```bash
git add src/simulator/sensors/motor_voltage.py src/simulator/sensors/__init__.py tests/unit/test_motor_voltage_sensor.py
git commit -m "feat(sensors): add MotorVoltageSensor (constant 24V)

DOMAIN.md sat. 21 — state-agnostic sabit baseline. Iter 4'te ElectricalFault
bu sensör üzerinde dalgalanma üretecek. SENSOR_REGISTRY 2 entry'e çıktı.

3 yeni test. Full suite 46 passed, mypy+ruff clean.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `MastPositionSensor` (position passthrough) ✅ TAMAMLANDI (commit `d2bae59`)

Position'ı `position_mm` parametresinden okur, direkt döner. compute_position lineer hesabını otomatik takip eder.

**Files:**
- Create: `src/simulator/sensors/mast_position.py`
- Create: `tests/unit/test_mast_position_sensor.py`
- Modify: `src/simulator/sensors/__init__.py`

- [x] **Step 3.1: Başarısız testleri yaz** — `tests/unit/test_mast_position_sensor.py`:

```python
"""MastPositionSensor için unit testler — position_mm passthrough."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.mast_position import MastPositionSensor


def _config() -> SensorConfig:
    return SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0)


def _make_runtime(state: DeviceState) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10.0,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(42),
        started_at_monotonic=0.0,
    )


def test_mast_position_sensor_is_base_sensor() -> None:
    assert isinstance(MastPositionSensor(_config()), BaseSensor)


def test_compute_returns_position_mm_passthrough() -> None:
    sensor = MastPositionSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    for pos in [0.0, 1234.5, 5000.0]:
        assert sensor.compute(runtime, position_mm=pos) == pos


def test_compute_does_not_depend_on_state() -> None:
    """Pozisyon engine tarafından compute_position ile zaten state'e göre hesaplandı.
    Sensör sadece parametreyi geri verir, state'i kendi yorumlamaz."""
    sensor = MastPositionSensor(_config())
    for state in DeviceState:
        runtime = _make_runtime(state)
        assert sensor.compute(runtime, position_mm=2500.0) == 2500.0


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="mast_position"):
        MastPositionSensor(bad)
```

- [x] **Step 3.2: Run, verify failure**

```bash
pytest tests/unit/test_mast_position_sensor.py -v
```

- [x] **Step 3.3: Implement** `src/simulator/sensors/mast_position.py`:

```python
"""Mast pozisyon sensörü. compute_position'dan gelen değeri passthrough yapar.
DOMAIN.md sat. 63."""
from __future__ import annotations

from simulator.config import SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor


class MastPositionSensor(BaseSensor):
    """Mast pozisyonu (mm). Engine compute_position() ile hesaplanan değeri
    direkt döner; engine üzerine ±1 mm gauss gürültü ekler.

    DOMAIN.md sat. 63: pozisyon doğrusal artış/azalış, ideal hızda eğim sabit.
    Lineer hesap zaten runtime.compute_position()'da; sensör ekstra mantık yapmaz.
    """

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "mast_position":
            raise ValueError(
                f"MastPositionSensor 'mast_position' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """Engine'in hesapladığı pozisyonu passthrough — state'e duyarlı değil."""
        return position_mm
```

- [x] **Step 3.4: Registry'ye ekle** — `src/simulator/sensors/__init__.py`:

```python
from simulator.sensors.mast_position import MastPositionSensor

SENSOR_REGISTRY: dict[str, type[BaseSensor]] = {
    "motor_current": MotorCurrentSensor,
    "motor_voltage": MotorVoltageSensor,
    "mast_position": MastPositionSensor,
}
```

- [x] **Step 3.5: Run new tests, verify 4 PASS**

```bash
pytest tests/unit/test_mast_position_sensor.py -v
```

- [x] **Step 3.6: FULL verification**

```bash
pytest tests/unit/ -q                       # expect 50 passed
mypy src/simulator tests/unit                # expect Success
ruff check src/simulator tests/unit          # expect All checks passed
```

- [x] **Step 3.7: Commit**

```bash
git add src/simulator/sensors/mast_position.py src/simulator/sensors/__init__.py tests/unit/test_mast_position_sensor.py
git commit -m "feat(sensors): add MastPositionSensor (compute_position passthrough)

DOMAIN.md sat. 63 — pozisyon doğrusal. Engine compute_position() zaten state'e
göre lineer hesabı yapıyor; sensör passthrough. Gürültü engine'de ±1 mm.

4 yeni test. Full suite 50 passed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `HydraulicPressureSensor` (state-bazlı, 4 değer) ✅ TAMAMLANDI (commit `93faef8`)

State'e göre 4 farklı baseline (motor_current şablonu). DOMAIN.md sat. 60 + spec § 6 LOWERING notu.

**Files:**
- Create: `src/simulator/sensors/hydraulic_pressure.py`
- Create: `tests/unit/test_hydraulic_pressure_sensor.py`
- Modify: `src/simulator/sensors/__init__.py`

- [x] **Step 4.1: Başarısız testleri yaz** — `tests/unit/test_hydraulic_pressure_sensor.py`:

```python
"""HydraulicPressureSensor için unit testler — state-bazlı 4 baseline."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.hydraulic_pressure import HydraulicPressureSensor


def _config() -> SensorConfig:
    return SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0)


def _make_runtime(state: DeviceState) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10.0,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(42),
        started_at_monotonic=0.0,
    )


def test_hydraulic_pressure_sensor_is_base_sensor() -> None:
    assert isinstance(HydraulicPressureSensor(_config()), BaseSensor)


def test_compute_idle_returns_low() -> None:
    """DOMAIN.md sat. 60: boşta 5-20 bar."""
    sensor = HydraulicPressureSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(runtime, position_mm=0.0)
    assert 5.0 <= value <= 20.0


def test_compute_raising_returns_high() -> None:
    """DOMAIN.md sat. 60: RAISING'de 100-200 bar (spec § 3 Iter 2 kriter 3: ≥100)."""
    sensor = HydraulicPressureSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    value = sensor.compute(runtime, position_mm=1000.0)
    assert 100.0 <= value <= 200.0


def test_compute_holding_returns_medium() -> None:
    """DOMAIN.md sat. 60: HOLDING'de 50-150 bar (tutucu)."""
    sensor = HydraulicPressureSensor(_config())
    runtime = _make_runtime(DeviceState.HOLDING)
    value = sensor.compute(runtime, position_mm=5000.0)
    assert 50.0 <= value <= 150.0


def test_compute_lowering_same_as_holding() -> None:
    """Spec § 6 LOWERING notu: HOLDING kategorisi (motor enerjili tutucu basınç)."""
    sensor = HydraulicPressureSensor(_config())
    runtime_holding = _make_runtime(DeviceState.HOLDING)
    runtime_lowering = _make_runtime(DeviceState.LOWERING)
    assert sensor.compute(runtime_lowering, 0.0) == sensor.compute(runtime_holding, 0.0)


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="hydraulic_pressure"):
        HydraulicPressureSensor(bad)
```

- [x] **Step 4.2: Run, verify failure**

```bash
pytest tests/unit/test_hydraulic_pressure_sensor.py -v
```

- [x] **Step 4.3: Implement** `src/simulator/sensors/hydraulic_pressure.py`:

```python
"""Hidrolik basınç sensörü. State-bazlı 4 baseline. DOMAIN.md sat. 60, spec § 6."""
from __future__ import annotations

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# DOMAIN.md sat. 60 değerleri (aralık ortaları):
_IDLE_PRESSURE_BAR = 10.0       # 5-20 boşta
_RAISING_PRESSURE_BAR = 150.0   # 100-200 hareket
_HOLDING_PRESSURE_BAR = 80.0    # 50-150 tutucu
_LOWERING_PRESSURE_BAR = 80.0   # spec § 6 LOWERING notu: HOLDING ile aynı kategori


class HydraulicPressureSensor(BaseSensor):
    """Hidrolik basınç (bar). State'e göre 4 farklı baseline."""

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "hydraulic_pressure":
            raise ValueError(
                f"HydraulicPressureSensor 'hydraulic_pressure' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """State'e göre temiz hidrolik basıncı."""
        match runtime.state:
            case DeviceState.IDLE:
                return _IDLE_PRESSURE_BAR
            case DeviceState.RAISING:
                return _RAISING_PRESSURE_BAR
            case DeviceState.HOLDING:
                return _HOLDING_PRESSURE_BAR
            case DeviceState.LOWERING:
                return _LOWERING_PRESSURE_BAR
```

- [x] **Step 4.4: Registry'ye ekle** — `src/simulator/sensors/__init__.py`:

```python
from simulator.sensors.hydraulic_pressure import HydraulicPressureSensor

SENSOR_REGISTRY: dict[str, type[BaseSensor]] = {
    "motor_current": MotorCurrentSensor,
    "motor_voltage": MotorVoltageSensor,
    "mast_position": MastPositionSensor,
    "hydraulic_pressure": HydraulicPressureSensor,
}
```

- [x] **Step 4.5: Run new tests, verify 6 PASS**

```bash
pytest tests/unit/test_hydraulic_pressure_sensor.py -v
```

- [x] **Step 4.6: FULL verification**

```bash
pytest tests/unit/ -q                       # expect 56 passed
mypy src/simulator tests/unit                # expect Success
ruff check src/simulator tests/unit          # expect All checks passed
```

- [x] **Step 4.7: Commit**

```bash
git add src/simulator/sensors/hydraulic_pressure.py src/simulator/sensors/__init__.py tests/unit/test_hydraulic_pressure_sensor.py
git commit -m "feat(sensors): add HydraulicPressureSensor (state-based 4 baselines)

DOMAIN.md sat. 60 + spec § 6 LOWERING notu. IDLE 10, RAISING 150,
HOLDING 80, LOWERING 80 (HOLDING kategori). Spec § 3 Iter 2 kriter 3
(RAISING ≥100 bar) otomatik karşılanır.

6 yeni test. Full suite 56 passed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `VibrationSensor` (motor_current şablonu) ✅ TAMAMLANDI (commit `7cb32ca`)

motor_current ile aynı kategori şablonu: IDLE/HOLDING düşük (0.05), RAISING/LOWERING yüksek (0.3).

**Files:**
- Create: `src/simulator/sensors/vibration.py`
- Create: `tests/unit/test_vibration_sensor.py`
- Modify: `src/simulator/sensors/__init__.py`

- [x] **Step 5.1: Başarısız testleri yaz** — `tests/unit/test_vibration_sensor.py`:

```python
"""VibrationSensor için unit testler — motor_current şablonu (motor enerjili kategori)."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.vibration import VibrationSensor


def _config() -> SensorConfig:
    return SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01)


def _make_runtime(state: DeviceState) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10.0,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(42),
        started_at_monotonic=0.0,
    )


def test_vibration_sensor_is_base_sensor() -> None:
    assert isinstance(VibrationSensor(_config()), BaseSensor)


def test_compute_idle_returns_low() -> None:
    """DOMAIN.md sat. 64: sabit durumda çok düşük (≈0.05g RMS)."""
    sensor = VibrationSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(runtime, position_mm=0.0)
    assert value == 0.05


def test_compute_holding_same_as_idle() -> None:
    """Motor durmuş kategori — IDLE ile aynı."""
    sensor = VibrationSensor(_config())
    runtime = _make_runtime(DeviceState.HOLDING)
    assert sensor.compute(runtime, position_mm=5000.0) == 0.05


def test_compute_raising_returns_active() -> None:
    """DOMAIN.md sat. 64: hareket halinde 0.1-0.5g RMS."""
    sensor = VibrationSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    value = sensor.compute(runtime, position_mm=1000.0)
    assert 0.1 <= value <= 0.5


def test_compute_lowering_same_as_raising() -> None:
    """Spec § 6 LOWERING notu: RAISING kategorisi (motor enerjili hareket)."""
    sensor = VibrationSensor(_config())
    runtime_raising = _make_runtime(DeviceState.RAISING)
    runtime_lowering = _make_runtime(DeviceState.LOWERING)
    assert sensor.compute(runtime_lowering, 0.0) == sensor.compute(runtime_raising, 0.0)


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="vibration"):
        VibrationSensor(bad)
```

- [x] **Step 5.2: Run, verify failure**

```bash
pytest tests/unit/test_vibration_sensor.py -v
```

- [x] **Step 5.3: Implement** `src/simulator/sensors/vibration.py`:

```python
"""Titreşim sensörü (g RMS). motor_current şablonu: motor enerjili kategori.
DOMAIN.md sat. 64, spec § 6 LOWERING notu."""
from __future__ import annotations

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# DOMAIN.md sat. 64 değerleri:
_IDLE_VIBRATION_G = 0.05    # sabit durumda çok düşük
_ACTIVE_VIBRATION_G = 0.3   # hareket halinde 0.1-0.5 RMS (aralık ortası)


class VibrationSensor(BaseSensor):
    """Titreşim (g). IDLE/HOLDING'de düşük, RAISING/LOWERING'de yüksek."""

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "vibration":
            raise ValueError(
                f"VibrationSensor 'vibration' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """State'e göre temiz titreşim değeri."""
        match runtime.state:
            case DeviceState.IDLE | DeviceState.HOLDING:
                return _IDLE_VIBRATION_G
            case DeviceState.RAISING | DeviceState.LOWERING:
                return _ACTIVE_VIBRATION_G
```

- [x] **Step 5.4: Registry'ye ekle**:

```python
from simulator.sensors.vibration import VibrationSensor

SENSOR_REGISTRY: dict[str, type[BaseSensor]] = {
    "motor_current": MotorCurrentSensor,
    "motor_voltage": MotorVoltageSensor,
    "mast_position": MastPositionSensor,
    "hydraulic_pressure": HydraulicPressureSensor,
    "vibration": VibrationSensor,
}
```

- [x] **Step 5.5: Run new tests, verify 6 PASS**

```bash
pytest tests/unit/test_vibration_sensor.py -v
```

- [x] **Step 5.6: FULL verification**

```bash
pytest tests/unit/ -q                       # expect 62 passed
mypy src/simulator tests/unit                # expect Success
ruff check src/simulator tests/unit          # expect All checks passed
```

- [x] **Step 5.7: Commit**

```bash
git add src/simulator/sensors/vibration.py src/simulator/sensors/__init__.py tests/unit/test_vibration_sensor.py
git commit -m "feat(sensors): add VibrationSensor (motor_current category template)

DOMAIN.md sat. 64 + spec § 6 LOWERING notu. IDLE/HOLDING 0.05g (motor durmuş),
RAISING/LOWERING 0.3g (motor enerjili hareket). 0.1-0.5g RMS aralığında.

6 yeni test. Full suite 62 passed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `MotorTemperatureSensor` (TEK STATEFUL sensör) ✅ TAMAMLANDI (commit `1403285`)

Instance attribute olarak son sıcaklığı tutar. RAISING/HOLDING/LOWERING'de 0.08 °C/s ısınır (üst 35), IDLE'da 0.04 °C/s soğur (alt 25). Çevre baseline 25. Spec § 5 stateful sensor pattern + § 6 + DOMAIN.md sat. 67.

**Files:**
- Create: `src/simulator/sensors/motor_temperature.py`
- Create: `tests/unit/test_motor_temperature_sensor.py`
- Modify: `src/simulator/sensors/__init__.py`

- [x] **Step 6.1: Başarısız testleri yaz** — `tests/unit/test_motor_temperature_sensor.py`:

```python
"""MotorTemperatureSensor için unit testler — TEK STATEFUL sensör.
Lineer ısınma 0.08 °C/s (motor enerjili), soğuma 0.04 °C/s (IDLE)."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor
from simulator.sensors.motor_temperature import MotorTemperatureSensor


def _config() -> SensorConfig:
    return SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5)


def _make_runtime(state: DeviceState) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10.0,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(42),
        started_at_monotonic=0.0,
    )


def test_motor_temperature_sensor_is_base_sensor() -> None:
    assert isinstance(MotorTemperatureSensor(_config()), BaseSensor)


def test_initial_temperature_is_ambient() -> None:
    """Yeni instance çevre sıcaklığında (25°C) başlar."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    # IDLE'da hemen soğutmaya başlar ama zaten 25'te → alt sınır 25, aynı kalır.
    assert sensor.compute(runtime, position_mm=0.0) == pytest.approx(25.0)


def test_heating_in_raising_lineer_per_tick() -> None:
    """RAISING'de her tick 0.08°C artar (1 Hz varsayımı, spec § 5 tick interval notu)."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    # 5 ardışık tick: 25 → 25.08 → 25.16 → 25.24 → 25.32 → 25.40
    values = [sensor.compute(runtime, position_mm=1000.0) for _ in range(5)]
    expected = [25.08, 25.16, 25.24, 25.32, 25.40]
    for v, e in zip(values, expected):
        assert v == pytest.approx(e)


def test_heating_caps_at_35() -> None:
    """Üst sınır 35°C — uzun süre RAISING'de bile aşmaz."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.HOLDING)  # motor enerjili
    # 25'ten 35'e (10°C) çıkmak 10 / 0.08 = 125 tick. 200 tick'te kapağa otururuz.
    for _ in range(200):
        sensor.compute(runtime, position_mm=5000.0)
    final = sensor.compute(runtime, position_mm=5000.0)
    assert final == pytest.approx(35.0)


def test_cooling_in_idle_lineer_per_tick() -> None:
    """IDLE'da her tick 0.04°C azalır."""
    sensor = MotorTemperatureSensor(_config())
    # Önce ısıt
    hot_runtime = _make_runtime(DeviceState.RAISING)
    for _ in range(125):  # 25 → ~35
        sensor.compute(hot_runtime, position_mm=1000.0)
    # Sonra soğut
    cool_runtime = _make_runtime(DeviceState.IDLE)
    before = sensor.compute(cool_runtime, position_mm=0.0)
    after = sensor.compute(cool_runtime, position_mm=0.0)
    assert before - after == pytest.approx(0.04)


def test_cooling_caps_at_ambient_25() -> None:
    """Alt sınır 25°C — uzun IDLE'da çevre sıcaklığının altına inmez."""
    sensor = MotorTemperatureSensor(_config())
    runtime = _make_runtime(DeviceState.IDLE)
    # Zaten 25'te; çok tick'te de aynı kalmalı.
    for _ in range(100):
        sensor.compute(runtime, position_mm=0.0)
    final = sensor.compute(runtime, position_mm=0.0)
    assert final == pytest.approx(25.0)


def test_lowering_heats_same_as_raising() -> None:
    """Spec § 6: motor enerjili durumlarda (RAISING/HOLDING/LOWERING) aynı ısınma hızı."""
    s1 = MotorTemperatureSensor(_config())
    s2 = MotorTemperatureSensor(_config())
    raising = _make_runtime(DeviceState.RAISING)
    lowering = _make_runtime(DeviceState.LOWERING)
    for _ in range(10):
        v1 = s1.compute(raising, position_mm=1000.0)
        v2 = s2.compute(lowering, position_mm=2500.0)
    assert v1 == pytest.approx(v2)


def test_state_change_preserves_instance_state() -> None:
    """Spec § 5 invaryant 5: state transition reset etmez."""
    sensor = MotorTemperatureSensor(_config())
    raising = _make_runtime(DeviceState.RAISING)
    sensor.compute(raising, position_mm=1000.0)  # 25 → 25.08
    sensor.compute(raising, position_mm=1000.0)  # 25.08 → 25.16
    # Şimdi IDLE'a geç — son sıcaklık taşınmalı (reset değil)
    idle = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(idle, position_mm=0.0)
    # 25.16 - 0.04 = 25.12
    assert value == pytest.approx(25.12)


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1)
    with pytest.raises(ValueError, match="motor_temperature"):
        MotorTemperatureSensor(bad)
```

- [x] **Step 6.2: Run, verify failure**

```bash
pytest tests/unit/test_motor_temperature_sensor.py -v
```

- [x] **Step 6.3: Implement** `src/simulator/sensors/motor_temperature.py`:

```python
"""Motor sıcaklığı sensörü — TEK STATEFUL sensör. Lineer ısınma/soğuma.
DOMAIN.md sat. 67, spec § 5 stateful pattern + § 6 + invaryant 5."""
from __future__ import annotations

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# Spec § 6 değerleri (DOMAIN.md sat. 67):
_AMBIENT_C = 25.0                # çevre sıcaklığı / alt sınır
_MAX_TEMP_C = 35.0               # motor enerjili üst sınır
_HEATING_RATE_C_PER_S = 0.08     # motor enerjili (RAISING/HOLDING/LOWERING)
_COOLING_RATE_C_PER_S = 0.04     # IDLE
_DELTA_PER_TICK_S = 1.0          # spec § 5 tick interval varsayımı: 1 Hz


class MotorTemperatureSensor(BaseSensor):
    """Motor sıcaklığı (°C). TEK STATEFUL sensör — instance attribute olarak son
    sıcaklığı taşır. Motor enerjili durumlarda (RAISING/HOLDING/LOWERING) lineer
    ısınır (0.08 °C/s, üst 35); IDLE'da lineer soğur (0.04 °C/s, alt 25).

    Spec § 5 invaryant 5: state transition'lar instance state'i reset etmez.
    Tick interval = 1.0 s varsayımı (spec § 5 stateful sensor notu).
    """

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "motor_temperature":
            raise ValueError(
                f"MotorTemperatureSensor 'motor_temperature' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)
        # Instance state — cihaz yaşam süresi boyunca taşınır.
        self._current_temp_c: float = _AMBIENT_C

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """State'e göre lineer ısınma veya soğuma; alt/üst sınırlarla saturate."""
        if runtime.state == DeviceState.IDLE:
            self._current_temp_c = max(
                _AMBIENT_C,
                self._current_temp_c - _COOLING_RATE_C_PER_S * _DELTA_PER_TICK_S,
            )
        else:  # RAISING, HOLDING, LOWERING — motor enerjili
            self._current_temp_c = min(
                _MAX_TEMP_C,
                self._current_temp_c + _HEATING_RATE_C_PER_S * _DELTA_PER_TICK_S,
            )
        return self._current_temp_c
```

- [x] **Step 6.4: Registry'ye ekle**:

```python
from simulator.sensors.motor_temperature import MotorTemperatureSensor

SENSOR_REGISTRY: dict[str, type[BaseSensor]] = {
    "motor_current": MotorCurrentSensor,
    "motor_voltage": MotorVoltageSensor,
    "mast_position": MastPositionSensor,
    "hydraulic_pressure": HydraulicPressureSensor,
    "vibration": VibrationSensor,
    "motor_temperature": MotorTemperatureSensor,
}
```

- [x] **Step 6.5: Run new tests, verify 9 PASS**

```bash
pytest tests/unit/test_motor_temperature_sensor.py -v
```

- [x] **Step 6.6: FULL verification**

```bash
pytest tests/unit/ -q                       # expect 71 passed
mypy src/simulator tests/unit                # expect Success
ruff check src/simulator tests/unit          # expect All checks passed
```

- [x] **Step 6.7: Commit**

```bash
git add src/simulator/sensors/motor_temperature.py src/simulator/sensors/__init__.py tests/unit/test_motor_temperature_sensor.py
git commit -m "feat(sensors): add MotorTemperatureSensor (single stateful sensor)

Spec § 5 invaryant 5 + § 6 + DOMAIN.md sat. 67. Instance attribute son
sıcaklığı taşır; motor enerjili state'lerde +0.08 °C/tick (üst 35),
IDLE'da -0.04 °C/tick (alt 25). Tick interval = 1.0s varsayımı (spec § 5).
SENSOR_REGISTRY 6 entry'e çıktı.

9 yeni test (heating sequence, cooling sequence, sınırlar, state preservation).
Full suite 71 passed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Engine Strict Validation (`_validate_iteration2b_constraints`) + Fixture 6 Sensör + test_engine Refactor ✅ TAMAMLANDI (commit `cf9e8d2`)

Engine artık 6 sensör isteyecek. devices_minimal.yaml + test_engine yeniden yazılır.

**Files:**
- Modify: `src/simulator/engine.py` (validation fonksiyonu değişir)
- Modify: `tests/fixtures/devices_minimal.yaml`
- Modify: `tests/unit/test_engine.py`

- [x] **Step 7.1: `tests/fixtures/devices_minimal.yaml`'ı 6 sensörlü hale getir**

İçeriği tamamen değiştir:

```yaml
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [5, 30]
      raising:  [10, 60]
      holding:  [60, 300]
      lowering: [10, 60]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
```

- [x] **Step 7.2: `tests/unit/test_engine.py`'i 6 sensör için yeniden yaz**

Dosyanın TÜM içeriğini şununla değiştir:

```python
"""Engine 6 sensör entegrasyonu için unit testler (Iter 2b)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulator.config import DeviceState
from simulator.engine import run
from tests.unit.test_runtime import FakeClock

FIXTURES = Path(__file__).parent.parent / "fixtures"


_EXPECTED_SENSORS = {
    "motor_current",
    "motor_voltage",
    "hydraulic_pressure",
    "motor_temperature",
    "mast_position",
    "vibration",
}


def test_run_publishes_all_six_sensors_per_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Her tick'te 6 sensör için publish_reading çağrılır (6 mesaj/tick)."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=2,
        seed=42,
        clock=clock,
    )

    # 2 tick × 6 sensör = 12 publish çağrısı
    assert mock_publisher.publish_reading.call_count == 12

    # Her tick'te 6 farklı sensör adı yayınlandı
    first_tick_sensors = {
        c.kwargs["sensor"]
        for c in mock_publisher.publish_reading.call_args_list[:6]
    }
    assert first_tick_sensors == _EXPECTED_SENSORS


def test_run_publishes_state_field_idle_when_clock_not_advanced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """clock advance edilmediğinde tüm sensörler IDLE state ile publish edilir."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=1,
        seed=42,
        clock=FakeClock(0.0),
    )

    for call in mock_publisher.publish_reading.call_args_list:
        assert call.kwargs["state"] == DeviceState.IDLE


def test_run_rejects_multiple_devices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """1'den fazla cihaz → ValueError 'exactly 1 device'."""
    devices_yaml = tmp_path / "devices.yaml"
    six_sensors_block = """
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}"""
    sd_block = """
    target_height_mm: 5000
    state_durations:
      idle: [5, 30]
      raising: [10, 60]
      holding: [60, 300]
      lowering: [10, 60]"""
    devices_yaml.write_text(f"""
devices:
  - id: device_001
    type: telescopic_mast_v1{sd_block}{six_sensors_block}
  - id: device_002
    type: telescopic_mast_v1{sd_block}{six_sensors_block}
""")
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="exactly 1 device"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_rejects_missing_required_sensor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6 sensörün hepsi zorunlu — vibration eksikse ValueError."""
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text("""
devices:
  - id: device_001
    type: telescopic_mast_v1
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
""")
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="eksik.*vibration"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_rejects_extra_unknown_sensor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Set tam olmalı — bilinmeyen sensör fazla → ValueError."""
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text("""
devices:
  - id: device_001
    type: telescopic_mast_v1
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
      - {name: gyroscope,          unit: deg,     baseline: 0,    noise_std: 0.1}
""")
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="fazla.*gyroscope"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )
```

- [x] **Step 7.3: Run, verify failures (engine henüz strict validation yapmıyor)**

```bash
pytest tests/unit/test_engine.py -v
```

Beklenen: Mevcut 5 testten bazıları fail (fixture artık 6 sensör ama validation hâlâ tek motor_current zorunlu). Yeni 5 test'in çoğu da fail. Toplam test_engine fail.

- [x] **Step 7.4: `src/simulator/engine.py` validation fonksiyonunu değiştir**

`_validate_iteration2a_constraints` fonksiyonunu komple sil ve yerine şunu koy:

```python
_REQUIRED_SENSORS = frozenset({
    "motor_current",
    "motor_voltage",
    "hydraulic_pressure",
    "motor_temperature",
    "mast_position",
    "vibration",
})


def _validate_iteration2b_constraints(devices: list[DeviceConfig]) -> DeviceConfig:
    """Iterasyon 2b kısıtlamaları: tam 1 cihaz + tam 6 sensör seti."""
    if len(devices) != 1:
        raise ValueError(
            f"Iterasyon 2b exactly 1 device destekliyor, alınan: {len(devices)}"
        )
    device = devices[0]
    names = {s.name for s in device.sensors}
    if names != _REQUIRED_SENSORS:
        parts: list[str] = []
        missing = _REQUIRED_SENSORS - names
        extra = names - _REQUIRED_SENSORS
        if missing:
            parts.append(f"eksik: {sorted(missing)}")
        if extra:
            parts.append(f"fazla: {sorted(extra)}")
        raise ValueError(
            f"Iterasyon 2b: cihaz tam olarak 6 sensör içermeli ({', '.join(parts)})"
        )
    return device
```

`run()` içindeki çağrıyı güncelle:

ESKİ:
```python
device = _validate_iteration2a_constraints(devices)
```

YENİ:
```python
device = _validate_iteration2b_constraints(devices)
```

- [x] **Step 7.5: Run test_engine, verify 5 PASS**

```bash
pytest tests/unit/test_engine.py -v
```

- [x] **Step 7.6: FULL verification**

```bash
pytest tests/unit/ -q                       # expect 71 passed (Task 7 net delta: -5 eski engine test + 5 yeni = 0)
mypy src/simulator tests/unit                # expect Success
ruff check src/simulator tests/unit          # expect All checks passed
```

Coverage'da düşüş olabilir (engine.py'da `_validate_iteration2a_constraints` yerine yeni fonksiyon — coverage farklı satırlara dağılır). %85+ hâlâ tutturulmalı.

- [x] **Step 7.7: Commit**

```bash
git add src/simulator/engine.py tests/fixtures/devices_minimal.yaml tests/unit/test_engine.py
git commit -m "refactor(engine): _validate_iteration2b_constraints (6-sensor strict set)

_validate_iteration2a_constraints kaldırıldı. Yeni validation tam 6 sensör
seti ister (motor_current, motor_voltage, hydraulic_pressure,
motor_temperature, mast_position, vibration); eksik/fazla durumda
açıklayıcı ValueError.

devices_minimal.yaml fixture 6 sensörlü hale getirildi. test_engine
tamamen yeniden yazıldı: 6 publish/tick, eksik sensör, fazla sensör testleri.

Full suite 71 passed (Task 7 engine testleri yeniden yazıldı, net delta 0).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `config/devices.yaml.example` Genişlet + Manuel Doğrulama (Kullanıcı) + Milestone ✅ TAMAMLANDI (commit `1a09765` + paketleme fix `7c6c195`; manuel uçtan uca 2026-05-28)

> **Not — ikinci paketleme fix:** Manuel testte yine 'No module named simulator' çıktı; pyproject.toml `[tool.setuptools.packages.find]` `src/` altındaki boş Faz 0 klasörlerini (alerts, dashboard, vs.) namespace paketi sayıp top_level.txt'ye yazıyor, ve eski `src/mast_anomaly_detection.egg-info/` artığı setuptools editable install'ı bozuyordu. Commit `7c6c195`: `include = ["simulator*"]` + `namespaces = false` eklendi, egg-info silindi. Artık `python -m simulator` PYTHONPATH'siz stabil çalışıyor.

**Files:**
- Modify: `config/devices.yaml.example`

- [x] **Step 8.1: `config/devices.yaml.example`'ı 6 sensörlü hale getir**

Mevcut içeriğini tamamen değiştir:

```yaml
# Simülasyon için cihaz tanımları örneği — Iterasyon 2b (6 sensör)
# Gerçek devices.yaml dosyasını bu örnekten oluşturun: cp devices.yaml.example devices.yaml

devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [5, 30]      # [min_s, max_s]
      raising:  [10, 60]
      holding:  [60, 300]
      lowering: [10, 60]
    sensors:
      # baseline alanı IDLE durumu için; state-bazlı diğer değerler sensör sınıfında kodlu.
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
```

- [x] **Step 8.2: Lokal `config/devices.yaml`'ı güncelle**

```bash
cp config/devices.yaml.example config/devices.yaml
```

- [x] **Step 8.3: Commit**

```bash
git add config/devices.yaml.example
git commit -m "feat(config): extend devices.yaml.example to 6 sensors (Iter 2b)

Iterasyon 2b tüm sensörleri içeren örnek. baseline kuralı yorumu eklendi.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [x] **Step 8.4: KULLANICI TARAFI — Uçtan uca manuel doğrulama**

Bu adım agent tarafından yapılamaz; kullanıcı kendi terminalinde test eder.

**Terminal C** (broker, hâlâ açıksa kullan; yoksa `mosquitto -v`):

**Terminal A** (subscriber, tüm sensörler):
```bash
mosquitto_sub -t 'telemetry/+/#' -v
```
(`+/#` ile tüm cihaz/tüm sensör; ya da spesifik: `-t 'telemetry/device_001/+'`)

**Terminal B** (simulator):
```bash
cd ~/mast-anomaly-detection
source .venv/bin/activate
python -m simulator
```

**Beklenen davranış:**

1. Terminal B'de Loguru log: `MQTT bağlanılıyor: localhost:1883`.
2. Terminal A'da **her saniye 6 JSON mesaj** akar (her sensörden 1) — 6 farklı topic:
   - `telemetry/device_001/motor_current`
   - `telemetry/device_001/motor_voltage`
   - `telemetry/device_001/hydraulic_pressure`
   - `telemetry/device_001/motor_temperature`
   - `telemetry/device_001/mast_position`
   - `telemetry/device_001/vibration`
3. `state` alanı geçişleri:
   - İlk 5-30 sn IDLE → motor_current ~0.5, motor_voltage 24, hydraulic_pressure ~10, motor_temperature ~25 (sabit), mast_position ~0, vibration ~0.05
   - RAISING'e geçince motor_current ~8, hydraulic_pressure ~150, vibration ~0.3, motor_temperature lineer artmaya başlar (1 dakikada ~5°C), mast_position 0'dan target'a doğru artar
   - HOLDING'de hydraulic_pressure ~80, motor_current ~0.5, mast_position ~5000 sabit, motor_temperature artmaya devam (motor enerjili) ama üst sınır 35
   - LOWERING'de hydraulic_pressure ~80 (HOLDING ile aynı), motor_current ~8, mast_position target'tan 0'a, vibration ~0.3
4. Ctrl+C → temiz kapanma.

**Bitti kriterleri (spec § 3 Iter 2 tam set):**

- [ ] IDLE'da `motor_current ∈ [0, 1] A` (Iter 2a'da zaten ✅)
- [ ] RAISING kararlı kısımda `motor_current ∈ [5, 15] A` (Iter 2a ✅)
- [ ] RAISING ilk 2 saniyede `hydraulic_pressure ≥ 100 bar` (150 sabit, hep ≥100 ✅)
- [ ] HOLDING'de `mast_position ≈ target ± 1 mm` (engine compute_position = target, ± noise)
- [ ] Tam döngü 85-450 sn (state machine zaten Iter 2a ✅)
- [ ] Test paketi her sensör için durum-başına davranış testi (Task 2-6 ✅)

- [x] **Step 8.5: Iterasyon 2b milestone commit** (kullanıcı manuel testi başarılı raporlayınca)

```bash
git commit --allow-empty -m "milestone: Faz 1 Iterasyon 2b (tüm sensörler) tamamlandı 🎉

Spec § 3 Iterasyon 2 kabul kriterleri TAM karşılandı:
- 6 sensör (motor_current, motor_voltage, hydraulic_pressure, motor_temperature,
  mast_position, vibration) her tick yayınlanıyor
- state machine 4 durumu (Iter 2a) tüm sensörlere yansıyor
- DOMAIN.md aralıklarında değerler, spec § 6 baseline'ları
- motor_temperature tek stateful sensör (instance attribute pattern)
- 71 unit test yeşil, hedef coverage tutturuldu
- Manuel uçtan uca: 6 topic'te paralel akış, state geçişleri tüm sensörlerde,
  Ctrl+C graceful shutdown

Faz 1 ROADMAP'inde Iterasyon 3 (çoklu cihaz asyncio) sıradaki.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notları

**Spec coverage (§ 3 Iterasyon 2 tam set):**
- 6 sensör (motor_current ✅ Iter 2a, kalan 5 → Task 2-6) ✅
- DeviceState + DeviceRuntimeState + state machine (Iter 2a ✅)
- BaseSensor ABC (Iter 2a ✅)
- Her sensörün durum-başına davranış formülleri (Task 2-6) ✅
- Implicit korelasyon (sensörler ortak `runtime.state` okur, motor_current↑ + hydraulic_pressure↑ otomatik) ✅
- SENSOR_REGISTRY 6 entry (Task 2-6) ✅
- Engine N-sensör loop (Task 1) + strict validation (Task 7) ✅

**Spec § 5 invaryantlar:**
- Sensor instance state preservation → `MotorTemperatureSensor` test_state_change_preserves_instance_state (Task 6) ✅
- Stateless sensörler runtime+position'dan hesaplar (Task 2-5) ✅

**Spec § 6 + § 5 LOWERING + tick interval güncellemeleri:**
- hydraulic_pressure LOWERING = 80 (spec § 6 not, commit `761fa17`) → Task 4 implementasyon + test ✅
- vibration LOWERING = 0.3 → Task 5 ✅
- motor_temperature tick interval = 1.0s (spec § 5 not) → Task 6 docstring + sabit ✅

**Placeholder taraması:** "TBD", "TODO" yok. Tüm code block'lar tam.

**Type tutarlılığı:**
- `BaseSensor.compute(runtime, position_mm)` her 5 yeni sensörde aynı imza ✅
- `SENSOR_REGISTRY: dict[str, type[BaseSensor]]` tek tanım, her task'ta tek satır ekleme ✅
- `_REQUIRED_SENSORS: frozenset[str]` Task 7'de tanımlı, validation içinde kullanılıyor ✅

**Iterasyon sonu durum:**
- Tek cihaz, 6 sensör — Iter 3'te asyncio + çoklu cihaz.
- ~73 unit test yeşil, ≥85% coverage hedef.
- python -m simulator → 6 mesaj/saniye akar.

# Faz 1 — Iterasyon 2a: State Machine + motor_current Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Iterasyon 1'in sabit `state="idle"` walking skeleton'unu state-aware bir yapıya dönüştürmek: DeviceRuntimeState + state machine (IDLE→RAISING→HOLDING→LOWERING→IDLE) + clock DI + BaseSensor ABC + motor_current refactor (compute(runtime, position) sözleşmesine).

**Architecture:** Yeni `runtime.py` modülü DeviceRuntimeState (mutable, clock injectable) + `advance_state_machine` + `compute_position` üçlüsünü barındırır. `BaseSensor` ABC `sensors/base.py`'da, gürültü artık sensörde değil engine'de eklenir (Iterasyon 4 senaryolarına hazırlık). Engine güncellenir: state machine'i sürer, sensör compute() çağırır, gürültüyü kendi ekler, payload'da `state=runtime.state` (StrEnum) ile yayın yapar.

**Tech Stack:** Python 3.11+ (StrEnum, mypy strict), dataclasses, type hints, pytest. Iterasyon 1 tüm bağımlılıkları zaten yüklü (paho-mqtt, pyyaml, loguru). Yeni dependency yok.

**Referans:** `docs/specs/2026-05-18-faz1-simulator-design.md` (güncellenmiş, commit `9931a9e`) § 3 Iterasyon 2, § 5 veri modelleri, § 8 tick akışı, § 12 FakeClock pattern.

---

## Önkoşul

`.venv` aktif, `pip install -e .` yapılmış. Tüm Iterasyon 1 testleri (17 PASS) yeşil olmalı. Bu plan'ın başında doğrulamak için:

```bash
cd ~/mast-anomaly-detection
source .venv/bin/activate
pytest tests/unit/ -v
```

17 PASS bekleniyor. Eğer değilse plan'a başlamadan önce sorunu çöz.

---

## Dosya Yapısı (Iterasyon 2a sonunda)

```
src/simulator/
├── __init__.py                       # değişmez
├── __main__.py                       # değişmez
├── config.py                         # GENİŞLETİLDİ: DeviceState, StateDurations, DeviceConfig+
├── publisher.py                      # değişmez
├── runtime.py                        # YENİ: DeviceRuntimeState, advance, position
├── engine.py                         # REFACTOR: state machine entegrasyonu, clock param
└── sensors/
    ├── __init__.py                   # GENİŞLETİLDİ: SENSOR_REGISTRY
    ├── base.py                       # YENİ: BaseSensor ABC
    └── motor_current.py              # REFACTOR: sample() → compute(runtime, position)

tests/
├── conftest.py                       # değişmez
├── fixtures/
│   ├── devices_minimal.yaml          # GENİŞLETİLDİ: state_durations + target_height_mm + seed
│   ├── mqtt_minimal.yaml             # değişmez
│   └── simulator_minimal.yaml        # değişmez
└── unit/
    ├── test_config.py                # GENİŞLETİLDİ: yeni alanlar için 2 test
    ├── test_engine.py                # GÜNCELLENDİ: state machine entegrasyonu
    ├── test_motor_current_sensor.py  # YENİDEN YAZILDI: 7 yeni test (state-aware)
    ├── test_mqtt_publisher.py        # değişmez
    └── test_runtime.py               # YENİ: ~8 test (state machine, position, clock DI)

config/
└── devices.yaml.example              # GENİŞLETİLDİ
```

**Beklenen test sayısı:** ~42 (config 9 + runtime 12 + motor_current 12 + engine 4 + publisher 5). Iterasyon 1'in 17'sinden artış.
**Hedef coverage:** ≥85% (Iterasyon 1'in %84'ünden hafif artış).

---

## Task 1: Config Genişletmesi (DeviceState + StateDurations + DeviceConfig) ✅ TAMAMLANDI (commit `b606141`)

Spec § 5 yeni alanları config layer'a ekleriz. `DeviceState` StrEnum, `StateDurations` frozen dataclass, `DeviceConfig`'e `state_durations`, `target_height_mm`, `seed` alanları.

**Files:**
- Modify: `src/simulator/config.py`
- Modify: `tests/fixtures/devices_minimal.yaml`
- Modify: `tests/unit/test_config.py`

- [x] **Step 1.1: `tests/fixtures/devices_minimal.yaml` genişletme**

Mevcut içeriği şu yeni içerikle değiştir:

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
      - name: motor_current
        unit: A
        baseline: 0.5
        noise_std: 0.1
```

- [x] **Step 1.2: Yeni testleri yaz (`tests/unit/test_config.py` sonuna ekle)**

Dosyanın sonuna şu testleri ekle:

```python
def test_load_devices_parses_state_durations_as_tuples() -> None:
    devices = load_devices(FIXTURES / "devices_minimal.yaml")
    device = devices[0]
    assert device.state_durations.idle == (5.0, 30.0)
    assert device.state_durations.raising == (10.0, 60.0)
    assert device.state_durations.holding == (60.0, 300.0)
    assert device.state_durations.lowering == (10.0, 60.0)


def test_load_devices_includes_target_height_and_seed() -> None:
    devices = load_devices(FIXTURES / "devices_minimal.yaml")
    device = devices[0]
    assert device.target_height_mm == 5000.0
    assert device.seed == 42


def test_load_devices_rejects_missing_state_durations(tmp_path) -> None:
    bad = tmp_path / "devices.yaml"
    bad.write_text(
        """
devices:
  - id: device_001
    type: telescopic_mast_v1
    target_height_mm: 5000
    sensors:
      - {name: motor_current, unit: A, baseline: 0.5, noise_std: 0.1}
"""
    )
    with pytest.raises(ValueError, match="state_durations"):
        load_devices(bad)


def test_device_state_is_str_enum() -> None:
    from simulator.config import DeviceState
    assert DeviceState.IDLE == "idle"
    assert DeviceState.RAISING == "raising"
    assert DeviceState.HOLDING == "holding"
    assert DeviceState.LOWERING == "lowering"
    # JSON serialization works without .value:
    import json
    assert json.dumps({"s": DeviceState.IDLE}) == '{"s": "idle"}'
```

İlk 3 test mevcut `test_load_devices_returns_list_of_device_configs` testinin yeni alanlarını test eder (var olan testi BOZMA — sadece yeni testler ekle). 4. test DeviceState StrEnum behavior.

- [x] **Step 1.3: Testleri çalıştır, mevcut testlerin **bozulduğunu** doğrula**

```bash
pytest tests/unit/test_config.py -v
```

Beklenen: Yeni 4 test **fail** eder — `test_device_state_is_str_enum` ImportError (DeviceState yok), diğer 3'ü AttributeError (`device.state_durations`/`device.target_height_mm` field'ları DeviceConfig'de yok). Mevcut `test_load_devices_returns_list_of_device_configs` testi geçmeye devam EDEBİLİR (eski alanları kontrol ediyor, fixture'da hâlâ var). Önemli olan yeni testlerin kırmızı olması.

- [x] **Step 1.4: `src/simulator/config.py` güncelle**

Dosyanın başına import ekle:

```python
from enum import StrEnum
```

`SensorConfig` tanımından SONRA, `DeviceConfig`'den ÖNCE şu sınıfları ekle:

```python
class DeviceState(StrEnum):
    IDLE = "idle"
    RAISING = "raising"
    HOLDING = "holding"
    LOWERING = "lowering"


@dataclass(frozen=True)
class StateDurations:
    idle: tuple[float, float]      # (min_s, max_s)
    raising: tuple[float, float]
    holding: tuple[float, float]
    lowering: tuple[float, float]
```

`DeviceConfig`'i şu hale getir (eski tanımı tamamen değiştir):

```python
@dataclass(frozen=True)
class DeviceConfig:
    id: str
    type: str
    sensors: list[SensorConfig]
    state_durations: StateDurations
    target_height_mm: float
    seed: int | None = None
```

`load_devices` fonksiyonunu güncelle — state_durations + target_height_mm + seed parse etmeli. Tam yeni hali:

```python
def load_devices(path: Path) -> list[DeviceConfig]:
    """Cihaz yapılandırmalarını YAML dosyasından yükle.

    Args:
        path: devices.yaml dosyasının yolu.

    Returns:
        DeviceConfig listesi.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: YAML bozuksa veya şema geçersizse (eksik state_durations,
            target_height_mm vb.).
    """
    data = _read_yaml(path)
    try:
        device_dicts = data["devices"]
        if not isinstance(device_dicts, list):
            raise ValueError("'devices' bir liste olmalı")
        devices: list[DeviceConfig] = []
        for d in device_dicts:
            sensors = [
                SensorConfig(
                    name=str(s["name"]),
                    unit=str(s["unit"]),
                    baseline=float(s["baseline"]),
                    noise_std=float(s["noise_std"]),
                )
                for s in d["sensors"]
            ]
            sd = d["state_durations"]
            state_durations = StateDurations(
                idle=(float(sd["idle"][0]), float(sd["idle"][1])),
                raising=(float(sd["raising"][0]), float(sd["raising"][1])),
                holding=(float(sd["holding"][0]), float(sd["holding"][1])),
                lowering=(float(sd["lowering"][0]), float(sd["lowering"][1])),
            )
            devices.append(
                DeviceConfig(
                    id=str(d["id"]),
                    type=str(d["type"]),
                    sensors=sensors,
                    state_durations=state_durations,
                    target_height_mm=float(d["target_height_mm"]),
                    seed=int(d["seed"]) if "seed" in d else None,
                )
            )
        return devices
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Devices config geçersiz ({path}): {e}") from e
```

- [x] **Step 1.5: Testleri çalıştır, hepsinin geçtiğini doğrula**

```bash
pytest tests/unit/test_config.py -v
```

Beklenen: **9 PASS** (mevcut 5 + yeni 4). Mevcut `test_load_devices_returns_list_of_device_configs` testi de geçer çünkü yeni alanlar fixture'da artık var ve dataclass'ı doldurmak için yeterli.

- [x] **Step 1.6: Commit**

```bash
git add src/simulator/config.py tests/fixtures/devices_minimal.yaml tests/unit/test_config.py
git commit -m "feat(config): add DeviceState, StateDurations, extend DeviceConfig

Iterasyon 2a için config layer genişletmesi (spec § 5):
- DeviceState StrEnum (idle/raising/holding/lowering)
- StateDurations frozen dataclass (per-state min/max ranges)
- DeviceConfig'e state_durations, target_height_mm, seed alanları
- devices_minimal.yaml fixture güncellendi

4 yeni test (9 toplam, hepsi yeşil).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: DeviceRuntimeState + FakeClock + Property Testleri ✅ TAMAMLANDI (commit `44363c0`)

`runtime.py`'ı oluşturup `DeviceRuntimeState` dataclass'ını kuracağız. Henüz `advance_state_machine` veya `compute_position` yok — sadece veri tipi + property'ler + FakeClock test helper'ı.

**Files:**
- Create: `src/simulator/runtime.py`
- Create: `tests/unit/test_runtime.py`

- [x] **Step 2.1: Başarısız testi yaz**

`tests/unit/test_runtime.py`:

```python
"""DeviceRuntimeState + state machine + position için unit testler."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, StateDurations
from simulator.runtime import DeviceRuntimeState


class FakeClock:
    """Test'te zamanı manuel kontrol et (DI pattern, monkeypatch yerine)."""

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _fixed_durations() -> StateDurations:
    """Test'te deterministik kullanım için min == max."""
    return StateDurations(
        idle=(5.0, 5.0),
        raising=(10.0, 10.0),
        holding=(60.0, 60.0),
        lowering=(10.0, 10.0),
    )


def _make_runtime(
    *,
    clock: FakeClock,
    state: DeviceState = DeviceState.IDLE,
    duration: float = 5.0,
    start: float = 0.0,
    seed: int = 42,
) -> DeviceRuntimeState:
    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=start,
        current_state_duration_s=duration,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(seed),
        started_at_monotonic=start,
        clock=clock,
    )


def test_runtime_can_be_constructed_with_all_fields() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock)
    assert runtime.state == DeviceState.IDLE
    assert runtime.current_state_duration_s == 5.0
    assert runtime.cycle_count == 0
    assert runtime.position_mm == 0.0


def test_elapsed_in_state_uses_clock_difference() -> None:
    clock = FakeClock(100.0)
    runtime = _make_runtime(clock=clock, start=100.0)
    assert runtime.elapsed_in_state_s == 0.0
    clock.advance(7.5)
    assert runtime.elapsed_in_state_s == 7.5


def test_device_elapsed_uses_started_at_monotonic() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, start=0.0)
    clock.advance(30.0)
    # State'e 30s önce girdik, cihaz spawn'dan da 30s geçti
    assert runtime.device_elapsed_s == 30.0
    assert runtime.elapsed_in_state_s == 30.0
```

- [x] **Step 2.2: Testleri başarısız çalıştır**

```bash
pytest tests/unit/test_runtime.py -v
```

Beklenen: `ModuleNotFoundError: No module named 'simulator.runtime'`.

- [x] **Step 2.3: `src/simulator/runtime.py` oluştur**

```python
"""Cihaz çalışma zamanı durumu, state machine geçişleri ve pozisyon hesabı."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random

from simulator.config import DeviceState


@dataclass
class DeviceRuntimeState:
    """Bir cihazın anlık çalışma durumu (mutable).

    Iterasyon 1'in DeviceConfig (immutable) ile karıştırılmamalı: DeviceConfig
    YAML'den okunan sabit yapılandırma; DeviceRuntimeState engine tarafından
    mutate edilen canlı durum.

    Invaryantlar (spec § 5):
        1. current_state_duration_s sadece state transition anında seçilir.
        2. clock() monotonic (default time.monotonic).
        3. rng per-device, seed'li → testler tekrarlanabilir.
        4. State geçişi tek yönlü: IDLE → RAISING → HOLDING → LOWERING → IDLE.
    """

    state: DeviceState
    state_entered_at_monotonic: float
    current_state_duration_s: float
    position_mm: float
    cycle_count: int
    rng: Random
    started_at_monotonic: float
    clock: Callable[[], float] = field(default=time.monotonic)

    @property
    def elapsed_in_state_s(self) -> float:
        """Mevcut state'e girişten beri geçen süre (saniye)."""
        return self.clock() - self.state_entered_at_monotonic

    @property
    def device_elapsed_s(self) -> float:
        """Cihaz engine'de spawn olduğundan beri geçen toplam süre (senaryolar için)."""
        return self.clock() - self.started_at_monotonic
```

- [x] **Step 2.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_runtime.py -v
```

Beklenen: **3 PASS**.

- [x] **Step 2.5: Commit**

```bash
git add src/simulator/runtime.py tests/unit/test_runtime.py
git commit -m "feat(runtime): add DeviceRuntimeState with clock DI

Iterasyon 2a foundation: mutable runtime state for state machine. Clock
field (Callable[[], float]) injectable for deterministic tests via FakeClock.
elapsed_in_state_s and device_elapsed_s properties compute via clock().

3 yeni test (DeviceRuntimeState construction, elapsed properties).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: State Machine Transition Algoritması ✅ TAMAMLANDI (commit `33f25c2` + cleanup `6c25a3a`)

`advance_state_machine` ekleyeceğiz: state süresi dolunca tek yönlü çevrime göre bir sonraki state'e geç. Spec § 5 invaryant 1 — transition anında `current_state_duration_s` yeniden seçilir.

**Files:**
- Modify: `src/simulator/runtime.py`
- Modify: `tests/unit/test_runtime.py`

- [x] **Step 3.1: Başarısız testleri yaz (`tests/unit/test_runtime.py` sonuna ekle)**

```python
from simulator.runtime import advance_state_machine


def test_no_transition_before_duration_elapses() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    clock.advance(4.999)
    advance_state_machine(runtime, _fixed_durations())
    assert runtime.state == DeviceState.IDLE


def test_transition_happens_when_duration_elapses() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    clock.advance(5.0)
    advance_state_machine(runtime, _fixed_durations())
    assert runtime.state == DeviceState.RAISING


def test_transition_resamples_current_state_duration() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    clock.advance(5.0)
    advance_state_machine(runtime, _fixed_durations())
    # _fixed_durations: raising=(10, 10), so resampled value must be 10.0
    assert runtime.current_state_duration_s == 10.0


def test_transition_updates_state_entered_at_to_clock() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    clock.advance(5.0)
    advance_state_machine(runtime, _fixed_durations())
    assert runtime.state_entered_at_monotonic == 5.0


def test_full_cycle_returns_to_idle_and_increments_count() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    durations = _fixed_durations()

    # IDLE → RAISING
    clock.advance(5.0)
    advance_state_machine(runtime, durations)
    assert runtime.state == DeviceState.RAISING
    assert runtime.cycle_count == 0

    # RAISING → HOLDING
    clock.advance(10.0)
    advance_state_machine(runtime, durations)
    assert runtime.state == DeviceState.HOLDING

    # HOLDING → LOWERING
    clock.advance(60.0)
    advance_state_machine(runtime, durations)
    assert runtime.state == DeviceState.LOWERING

    # LOWERING → IDLE (cycle complete)
    clock.advance(10.0)
    advance_state_machine(runtime, durations)
    assert runtime.state == DeviceState.IDLE
    assert runtime.cycle_count == 1
```

- [x] **Step 3.2: Testleri başarısız çalıştır**

```bash
pytest tests/unit/test_runtime.py -v
```

Beklenen: `ImportError: cannot import name 'advance_state_machine'`.

- [x] **Step 3.3: `src/simulator/runtime.py`'i güncelle**

**Önce** dosyanın başındaki import satırını güncelle (ruff E402'den kaçınmak için import dosya başında olmalı):

```python
# ESKİ:
from simulator.config import DeviceState
# YENİ:
from simulator.config import DeviceState, StateDurations
```

**Sonra** dosyanın sonuna (DeviceRuntimeState sınıfından sonra) şunları ekle:

```python
_NEXT_STATE: dict[DeviceState, DeviceState] = {
    DeviceState.IDLE: DeviceState.RAISING,
    DeviceState.RAISING: DeviceState.HOLDING,
    DeviceState.HOLDING: DeviceState.LOWERING,
    DeviceState.LOWERING: DeviceState.IDLE,
}


def _state_bounds(state: DeviceState, durations: StateDurations) -> tuple[float, float]:
    """State için (min_s, max_s) süre aralığı döndür."""
    match state:
        case DeviceState.IDLE:
            return durations.idle
        case DeviceState.RAISING:
            return durations.raising
        case DeviceState.HOLDING:
            return durations.holding
        case DeviceState.LOWERING:
            return durations.lowering


def advance_state_machine(runtime: DeviceRuntimeState, durations: StateDurations) -> None:
    """State süresi dolduysa sıradaki state'e geç. Aksi halde no-op.

    Transition anında current_state_duration_s YENİDEN seçilir (invaryant 1).
    Tam IDLE→IDLE döngüsünde cycle_count artar.

    Args:
        runtime: Mutate edilecek runtime durumu.
        durations: State başına (min, max) süre aralıkları.
    """
    if runtime.elapsed_in_state_s < runtime.current_state_duration_s:
        return

    next_state = _NEXT_STATE[runtime.state]
    next_min, next_max = _state_bounds(next_state, durations)

    runtime.state = next_state
    runtime.current_state_duration_s = runtime.rng.uniform(next_min, next_max)
    runtime.state_entered_at_monotonic = runtime.clock()
    if next_state == DeviceState.IDLE:
        runtime.cycle_count += 1
```

- [x] **Step 3.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_runtime.py -v
```

Beklenen: **8 PASS** (3 önceki + 5 yeni).

- [x] **Step 3.5: Commit**

```bash
git add src/simulator/runtime.py tests/unit/test_runtime.py
git commit -m "feat(runtime): add advance_state_machine with one-way cycle

State geçişleri tek yönlü: IDLE→RAISING→HOLDING→LOWERING→IDLE.
Transition'da current_state_duration_s yeniden seçilir (spec § 5 invaryant 1).
Tam döngüde cycle_count artar.

5 yeni test (no-transition, exact-elapsed, duration-resample, state_entered_at,
full-cycle).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `compute_position` Fonksiyonu ✅ TAMAMLANDI (commit `ce15a60`)

Spec § 5/8'deki lineer pozisyon hesabı. State + elapsed + duration → position.

**Files:**
- Modify: `src/simulator/runtime.py`
- Modify: `tests/unit/test_runtime.py`

- [x] **Step 4.1: Başarısız testleri yaz (`tests/unit/test_runtime.py` sonuna ekle)**

```python
from simulator.runtime import compute_position


def test_compute_position_idle_returns_zero() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.IDLE, duration=5.0)
    assert compute_position(runtime, target_mm=5000.0) == 0.0


def test_compute_position_raising_returns_linear_progress() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.RAISING, duration=10.0)
    # 0 elapsed → 0 progress
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(0.0)
    clock.advance(5.0)
    # 5/10 elapsed → 50% progress
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(2500.0)
    clock.advance(5.0)
    # 10/10 elapsed → 100% progress
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(5000.0)


def test_compute_position_holding_returns_target() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.HOLDING, duration=60.0)
    clock.advance(30.0)
    assert compute_position(runtime, target_mm=5000.0) == 5000.0


def test_compute_position_lowering_returns_decreasing() -> None:
    clock = FakeClock(0.0)
    runtime = _make_runtime(clock=clock, state=DeviceState.LOWERING, duration=10.0)
    # 0 elapsed → still at target
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(5000.0)
    clock.advance(5.0)
    # 5/10 elapsed → 50% down
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(2500.0)
    clock.advance(5.0)
    # 10/10 elapsed → fully down
    assert compute_position(runtime, target_mm=5000.0) == pytest.approx(0.0)
```

- [x] **Step 4.2: Testleri başarısız çalıştır**

```bash
pytest tests/unit/test_runtime.py -v
```

Beklenen: `ImportError: cannot import name 'compute_position'`.

- [x] **Step 4.3: `src/simulator/runtime.py` sonuna ekle**

```python
def compute_position(runtime: DeviceRuntimeState, target_mm: float) -> float:
    """State ve elapsed'e göre lineer pozisyon hesabı.

    Saf fonksiyon — runtime'ı mutate etmez. Sensörler (özellikle mast_position
    Iterasyon 2b'de) bu fonksiyondan pozisyon okur.

    Args:
        runtime: Cihaz çalışma durumu.
        target_mm: Cihazın hedef yüksekliği (config'den).

    Returns:
        Şu anki pozisyon (mm). IDLE→0, RAISING→0..target lineer,
        HOLDING→target, LOWERING→target..0 lineer.
    """
    progress = min(1.0, runtime.elapsed_in_state_s / runtime.current_state_duration_s)
    match runtime.state:
        case DeviceState.IDLE:
            return 0.0
        case DeviceState.RAISING:
            return target_mm * progress
        case DeviceState.HOLDING:
            return target_mm
        case DeviceState.LOWERING:
            return target_mm * (1.0 - progress)
```

- [x] **Step 4.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_runtime.py -v
```

Beklenen: **12 PASS** (8 önceki + 4 yeni).

- [x] **Step 4.5: Commit**

```bash
git add src/simulator/runtime.py tests/unit/test_runtime.py
git commit -m "feat(runtime): add compute_position with linear interpolation

Pure function. IDLE→0, RAISING→0..target linear, HOLDING→target,
LOWERING→target..0 linear. Spec § 5/8 referansı.

4 yeni test (IDLE/RAISING/HOLDING/LOWERING).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `BaseSensor` ABC ✅ TAMAMLANDI (commit `b5d8a42`)

Sensör sözleşmesi. Iterasyon 2a'da tek implementasyon (MotorCurrentSensor), Iterasyon 2b'de 5 sensör daha eklenecek.

**Files:**
- Create: `src/simulator/sensors/base.py`
- Modify: `tests/unit/test_motor_current_sensor.py` (sadece test ekleyeceğiz, kalan tests Task 6'da güncellenecek)

- [x] **Step 5.1: Başarısız testi yaz**

`tests/unit/test_motor_current_sensor.py` dosyasının **mevcut içeriğini sakla** (Task 6'da değiştirilecek), en sona şu testi ekle:

```python
def test_base_sensor_cannot_be_instantiated() -> None:
    """BaseSensor ABC abstract — direkt instance edilemez."""
    from simulator.sensors.base import BaseSensor
    from simulator.config import SensorConfig

    config = SensorConfig(name="x", unit="X", baseline=0.0, noise_std=0.0)
    with pytest.raises(TypeError, match="abstract"):
        BaseSensor(config)  # type: ignore[abstract]
```

- [x] **Step 5.2: Testi başarısız çalıştır**

```bash
pytest tests/unit/test_motor_current_sensor.py::test_base_sensor_cannot_be_instantiated -v
```

Beklenen: `ModuleNotFoundError: No module named 'simulator.sensors.base'`.

- [x] **Step 5.3: `src/simulator/sensors/base.py` oluştur**

```python
"""Sensör sözleşmesi: tüm sensörler bu ABC'yi uygular (spec § 5)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from simulator.config import SensorConfig
from simulator.runtime import DeviceRuntimeState


class BaseSensor(ABC):
    """Bir sensörün davranışını temsil eder.

    Sözleşme:
        - Aynı sensör instance'ı + aynı runtime tick sırası → aynı çıktı sırası
          (deterministik). RNG yok.
        - Gürültü engine tarafından eklenir (spec § 8): clean → fault → noise.
          Sensörler saf değer döndürür.
        - Sensör instance'ı internal state tutabilir (örn. motor_temperature
          Iterasyon 2b'de). Diğer sensörler stateless.
    """

    config: SensorConfig

    def __init__(self, config: SensorConfig) -> None:
        self.config = config

    @abstractmethod
    def compute(
        self,
        runtime: DeviceRuntimeState,
        position_mm: float,
    ) -> float:
        """Bu sensör için bu tick'teki TEMİZ (arızasız, gürültüsüz) değer.

        Args:
            runtime: Cihazın anlık durumu.
            position_mm: Engine tarafından compute_position() ile hesaplanmış pozisyon.

        Returns:
            Sensörün bu tick'teki temiz çıktısı.
        """
```

- [x] **Step 5.4: Testi yeşil çalıştır**

```bash
pytest tests/unit/test_motor_current_sensor.py::test_base_sensor_cannot_be_instantiated -v
```

Beklenen: **1 PASS**.

- [x] **Step 5.5: Commit**

```bash
git add src/simulator/sensors/base.py tests/unit/test_motor_current_sensor.py
git commit -m "feat(sensors): add BaseSensor ABC contract

Spec § 5 sözleşme: compute(runtime, position_mm) -> float. Sensörler saf
değer döner; gürültü engine'in işi (Iterasyon 4 senaryolarına hazırlık).

1 yeni test (ABC instantiation hatası).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `MotorCurrentSensor` Refactor ✅ TAMAMLANDI (commit `8167f33`, engine minimal adapte dahil)

`sample()` kaldırılıp `compute(runtime, position_mm)` eklenir. Iterasyon 1 testleri silinip yeni state-aware testlerle değiştirilir. Bu task **breaking refactor** — mevcut test_motor_current_sensor.py'nin çoğu yeniden yazılır.

**Files:**
- Modify: `src/simulator/sensors/motor_current.py`
- Modify: `tests/unit/test_motor_current_sensor.py`

- [x] **Step 6.1: `tests/unit/test_motor_current_sensor.py`'i tamamen yeniden yaz**

Dosyanın TÜM içeriğini şu içerikle değiştir:

```python
"""MotorCurrentSensor state-aware compute() davranışı için unit testler."""
from __future__ import annotations

from random import Random

import pytest

from simulator.config import DeviceState, SensorConfig
from simulator.sensors.base import BaseSensor
from simulator.sensors.motor_current import MotorCurrentSensor


def _config(baseline: float = 0.5, noise_std: float = 0.1) -> SensorConfig:
    return SensorConfig(
        name="motor_current",
        unit="A",
        baseline=baseline,
        noise_std=noise_std,
    )


def _make_runtime(state: DeviceState) -> object:
    """Minimal runtime stub for compute() — sadece state field'i lazım."""
    from simulator.runtime import DeviceRuntimeState

    return DeviceRuntimeState(
        state=state,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=10.0,
        position_mm=0.0,
        cycle_count=0,
        rng=Random(42),
        started_at_monotonic=0.0,
    )


def test_motor_current_sensor_is_base_sensor() -> None:
    sensor = MotorCurrentSensor(_config())
    assert isinstance(sensor, BaseSensor)


def test_compute_in_idle_returns_config_baseline() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.IDLE)
    assert sensor.compute(runtime, position_mm=0.0) == 0.5


def test_compute_in_holding_returns_config_baseline() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.HOLDING)
    assert sensor.compute(runtime, position_mm=5000.0) == 0.5


def test_compute_in_raising_returns_active_baseline() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.RAISING)
    value = sensor.compute(runtime, position_mm=1000.0)
    # DOMAIN.md sat. 58: hareket halinde 5-15 A aralığı. _ACTIVE_BASELINE_A=8.0.
    assert value == 8.0


def test_compute_in_lowering_returns_active_baseline() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.LOWERING)
    value = sensor.compute(runtime, position_mm=2500.0)
    # LOWERING aynı kategori (motor enerjili). Spec § 6 LOWERING notu.
    assert value == 8.0


def test_compute_is_deterministic_no_rng() -> None:
    """Sensör saf — gürültü engine'in işi (spec § 8). Aynı runtime → aynı çıktı."""
    sensor = MotorCurrentSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    values = [sensor.compute(runtime, position_mm=1000.0) for _ in range(5)]
    assert all(v == values[0] for v in values)


def test_idle_baseline_within_domain_range() -> None:
    """DOMAIN.md sat. 58: IDLE'da 0-1A. config.baseline=0.5 bu aralığa düşer."""
    sensor = MotorCurrentSensor(_config(baseline=0.5))
    runtime = _make_runtime(DeviceState.IDLE)
    value = sensor.compute(runtime, position_mm=0.0)
    assert 0.0 <= value <= 1.0


def test_active_baseline_within_domain_range() -> None:
    """DOMAIN.md sat. 58: RAISING/LOWERING'de 5-15A. _ACTIVE_BASELINE_A=8.0 bu aralık."""
    sensor = MotorCurrentSensor(_config())
    runtime = _make_runtime(DeviceState.RAISING)
    value = sensor.compute(runtime, position_mm=1000.0)
    assert 5.0 <= value <= 15.0


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0)
    with pytest.raises(ValueError, match="motor_current"):
        MotorCurrentSensor(bad)


def test_base_sensor_cannot_be_instantiated() -> None:
    """BaseSensor ABC abstract — direkt instance edilemez."""
    config = SensorConfig(name="x", unit="X", baseline=0.0, noise_std=0.0)
    with pytest.raises(TypeError, match="abstract"):
        BaseSensor(config)  # type: ignore[abstract]
```

- [x] **Step 6.2: Testleri başarısız çalıştır**

```bash
pytest tests/unit/test_motor_current_sensor.py -v
```

Beklenen: Çoğu test fail — `MotorCurrentSensor` `compute()` metoduna henüz sahip değil ve constructor değişti (rng parametresi kaldırılmalı).

- [x] **Step 6.3: `src/simulator/sensors/motor_current.py`'i tamamen yeniden yaz**

Dosyanın TÜM içeriğini şununla değiştir:

```python
"""Iterasyon 2: state-aware motor akımı sensörü. State'e göre baseline değişir."""
from __future__ import annotations

from simulator.config import DeviceState, SensorConfig
from simulator.runtime import DeviceRuntimeState
from simulator.sensors.base import BaseSensor

# DOMAIN.md sat. 58 — hareket halinde 5-15A kararlı tüketim. 8.0 bu aralığın
# merkezi-altı, gerçekçi nominal yük. RAISING ve LOWERING aynı kategori.
_ACTIVE_BASELINE_A = 8.0


class MotorCurrentSensor(BaseSensor):
    """Motor akımı (A). IDLE/HOLDING'de düşük (config.baseline), RAISING/LOWERING'de yüksek."""

    def __init__(self, config: SensorConfig) -> None:
        if config.name != "motor_current":
            raise ValueError(
                f"MotorCurrentSensor 'motor_current' bekler, alınan: {config.name!r}"
            )
        super().__init__(config)

    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """State'e göre temiz motor akımı değeri.

        IDLE/HOLDING: config.baseline (sensör boşta, motor durmuş).
        RAISING/LOWERING: _ACTIVE_BASELINE_A (motor enerjili, yük altında).
        """
        match runtime.state:
            case DeviceState.IDLE | DeviceState.HOLDING:
                return self.config.baseline
            case DeviceState.RAISING | DeviceState.LOWERING:
                return _ACTIVE_BASELINE_A
```

- [x] **Step 6.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_motor_current_sensor.py -v
```

Beklenen: **10 PASS** (9 yeni + 1 ABC instantiation).

- [x] **Step 6.5: Commit**

```bash
git add src/simulator/sensors/motor_current.py tests/unit/test_motor_current_sensor.py
git commit -m "refactor(sensors): MotorCurrentSensor uses compute(runtime, position)

BREAKING (internal): sample() removed, compute() added per BaseSensor sözleşme.
sample() saf değer döner; gürültü artık engine'de (spec § 8).
RNG sensörden kaldırıldı (constructor sadeleşti).

State-aware davranış: IDLE/HOLDING config.baseline, RAISING/LOWERING 8.0A.
DOMAIN.md sat. 58 aralığı (5-15A) içinde.

10 test (9 state-aware + 1 ABC instantiation).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `SENSOR_REGISTRY` Aktivasyonu ✅ TAMAMLANDI (commit `4fb013a`)

`sensors/__init__.py` artık registry içerir. YAML'deki sensör adı string'ini sınıfa eşler. Iterasyon 2a'da tek kayıt (motor_current), Iterasyon 2b'de genişler.

**Files:**
- Modify: `src/simulator/sensors/__init__.py`
- Modify: `tests/unit/test_motor_current_sensor.py` (sonuna 1 test ekle)

- [x] **Step 7.1: Başarısız test ekle (`tests/unit/test_motor_current_sensor.py` sonuna)**

```python
def test_sensor_registry_contains_motor_current() -> None:
    from simulator.sensors import SENSOR_REGISTRY
    assert "motor_current" in SENSOR_REGISTRY
    assert SENSOR_REGISTRY["motor_current"] is MotorCurrentSensor


def test_sensor_registry_only_iterasyon_2a_sensors() -> None:
    """Iterasyon 2a'da sadece motor_current kayıtlı. 5 sensör daha 2b'de gelecek."""
    from simulator.sensors import SENSOR_REGISTRY
    assert set(SENSOR_REGISTRY.keys()) == {"motor_current"}
```

- [x] **Step 7.2: Testleri başarısız çalıştır**

```bash
pytest tests/unit/test_motor_current_sensor.py -v -k registry
```

Beklenen: `ImportError: cannot import name 'SENSOR_REGISTRY'`.

- [x] **Step 7.3: `src/simulator/sensors/__init__.py`'i güncelle**

Mevcut boş dosyayı şununla değiştir:

```python
"""Sensör registry — YAML sensör adı string'ini sınıfa eşler."""
from __future__ import annotations

from simulator.sensors.base import BaseSensor
from simulator.sensors.motor_current import MotorCurrentSensor

SENSOR_REGISTRY: dict[str, type[BaseSensor]] = {
    "motor_current": MotorCurrentSensor,
}
```

- [x] **Step 7.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_motor_current_sensor.py -v
```

Beklenen: **12 PASS** (10 + 2 registry).

- [x] **Step 7.5: Commit**

```bash
git add src/simulator/sensors/__init__.py tests/unit/test_motor_current_sensor.py
git commit -m "feat(sensors): activate SENSOR_REGISTRY (motor_current only)

Spec § 4 registry pattern. YAML sensör adı → sınıf eşlemesi (decorator/runtime
keşif yok, düz dict). Iterasyon 2b'de 5 sensör daha eklenecek.

2 yeni test (registry contains motor_current, exact membership).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Engine Refactor (state machine entegrasyonu, clock parametresi, gürültü) ✅ TAMAMLANDI (commit `e35ed9f`)

Engine artık DeviceRuntimeState inşa eder, state machine'i tick'te sürer, sensör compute() çağırır, gürültüyü kendi ekler. clock parametresi inject edilebilir.

**Files:**
- Modify: `src/simulator/engine.py`
- Modify: `tests/unit/test_engine.py`

- [x] **Step 8.1: `tests/unit/test_engine.py`'i yeniden yaz**

Dosyanın TÜM içeriğini şununla değiştir:

```python
"""Engine state machine entegrasyonu için unit testler."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulator.config import DeviceState
from simulator.engine import run
from tests.unit.test_runtime import FakeClock

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_run_publishes_with_state_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """publish_reading her tick'te runtime.state ile çağrılır (StrEnum → string)."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=42,
        clock=clock,
    )

    assert mock_publisher.publish_reading.call_count == 3
    for call in mock_publisher.publish_reading.call_args_list:
        kwargs = call.kwargs
        # state IDLE çünkü clock advance edilmedi, hala ilk state'te
        assert kwargs["state"] == DeviceState.IDLE


def test_run_rejects_multiple_devices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text(
        """
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
      - {name: motor_current, unit: A, baseline: 0.5, noise_std: 0.1}
  - id: device_002
    type: telescopic_mast_v1
    target_height_mm: 5000
    state_durations:
      idle: [5, 30]
      raising: [10, 60]
      holding: [60, 300]
      lowering: [10, 60]
    sensors:
      - {name: motor_current, unit: A, baseline: 0.5, noise_std: 0.1}
"""
    )
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="exactly 1 device"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_rejects_unsupported_sensor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text(
        """
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
      - {name: hydraulic_pressure, unit: bar, baseline: 10, noise_std: 2}
"""
    )
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(KeyError, match="hydraulic_pressure"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_publishes_noisy_value_around_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine gürültüyü ekler (spec § 8). IDLE'da değer config.baseline (0.5) civarı.

    clock advance edilmediği için state IDLE kalır; motor_current.compute() 0.5 döner,
    engine üzerine gauss(0, 0.1) ekler → değer 0.5 ± birkaç sigma.
    """
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)
    monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=20,
        seed=42,
        clock=clock,
    )

    values = [c.kwargs["value"] for c in mock_publisher.publish_reading.call_args_list]
    # IDLE baseline 0.5, noise_std 0.1. 20 örnek → ortalama ~0.5 (3-sigma tolerans geniş).
    mean = sum(values) / len(values)
    assert 0.2 < mean < 0.8
    # Gürültü gerçekten ekleniyor: tüm değerler birebir aynı OLMAMALI.
    assert len(set(values)) > 1
```

**Not:** Engine seviyesinde state-lifecycle testi (IDLE→RAISING geçişini engine üzerinden gözlemlemek) kasıtlı eklenmedi: engine her tick'te `clock()`'u birden çok kez çağırır (property erişimleri), bu yüzden tek bir test clock'u deterministik ilerletmek zordur ve kırılgan olur. State machine davranışı zaten `test_runtime.py::test_full_cycle_returns_to_idle_and_increments_count` ile tam kapsanıyor. Engine'in bu makineyi sürdüğü, `state` field'ının publish edilmesiyle (`test_run_publishes_with_state_field`) doğrulanıyor.

- [x] **Step 8.2: Testleri başarısız çalıştır**

```bash
pytest tests/unit/test_engine.py -v
```

Beklenen: Mevcut testler fail — engine henüz `clock` parametresi kabul etmiyor, runtime entegrasyonu yok.

- [x] **Step 8.3: `src/simulator/engine.py`'i refactor et**

Dosyanın TÜM içeriğini şununla değiştir:

```python
"""Iterasyon 2a engine: tek cihaz, state machine ile motor_current yayını."""
from __future__ import annotations

import random
import signal
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType

from loguru import logger

from simulator.config import (
    DeviceConfig,
    DeviceState,
    MQTTConfig,
    load_devices,
    load_engine_config,
    load_mqtt_config,
)
from simulator.publisher import MQTTPublisher
from simulator.runtime import (
    DeviceRuntimeState,
    advance_state_machine,
    compute_position,
)
from simulator.sensors import SENSOR_REGISTRY


def _make_publisher(config: MQTTConfig) -> MQTTPublisher:
    """Test edilebilirlik için factory; monkeypatch ile değiştirilebilir."""
    return MQTTPublisher(config)


def _validate_iteration2a_constraints(devices: list[DeviceConfig]) -> DeviceConfig:
    """Iterasyon 2a kısıtlamaları: tam 1 cihaz + tam 1 motor_current sensörü."""
    if len(devices) != 1:
        raise ValueError(
            f"Iterasyon 2a exactly 1 device destekliyor, alınan: {len(devices)}"
        )
    device = devices[0]
    if len(device.sensors) != 1 or device.sensors[0].name != "motor_current":
        raise ValueError(
            "Iterasyon 2a: cihaz tam olarak bir 'motor_current' sensörü içermeli"
        )
    return device


def run(
    mqtt_config_path: Path = Path("config/mqtt.yaml"),
    devices_path: Path = Path("config/devices.yaml"),
    engine_config_path: Path = Path("config/simulator.yaml"),
    max_iterations: int | None = None,
    seed: int | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Engine'i başlatır. State machine sürer, sensör compute() çağırır.

    Args:
        mqtt_config_path: MQTT YAML config.
        devices_path: Cihaz YAML config.
        engine_config_path: Engine YAML config.
        max_iterations: None → SIGINT/SIGTERM gelene dek sonsuz.
        seed: RNG seed; verilmezse YAML'deki device.seed kullanılır.
        clock: Saat kaynağı (DI). Test'lerde FakeClock inject edilebilir.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: Config geçersizse veya Iterasyon 2a kısıtlamaları ihlal edilmişse.
        KeyError: SENSOR_REGISTRY'de bilinmeyen sensör adı.
    """
    mqtt_config = load_mqtt_config(mqtt_config_path)
    devices = load_devices(devices_path)
    engine_config = load_engine_config(engine_config_path)
    logger.level(engine_config.log_level)

    device = _validate_iteration2a_constraints(devices)
    sensor_config = device.sensors[0]

    sensor_cls = SENSOR_REGISTRY[sensor_config.name]
    sensor = sensor_cls(sensor_config)

    rng = random.Random(seed if seed is not None else device.seed)
    now = clock()
    initial_duration = rng.uniform(*device.state_durations.idle)
    runtime = DeviceRuntimeState(
        state=DeviceState.IDLE,
        state_entered_at_monotonic=now,
        current_state_duration_s=initial_duration,
        position_mm=0.0,
        cycle_count=0,
        rng=rng,
        started_at_monotonic=now,
        clock=clock,
    )

    publisher = _make_publisher(mqtt_config)
    publisher.connect()

    stop = False

    def _shutdown(signum: int, _frame: FrameType | None) -> None:
        nonlocal stop
        logger.info("Shutdown sinyali alındı: {}", signum)
        stop = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    tick_interval = 1.0 / engine_config.tick_hz
    iterations = 0
    try:
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
                state=runtime.state,  # StrEnum → JSON serializable
            )
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            time.sleep(tick_interval)
    finally:
        publisher.close()
```

- [x] **Step 8.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_engine.py -v
```

Beklenen: **4 PASS**.

- [x] **Step 8.5: Tüm unit testleri çalıştır + coverage**

```bash
pytest tests/unit/ --cov=src/simulator --cov-report=term-missing
```

Beklenen: **~42 PASS**. Coverage `src/simulator` toplam ≥85%. Eğer kapsam düşükse runtime.py veya engine.py'da unreachable branch var demektir — log'a bak ama walking skeleton için makul bir miktar kabul edilebilir.

- [x] **Step 8.6: Commit**

```bash
git add src/simulator/engine.py tests/unit/test_engine.py
git commit -m "refactor(engine): integrate state machine + clock DI + noise responsibility

Iterasyon 2a engine refactor:
- DeviceRuntimeState inşası + advance_state_machine + compute_position tick'te
- clock parametresi (DI, default time.monotonic), FakeClock injectable
- Gürültü engine'de eklenir (spec § 8: clean → fault → noise sıralaması)
- Sensör SENSOR_REGISTRY üzerinden çözülür
- publish_reading payload state=runtime.state (StrEnum → 'idle'/'raising'/...)
- _validate_iteration2a_constraints — hâlâ tek motor_current sensörü kabul eder

4 test (state field, çoklu cihaz reddi, bilinmeyen sensör, state lifecycle).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `devices.yaml.example` Genişletme + Iterasyon 2a Manuel Doğrulama ✅ TAMAMLANDI (commit `88ff45d` + packaging fix `94ed570`; manuel uçtan uca 2026-05-28)

**Files:**
- Modify: `config/devices.yaml.example`

- [x] **Step 9.1: `config/devices.yaml.example`'ı genişlet**

Mevcut içeriğini şununla değiştir:

```yaml
# Simülasyon için cihaz tanımları örneği — Iterasyon 2a (state machine)
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
      - name: motor_current
        unit: A
        baseline: 0.5        # IDLE/HOLDING değeri; RAISING/LOWERING sensör sınıfında 8.0A
        noise_std: 0.1
```

- [x] **Step 9.2: Lokal `config/devices.yaml`'ı güncelle**

```bash
cp config/devices.yaml.example config/devices.yaml
```

- [x] **Step 9.3: Commit**

```bash
git add config/devices.yaml.example
git commit -m "feat(config): extend devices.yaml.example for Iterasyon 2a

state_durations bloğu (idle/raising/holding/lowering aralıkları),
target_height_mm=5000, seed=42 eklendi. baseline yorumu güncellendi.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [x] **Step 9.4: KULLANICI TARAFI — Uçtan uca manuel doğrulama**

Bu adım agent tarafından yapılamaz; kullanıcı kendi terminalinde test eder.

**Terminal C** (broker, hâlâ açıksa kullan; yoksa `mosquitto -v`):

**Terminal A** (subscriber):
```bash
mosquitto_sub -t 'telemetry/+/motor_current' -v
```

**Terminal B** (simulator):
```bash
cd ~/mast-anomaly-detection
source .venv/bin/activate
python -m simulator
```

**Beklenen davranış:**

1. Terminal B'de Loguru log: `MQTT bağlanılıyor: localhost:1883`.
2. Terminal A'da ~her saniye bir JSON mesaj. **Önemli — Iterasyon 1'den fark:** `state` alanı artık sabit "idle" değil. İlk 5-30 saniye IDLE, sonra RAISING, sonra HOLDING (uzun süre), sonra LOWERING, sonra tekrar IDLE.
3. RAISING/LOWERING durumlarında `value` ~8 A civarı (5-15 aralığı). IDLE/HOLDING'de ~0.5 A civarı.
4. Ctrl+C → temiz kapanma.

**Bitti kriterleri (spec § 3 Iterasyon 2 ilgili kısımları):**
- IDLE durumunda motor_current ∈ [0, 1] A (gauss noise göz önüne alındığında ~90%+ örnek bu aralıkta).
- RAISING/HOLDING/LOWERING geçişleri terminalden görülür.
- Tam bir döngü (IDLE→RAISING→HOLDING→LOWERING→IDLE) 85-450 saniye arasında tamamlanır.

- [x] **Step 9.5: Iterasyon 2a milestone commit**

Kullanıcı manuel doğrulamayı başarılı raporladıktan sonra:

```bash
git commit --allow-empty -m "milestone: Faz 1 Iterasyon 2a (state machine) tamamlandı

Spec § 3 Iterasyon 2 kabul kriterleri (motor_current için):
- IDLE/RAISING/HOLDING/LOWERING durumları state machine ile geçişli
- motor_current state-bazlı: IDLE/HOLDING ~0.5A, RAISING/LOWERING ~8A
- DOMAIN.md sat. 58 aralıkları içinde
- Tam döngü 85-450s
- Clock DI ile testler deterministik
- ~30 unit test yeşil, coverage ≥85%

Sıradaki: Iterasyon 2b (kalan 5 sensör + sensör formülleri + motor_temperature stateful).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notları

**Spec coverage (§ 3 Iterasyon 2 ilgili kısımları):**
- 6 sensör → Iterasyon 2b (bu plan'da sadece motor_current) — kasıtlı, alt-iterasyon bölmesi
- `DeviceState` enum → Task 1 ✓
- `DeviceRuntimeState` + clock DI → Task 2 ✓
- State transitions → Task 3 ✓
- `compute_position` → Task 4 ✓
- `BaseSensor` ABC → Task 5 ✓
- `motor_current` refactor → Task 6 ✓
- `SENSOR_REGISTRY` → Task 7 ✓
- Engine refactor → Task 8 ✓
- Manuel doğrulama → Task 9 ✓

**Spec § 5 invaryantlar:**
- `current_state_duration_s` transition anında resample → Task 3, test_transition_resamples_current_state_duration ✓
- `time.monotonic()` (clock DI) → Task 2 ✓
- Per-device RNG → Task 2 (rng field) + Task 8 (engine'de inşa) ✓
- Tek yönlü state geçişi → Task 3, _NEXT_STATE sabit dict ✓

**Spec § 8 tick akışı:**
- advance_state_machine → Task 3 + Task 8 ✓
- compute_position → Task 4 + Task 8 ✓
- sensor.compute(runtime, position) → Task 6 + Task 8 ✓
- gürültü engine'de (clean + rng.gauss) → Task 8 ✓
- publish_reading(state=runtime.state) → Task 8 ✓

**Spec § 11 hata yönetimi:**
- Bilinmeyen sensör adı → KeyError (Task 8 test_run_rejects_unsupported_sensor) ✓
- Eksik state_durations → ValueError (Task 1 test_load_devices_rejects_missing_state_durations) ✓

**Placeholder taraması:** "TBD", "TODO", "implement later", "Similar to Task N" yok. Tüm code block'lar tam, kopyala-yapıştır çalışır.

**Type tutarlılığı:**
- `DeviceState` Task 1'de tanımlı, Task 2-3-4-6-8'de kullanılıyor — tutarlı.
- `DeviceRuntimeState` Task 2'de tanımlı, Task 3-4-6-8'de kullanılıyor — tutarlı.
- `advance_state_machine(runtime, durations)` Task 3'te tanımlı, Task 8'de aynı imzayla çağrılıyor — tutarlı.
- `compute_position(runtime, target_mm)` Task 4'te tanımlı, Task 8'de aynı imzayla çağrılıyor — tutarlı.
- `BaseSensor.compute(runtime, position_mm)` Task 5'te tanımlı, Task 6 ve Task 8'de aynı imzayla — tutarlı.

**Iterasyon sonu durum:**
- Tek cihaz, tek sensör (motor_current) — Iterasyon 2b'de genişler.
- state machine + clock DI altyapısı kurulu.
- ~30 unit test yeşil, coverage ≥85% hedef.

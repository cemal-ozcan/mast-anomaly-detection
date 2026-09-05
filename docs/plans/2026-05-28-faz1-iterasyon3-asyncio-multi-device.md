# Faz 1 — Iterasyon 3: asyncio + Çoklu Cihaz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task's final verification step MUST run the FULL suite + mypy + ruff over BOTH src and tests (see [[feedback-full-suite-per-task]]).

**Goal:** Iter 2b'nin blocking tek-cihaz engine'ini asyncio loop'a geçirip aynı YAML'den N cihazı paralel task'lar halinde MQTT'ye yayınlayan engine'e dönüştürmek. Spec § 3 Iter 3'ün 4 bitti kriterini karşılayacak (3 cihaz paralel akış, aynı seed regresyon, 2-cihaz integration test, 71 mevcut unit test yeşil).

**Architecture:** `engine.run()` artık `asyncio.run(_amain(...))` çağırır; `_amain` (a) tüm cihazlar için ortak `engine_boot_at = clock()` snapshot'ını alır, (b) tek paylaşılan `MQTTPublisher` kurar, (c) `asyncio.Event` shutdown + `loop.add_signal_handler(SIGINT/SIGTERM, shutdown.set)` register eder, (d) her cihaz için bir `asyncio.create_task(run_device(...))` spawn eder, (e) `asyncio.gather(*tasks)` ile hepsi bitene kadar bekler, sonra publisher'ı kapatır. `run_device` Iter 2b'nin tick gövdesini async hale getirir (`time.sleep` → `await asyncio.sleep`, `nonlocal stop` → `shutdown.is_set()`). Cihazlar arasında shared state yok: her cihazın kendi `DeviceRuntimeState`, kendi `random.Random(seed)`, kendi sensor instance listesi (sadece publisher + boot timestamp paylaşılır).

**Tech Stack:** Iter 2b ile aynı (Python 3.11+ asyncio stdlib, paho-mqtt, mypy strict, ruff, pytest, loguru). Yeni dev dependency: `pytest-asyncio==0.23.7` (auto-mode, `async def test_*` otomatik yakalanır).

**Referans:** `docs/specs/2026-05-18-faz1-simulator-design.md` (commit `59fcff8` — Iter 3 mikro-kararları + asyncio test pattern + 4 self-review düzeltmesi inline). Spec § 3 Iter 3 Kapsam & Bitti, § 5 invaryantlar (`started_at_monotonic` ortak referans notu), § 8 Çoklu cihaz alt başlığı, § 11 SIGINT asyncio satırı, § 12 Asyncio Test Pattern.

---

## Önkoşul

`.venv` aktif, `pip install -e .` yapılmış, Iter 2b testleri (71 PASS) yeşil olmalı:

```bash
cd ~/mast-anomaly-detection
source .venv/bin/activate
pytest tests/ -q                          # 71 passed beklenir
mypy src/simulator tests/unit             # Success
ruff check src/simulator tests/unit       # All checks passed
```

Eğer baseline kırıksa durduralım ve önce neden anlaşılsın — Iter 3 task'ları bu zemine binecek.

---

## Dosya Yapısı (Iter 3 sonunda)

```
src/simulator/
├── engine.py                              # MAJOR REFACTOR: asyncio.run + _amain + run_device + _validate_devices
├── ... (diğer dosyalar değişmez)

tests/
├── conftest.py                            # değişmez
├── unit/
│   ├── test_engine.py                     # GENİŞLET: asyncio testleri, multi-device, same-seed regresyon
│   ├── test_validation.py                 # YENİ: _validate_devices testleri (yeni dosya)
│   └── ... (diğer 6 sensor + runtime + config + publisher testleri değişmez)
├── integration/
│   └── test_multi_device_engine.py        # YENİ: 2 cihaz paralel integration
└── fixtures/
    ├── devices_minimal.yaml               # değişmez (1 cihaz, 6 sensör — unit testler için)
    ├── devices_multi.yaml                 # YENİ: 2 cihaz, farklı seed (integration için)
    └── devices_same_seed.yaml             # YENİ: 2 cihaz, aynı seed (regresyon için)

config/
└── devices.yaml.example                   # GENİŞLET: 3 cihaz örneği (manuel smoke için)

requirements.txt                            # GÜNCELLE: + pytest-asyncio==0.23.7

pyproject.toml                              # GÜNCELLE: [tool.pytest_asyncio] asyncio_mode = "auto"
```

**Beklenen test sayısı:** ~85+ (Iter 2b 71 + ~14 yeni: validation 5 + engine asyncio 4 + same-seed 2 + integration 3).
**Hedef coverage:** ≥%80 (Iter 2b ~%93'tü; asyncio code daha az kontrol akışı içerdiği için hafif düşebilir, eşik altına inmemeli).

---

## Task 1: pytest-asyncio Kurulumu + Auto-Mode Yapılandırması

Yeni dev dependency + pyproject config + sanity async test. Bu task'ın amacı altyapıyı kurmak; davranış değişikliği YOK.

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Create: `tests/unit/test_async_infrastructure.py`

- [x] **Step 1.1: `requirements.txt` içine pytest-asyncio ekle**

Mevcut "# Testing" bloğunu şuna güncelle:
```
# Testing
pytest==8.2.2
pytest-cov==5.0.0
pytest-asyncio==0.23.7
```

- [x] **Step 1.2: pip install ile dependency'yi kur**

```bash
pip install -r requirements.txt
```
Beklenen: `Successfully installed pytest-asyncio-0.23.7` (veya zaten kuruluysa "Requirement already satisfied").

- [x] **Step 1.3: `pyproject.toml` içine `asyncio_mode = "auto"` ekle**

`asyncio_mode` pytest-asyncio'nun pytest-ini option'ı; ayrı bir `[tool.pytest_asyncio]` section'a DEĞİL, mevcut `[tool.pytest.ini_options]` bloğunun İÇİNE eklenir (örn. `addopts` satırının altına):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-ra --strict-markers --cov=src --cov-report=term-missing"
asyncio_mode = "auto"
```

Bu, `@pytest.mark.asyncio` decorator gerekmeden `async def test_*` fonksiyonlarının otomatik koşturulmasını sağlar. (İlk yazımda ayrı `[tool.pytest_asyncio]` section önerilmişti — pytest-asyncio 0.23.7 o key'i okumuyor, async testler SKIPPED kalıyor.)

- [x] **Step 1.4: Sanity async test dosyası yaz**

Create `tests/unit/test_async_infrastructure.py`:
```python
"""Iter 3 altyapı testi: pytest-asyncio + asyncio.sleep no-op pattern çalışıyor mu?"""
from __future__ import annotations

import asyncio

import pytest


async def test_async_test_runner_works() -> None:
    """pytest-asyncio auto-mode ile async def test çalışmalı."""
    await asyncio.sleep(0)
    assert True


async def test_asyncio_sleep_can_be_monkeypatched_without_recursion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec § 12 pattern: orijinal sleep referansını sakla, lambda onu çağırsın.

    Bu test recursive-lambda hatasının regression koruyucusudur.
    """
    original_sleep = asyncio.sleep
    monkeypatch.setattr("asyncio.sleep", lambda _s: original_sleep(0))

    # 1.0 sn istesek bile gerçekte 0 sn bekler
    await asyncio.sleep(1.0)
    await asyncio.sleep(5.0)
    assert True  # Sonsuz döngü olsa buraya gelmezdik
```

- [x] **Step 1.5: Testi çalıştır ve yeşil gör**

```bash
pytest tests/unit/test_async_infrastructure.py -v
```
Beklenen: 2 passed.

- [x] **Step 1.6: Tam suite + mypy + ruff yeşil**

```bash
pytest tests/ -q                          # 71 + 2 = 73 passed
mypy src/simulator tests/unit             # Success
ruff check src/simulator tests/unit       # All checks passed
```

- [x] **Step 1.7: Commit**

```bash
git add requirements.txt pyproject.toml tests/unit/test_async_infrastructure.py
git commit -m "$(cat <<'EOF'
chore(deps): add pytest-asyncio + auto-mode for Iter 3

pytest-asyncio==0.23.7 dev dep; pyproject asyncio_mode="auto"
async def test_* fonksiyonlarını decorator'sız yakalar.
Sanity test recursive-lambda monkeypatch hatasını regression-koruyor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `_validate_iteration2b_constraints` → `_validate_devices` Refactor

Validation fonksiyonunu N cihaza açar; her cihaz hâlâ tam 6-sensör setini içermek zorunda; ID'ler unique; aynı seed birden fazla cihazda WARN log. Engine HÂLÂ tek cihaz çalıştırıyor (henüz `devices[0]`'ı alıyor) — multi-device spawn Task 5'te gelecek. Bu task TDD ile validator'ü hazırlar.

**Files:**
- Modify: `src/simulator/engine.py` (sadece validation fonksiyonu + import + bir çağrı satırı)
- Create: `tests/unit/test_validation.py`

- [x] **Step 2.1: `tests/unit/test_validation.py` yaz (TDD failing tests)**

```python
"""_validate_devices testleri (Iter 3 — N cihaz desteği)."""
from __future__ import annotations

import logging

import pytest

from simulator.config import DeviceConfig, SensorConfig, StateDurations
from simulator.engine import _validate_devices


_SIX_SENSORS = [
    SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1),
    SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2),
    SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0),
    SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5),
    SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0),
    SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01),
]


def _make_device(device_id: str, seed: int | None = 42) -> DeviceConfig:
    return DeviceConfig(
        id=device_id,
        type="telescopic_mast_v1",
        sensors=list(_SIX_SENSORS),
        state_durations=StateDurations(
            idle=(5.0, 5.0),
            raising=(10.0, 10.0),
            holding=(60.0, 60.0),
            lowering=(10.0, 10.0),
        ),
        target_height_mm=5000.0,
        seed=seed,
    )


def test_validate_accepts_single_device() -> None:
    """Tek cihaz + 6 sensör geçerli (Iter 2b geri uyumluluğu)."""
    _validate_devices([_make_device("d1")])  # raise etmez


def test_validate_accepts_multiple_devices_with_unique_ids() -> None:
    """N cihaz, her biri 6 sensör, unique ID — geçerli."""
    _validate_devices([_make_device("d1"), _make_device("d2", seed=7)])


def test_validate_rejects_empty_device_list() -> None:
    """En az 1 cihaz olmalı."""
    with pytest.raises(ValueError, match="en az 1 cihaz"):
        _validate_devices([])


def test_validate_rejects_duplicate_device_ids() -> None:
    """Aynı device.id iki kez → topic collision riski → hata."""
    with pytest.raises(ValueError, match="unique"):
        _validate_devices([_make_device("d1"), _make_device("d1", seed=7)])


def test_validate_rejects_missing_sensor() -> None:
    """Bir cihazda 6 sensörden biri eksikse hata."""
    bad = _make_device("d1")
    bad_sensors = [s for s in _SIX_SENSORS if s.name != "vibration"]
    bad = DeviceConfig(
        id=bad.id,
        type=bad.type,
        sensors=bad_sensors,
        state_durations=bad.state_durations,
        target_height_mm=bad.target_height_mm,
        seed=bad.seed,
    )
    with pytest.raises(ValueError, match="vibration"):
        _validate_devices([bad])


def test_validate_warns_when_two_devices_share_seed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Aynı seed'li iki cihaz WARN log basar (hata değil — regresyon testi kullanım örneği)."""
    # loguru pytest caplog ile çalışması için propagate gerekiyor — engine import
    # edildiğinde loguru zaten yapılandırılıyor. Test'te caplog seviyesini WARNING'a alıyoruz.
    from loguru import logger as loguru_logger

    handler_id = loguru_logger.add(caplog.handler, level="WARNING", format="{message}")
    try:
        with caplog.at_level(logging.WARNING):
            _validate_devices([_make_device("d1", seed=42), _make_device("d2", seed=42)])
    finally:
        loguru_logger.remove(handler_id)

    # Hata raise edilmemiş; ama WARN mesajı atılmış olmalı
    assert any("aynı seed" in record.message.lower() or "same seed" in record.message.lower()
               for record in caplog.records)
```

- [x] **Step 2.2: Testleri çalıştır, FAIL gör (fonksiyon henüz yok)**

```bash
pytest tests/unit/test_validation.py -v
```
Beklenen: `ImportError` veya `AttributeError: _validate_devices` — fonksiyon henüz yok.

- [x] **Step 2.3: `src/simulator/engine.py` içinde `_validate_iteration2b_constraints` yerine `_validate_devices` yaz**

Mevcut `_validate_iteration2b_constraints` fonksiyonunu (line ~46-65) TAMAMEN SİL ve yerine şunu koy:

```python
def _validate_devices(devices: list[DeviceConfig]) -> None:
    """Iter 3 validasyonu: N cihaz, her biri tam 6 sensör seti, unique ID'ler.

    Args:
        devices: YAML'den yüklenmiş cihaz config'leri.

    Raises:
        ValueError: Liste boşsa, herhangi bir cihazda 6 sensör setinden sapma varsa,
            veya device.id değerleri arasında duplikasyon varsa.

    Aynı `seed` birden fazla cihazda görülürse hata DEĞİL, WARN log basılır
    (spec § 3 Iter 3 bitti kriteri #2 — aynı seed regresyon testi meşru kullanım).
    """
    if len(devices) < 1:
        raise ValueError("Iterasyon 3: en az 1 cihaz tanımlı olmalı")

    # ID uniqueness
    ids = [d.id for d in devices]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(
            f"Iterasyon 3: device.id değerleri unique olmalı (duplikatlar: {dupes})"
        )

    # Her cihazda tam 6-sensör seti
    for device in devices:
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
                f"Iterasyon 3: cihaz '{device.id}' tam 6-sensör seti içermeli "
                f"({', '.join(parts)})"
            )

    # Same-seed → WARN (hata değil)
    seeds = [d.seed for d in devices if d.seed is not None]
    duplicated_seeds = sorted({s for s in seeds if seeds.count(s) > 1})
    if duplicated_seeds:
        logger.warning(
            "Birden fazla cihazda aynı seed kullanılıyor: {} — "
            "bu deterministik regresyon senaryosu için meşru, ama production'da "
            "cihazların aynı değer dizilerini üreteceğini unutmayın.",
            duplicated_seeds,
        )
```

Sonra `engine.run()` içinde mevcut:
```python
device = _validate_iteration2b_constraints(devices)
```
satırını şununla değiştir (henüz tek cihaz çalıştırıyoruz — multi-device spawn Task 5):
```python
_validate_devices(devices)
device = devices[0]  # Iter 3 ara durum: validation N cihazı kabul ediyor ama engine hâlâ tek çalıştırıyor
```

- [x] **Step 2.4: Validation testlerini koş, yeşil gör**

```bash
pytest tests/unit/test_validation.py -v
```
Beklenen: 6 passed.

- [x] **Step 2.5: Tam suite (mevcut testler kırılmamalı)**

```bash
pytest tests/ -q
```
Beklenen: 73 + 6 = 79 passed. Iter 2b engine testleri hâlâ yeşil çünkü `devices_minimal.yaml` zaten geçerli tek cihaz.

- [x] **Step 2.6: mypy + ruff yeşil**

```bash
mypy src/simulator tests/unit
ruff check src/simulator tests/unit
```
Beklenen: ikisi de clean.

- [x] **Step 2.7: Commit**

```bash
git add src/simulator/engine.py tests/unit/test_validation.py
git commit -m "$(cat <<'EOF'
refactor(engine): _validate_iteration2b_constraints → _validate_devices

N cihaz desteği için validasyon gevşetildi:
- Cihaz sayısı ≥ 1 (önceden tam = 1)
- device.id değerleri unique
- Her cihaz hâlâ tam 6-sensör seti içermek zorunda (spec § 6 disiplini)
- Aynı seed birden fazla cihazda → WARN log (regresyon testi meşru kullanım)

Engine hâlâ tek cihaz çalıştırıyor (devices[0]); multi-device spawn Task 5'te.
6 yeni validation testi, mevcut Iter 2b davranışı korunuyor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `async def run_device(...)` Çıkarımı — Tek Cihaz, Asyncio

Engine'in tick döngüsünü async fonksiyona taşır. `engine.run()` artık `asyncio.run(run_device(...))` çağırır. `time.sleep` → `await asyncio.sleep`. `nonlocal stop` → `shutdown_event.is_set()`. Hâlâ tek cihaz; çoklu cihaz spawn Task 5'te. Bu task sadece async dönüşümü test eder.

**Files:**
- Modify: `src/simulator/engine.py` (major refactor)
- Modify: `tests/unit/test_engine.py` (mevcut testlerin asyncio'ya uyumlu hale getirilmesi)

- [x] **Step 3.1: Mevcut test_engine.py testlerinin DURUMUNU NOTLA**

Şunları çalıştır ve baseline'ı kayda al:
```bash
pytest tests/unit/test_engine.py -v
```
Beklenen: tüm mevcut engine testleri (4-6 adet) PASS. Bu task sonunda hepsi hâlâ PASS olmalı (davranış aynı, sadece iç implementasyon async).

- [x] **Step 3.2: `src/simulator/engine.py` üst tarafına import ve yardımcı sleep ekle**

Mevcut import'lar arasına `import asyncio` ekle (alfabetik sıra: `import asyncio` `random`'ın üstüne). `time` import'u kalsın — `time.monotonic` clock default'u için hâlâ lazım. `signal` import'u Task 4'te güncellenecek, şimdilik dursun.

Dosyada (üst seviyede, `_make_publisher`'ın altında) yeni async fonksiyonu ekle:

```python
async def run_device(
    device: DeviceConfig,
    runtime: DeviceRuntimeState,
    sensors: list[BaseSensor],
    publisher: MQTTPublisher,
    tick_interval: float,
    shutdown_event: asyncio.Event,
    max_iterations: int | None = None,
) -> None:
    """Tek cihazın asyncio tick döngüsü. Spec § 8 tick akışı asyncio versiyonu.

    Args:
        device: Cihaz config'i (id, sensors, state_durations, target_height_mm).
        runtime: Önceden başlatılmış `DeviceRuntimeState` (clock + started_at_monotonic
            engine'de set edilmiş). Tüm randomness `runtime.rng` üzerinden akar —
            engine-side noise dahil bu cihaza ait tek `random.Random(seed)` kaynağıdır
            (spec § 5 invaryantı).
        sensors: Önceden registry'den inşa edilmiş sensor instance listesi.
        publisher: Paylaşılan MQTTPublisher (N cihazlı engine'de aynı instance).
        tick_interval: Saniye cinsinden tick periyodu (engine_config.tick_hz'den).
        shutdown_event: Set edildiğinde döngü tick başında çıkar (SIGINT/SIGTERM
            veya test-side .set()).
        max_iterations: None → shutdown_event'e kadar sonsuz. Int verilirse o kadar
            tick sonra normal çıkış (testlerde max_iterations=N kullanılır).

    Note:
        Bu fonksiyon kendi engine'i başlatmaz, kendi publisher'ını connect etmez —
        bunları engine.run() / _amain orkestre eder. Burada sadece tick gövdesi var.
    """
    iterations = 0
    while not shutdown_event.is_set():
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
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return
        await asyncio.sleep(tick_interval)
```

- [x] **Step 3.3: `engine.run()` gövdesini yeniden yaz — asyncio'ya geçiş ama tek cihaz**

Mevcut `run()` fonksiyonunun gövdesini AŞAĞIDAKİ İLE TAM DEĞİŞTİR (signature aynı kalır):

```python
def run(
    mqtt_config_path: Path = Path("config/mqtt.yaml"),
    devices_path: Path = Path("config/devices.yaml"),
    engine_config_path: Path = Path("config/simulator.yaml"),
    max_iterations: int | None = None,
    seed: int | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Engine entry — asyncio.run(_amain) sarmalayıcısı.

    Args/Raises: önceki sürümle aynı. İçeride asyncio.run kullanılır.

    Note (Iter 3): Bu task tek cihaz çalıştırır; Task 5 multi-device spawn ekler.
    """
    mqtt_config = load_mqtt_config(mqtt_config_path)
    devices = load_devices(devices_path)
    engine_config = load_engine_config(engine_config_path)
    logger.level(engine_config.log_level)

    _validate_devices(devices)
    device = devices[0]  # Iter 3 Task 3 ara durum

    sensors: list[BaseSensor] = [
        SENSOR_REGISTRY[sc.name](sc) for sc in device.sensors
    ]

    rng = random.Random(seed if seed is not None else device.seed)
    engine_boot_at = clock()
    initial_duration = rng.uniform(*device.state_durations.idle)
    runtime = DeviceRuntimeState(
        state=DeviceState.IDLE,
        state_entered_at_monotonic=engine_boot_at,
        current_state_duration_s=initial_duration,
        position_mm=0.0,
        cycle_count=0,
        rng=rng,
        started_at_monotonic=engine_boot_at,
        clock=clock,
    )

    publisher = _make_publisher(mqtt_config)
    publisher.connect()

    tick_interval = 1.0 / engine_config.tick_hz

    async def _amain() -> None:
        shutdown = asyncio.Event()
        # Task 4'te add_signal_handler eklenecek; Task 3 sonu sinyal yok,
        # max_iterations veya KeyboardInterrupt ile çıkış.
        try:
            await run_device(
                device=device,
                runtime=runtime,
                sensors=sensors,
                publisher=publisher,
                tick_interval=tick_interval,
                shutdown_event=shutdown,
                max_iterations=max_iterations,
            )
        finally:
            publisher.close()

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — Task 4'te add_signal_handler ile temiz shutdown gelecek")
```

ESKİ `signal.signal(...)` ÇAĞRILARINI VE `stop = False` `nonlocal` PATTERN'İNİ KALDIR. (Task 4 asyncio sinyal yöneticisini ekleyecek.) `signal` import'u şimdilik kalabilir (Task 4 kaldıracak), ya da bu task'ta `# noqa: F401` ile bırakabilirsin — daha temiz olan: şimdi sil, Task 4 zaten ekleyecek (asyncio versiyonu kullanmayacak). Ruff F401 unused import yakalar — sil.

- [x] **Step 3.4: Mevcut `tests/unit/test_engine.py` testlerinde `time.sleep` monkeypatch'ini `asyncio.sleep`'e çevir**

`tests/unit/test_engine.py` içinde GLOBAL search-replace:

Eski:
```python
monkeypatch.setattr("simulator.engine.time.sleep", lambda _: None)
```

Yeni (her testin başında bir kez — orijinal sleep referansını kullan):
```python
_original_sleep = asyncio.sleep
monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: _original_sleep(0))
```

Dosyanın en üstündeki import bloğuna `import asyncio` ekle (alfabetik).

ÖNEMLİ: `_original_sleep` her test fonksiyonunun lokal scope'unda tanımlanmalı (test izolasyonu). Eğer modul-seviyesinde tanımlarsan import sırasında zaten doğru asyncio.sleep yakalanır, ama her test başında re-snapshot daha güvenli.

- [x] **Step 3.5: `test_engine.py`'deki engine.run testlerini koş, yeşil gör**

```bash
pytest tests/unit/test_engine.py -v
```
Beklenen: tüm mevcut engine testleri PASS. Eğer FAIL varsa: muhtemelen sleep monkeypatch path yanlış (`simulator.engine.asyncio.sleep`) — `import asyncio` engine.py'de top-level olmalı (Step 3.2'de eklendi).

- [x] **Step 3.6: Yeni test ekle — `run_device` doğrudan çağrı**

`tests/unit/test_engine.py` SONUNA ekle:

```python
async def test_run_device_respects_max_iterations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_device max_iterations'a ulaşınca temiz biter (shutdown.set path Task 4'te ayrı test)."""
    import asyncio as _asyncio
    import random as _random

    from simulator.config import DeviceState, SensorConfig, StateDurations
    from simulator.engine import run_device
    from simulator.runtime import DeviceRuntimeState
    from simulator.sensors import SENSOR_REGISTRY

    # Sensor config + device-equivalent fixture
    sensor_cfgs = [
        SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1),
        SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2),
        SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0),
        SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5),
        SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0),
        SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01),
    ]
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in sensor_cfgs]

    from simulator.config import DeviceConfig
    device = DeviceConfig(
        id="d1",
        type="telescopic_mast_v1",
        sensors=sensor_cfgs,
        state_durations=StateDurations(
            idle=(5.0, 5.0), raising=(10.0, 10.0),
            holding=(60.0, 60.0), lowering=(10.0, 10.0),
        ),
        target_height_mm=5000.0,
        seed=42,
    )

    clock = FakeClock(0.0)
    rng = _random.Random(42)
    runtime = DeviceRuntimeState(
        state=DeviceState.IDLE,
        state_entered_at_monotonic=0.0,
        current_state_duration_s=rng.uniform(*device.state_durations.idle),
        position_mm=0.0,
        cycle_count=0,
        rng=rng,
        started_at_monotonic=0.0,
        clock=clock,
    )

    publisher = MagicMock()
    shutdown = _asyncio.Event()

    # asyncio.sleep no-op
    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    await run_device(
        device=device, runtime=runtime, sensors=sensors,
        publisher=publisher, tick_interval=1.0,
        shutdown_event=shutdown, max_iterations=3,
    )
    # 3 tick × 6 sensör = 18 publish
    assert publisher.publish_reading.call_count == 18
```

- [x] **Step 3.7: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit
ruff check src/simulator tests/unit
```
Beklenen: 80 passed (79 + 1 yeni), mypy clean, ruff clean. `signal` unused import varsa Step 3.3'te kaldırıldığını doğrula.

- [x] **Step 3.8: Manuel duman testi — `python -m simulator` hâlâ yayın yapıyor mu?**

Ayrı terminalde mosquitto açık olmalı:
```bash
mosquitto_sub -t 'telemetry/+/+'
```
Sonra:
```bash
python -m simulator
```
Beklenen: Saniyede 6 satır mesaj (motor_current, motor_voltage, hydraulic_pressure, motor_temperature, mast_position, vibration), `device_001` topic'inden. Ctrl+C → KeyboardInterrupt → temiz çıkış. Task 4 asyncio sinyal yönetimini ekleyecek.

- [x] **Step 3.9: Commit**

```bash
git add src/simulator/engine.py tests/unit/test_engine.py
git commit -m "$(cat <<'EOF'
refactor(engine): async def run_device + asyncio.run wrapper (tek cihaz)

engine.run() artık asyncio.run(_amain()) çağırıyor; tick gövdesi async
def run_device(...) fonksiyonuna çıkarıldı. time.sleep → await asyncio.sleep.
shutdown asyncio.Event ile yönetiliyor (signal handler Task 4'te).
max_iterations parametresi per-device (Iter 2b'deki global'den dönüşüm).

started_at_monotonic = engine_boot_at = clock() (boot anı) — Task 5'te
multi-device spawn için ortak referans olacak (spec § 3 Iter 3 + § 5).

Mevcut 73 test + 1 yeni run_device direkt çağrı testi yeşil.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: SIGINT/SIGTERM asyncio Pattern + Shutdown Event

`signal.signal` yerine `loop.add_signal_handler` ile shutdown event'i set edilir. Test edilebilir, asyncio-uyumlu temiz kapanma. Iter 2a/2b'nin `signal.signal` pattern'i Iter 3'te artık geçerli değil.

**Files:**
- Modify: `src/simulator/engine.py` (_amain içine signal handler ekle, KeyboardInterrupt fallback'i sadeleştir)
- Modify: `tests/unit/test_engine.py` (shutdown event testi ekle)

- [x] **Step 4.1: Failing test ekle — shutdown event tetiklendiğinde run_device temiz çıkar**

`tests/unit/test_engine.py` SONUNA:

```python
async def test_run_device_exits_when_shutdown_event_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """shutdown.set() çağrılınca run_device bir sonraki tick öncesinde çıkar."""
    import asyncio as _asyncio
    import random as _random

    from simulator.config import DeviceConfig, DeviceState, SensorConfig, StateDurations
    from simulator.engine import run_device
    from simulator.runtime import DeviceRuntimeState
    from simulator.sensors import SENSOR_REGISTRY

    sensor_cfgs = [
        SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1),
        SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2),
        SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0),
        SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5),
        SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0),
        SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01),
    ]
    sensors = [SENSOR_REGISTRY[sc.name](sc) for sc in sensor_cfgs]
    device = DeviceConfig(
        id="d1", type="telescopic_mast_v1", sensors=sensor_cfgs,
        state_durations=StateDurations(
            idle=(5.0, 5.0), raising=(10.0, 10.0),
            holding=(60.0, 60.0), lowering=(10.0, 10.0),
        ),
        target_height_mm=5000.0, seed=42,
    )
    rng = _random.Random(42)
    runtime = DeviceRuntimeState(
        state=DeviceState.IDLE, state_entered_at_monotonic=0.0,
        current_state_duration_s=rng.uniform(*device.state_durations.idle),
        position_mm=0.0, cycle_count=0, rng=rng,
        started_at_monotonic=0.0, clock=FakeClock(0.0),
    )
    publisher = MagicMock()

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    shutdown = _asyncio.Event()

    async def runner() -> None:
        await run_device(
            device=device, runtime=runtime, sensors=sensors,
            publisher=publisher, tick_interval=1.0,
            shutdown_event=shutdown, max_iterations=None,  # sonsuz, sadece shutdown ile bitsin
        )

    task = _asyncio.create_task(runner())
    # Birkaç tick geçsin
    await _asyncio.sleep(0)
    await _asyncio.sleep(0)
    shutdown.set()
    await _asyncio.wait_for(task, timeout=1.0)

    assert publisher.publish_reading.call_count > 0
```

- [x] **Step 4.2: Testi koş, FAIL gör (henüz shutdown handler eklenmedi ama run_device zaten event kontrol ediyor — bu test PASS olabilir)**

```bash
pytest tests/unit/test_engine.py::test_run_device_exits_when_shutdown_event_set -v
```
Sonuç: Eğer Task 3'teki run_device shutdown_event.is_set() kontrolünü doğru yapıyorsa bu test PASS olabilir. Sadece behaviour'u garantilemek için yazıldı; FAIL ederse run_device'da `while not shutdown_event.is_set():` döngüsünün doğru çalıştığını incele.

- [x] **Step 4.3: `engine.run()` içindeki `_amain`'e signal handler ekle**

Mevcut `_amain` gövdesini şununla değiştir:

```python
async def _amain() -> None:
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _set_shutdown(signum: int) -> None:
        logger.info("Shutdown sinyali alındı: {}", signum)
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _set_shutdown, sig)
        except NotImplementedError:
            # Windows asyncio signal handlers desteklemez; KeyboardInterrupt fallback'i bırak.
            logger.warning("add_signal_handler {} desteklenmiyor (Windows?)", sig)

    try:
        await run_device(
            device=device, runtime=runtime, sensors=sensors,
            publisher=publisher, tick_interval=tick_interval,
            shutdown_event=shutdown, max_iterations=max_iterations,
        )
    finally:
        publisher.close()
```

`signal` import'unu engine.py üst tarafına geri ekle (alfabetik: `import asyncio`'dan sonra, `random`'ın üstünde).

Mevcut `try: asyncio.run(_amain()) except KeyboardInterrupt: ...` bloğunu sadeleştir — KeyboardInterrupt artık signal handler tarafından yakalanacak, ama Windows fallback için satırı koru:

```python
asyncio.run(_amain())
```

(KeyboardInterrupt'ın asyncio.run'dan dışarı sızması Unix'te add_signal_handler sayesinde gerçekleşmez; Windows'ta KeyboardInterrupt _amain'in run_device awaiti içinde patlar → asyncio.run bunu CancelledError'a sarar ve publisher.close finally bloğu yine de çalışır. Yeterince temiz.)

- [x] **Step 4.4: Shutdown event testini tekrar koş, PASS olduğundan emin ol**

```bash
pytest tests/unit/test_engine.py::test_run_device_exits_when_shutdown_event_set -v
```
Beklenen: PASS.

- [x] **Step 4.5: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit
ruff check src/simulator tests/unit
```
Beklenen: 81 passed (80 + 1 yeni), mypy clean, ruff clean.

- [x] **Step 4.6: Manuel SIGINT testi**

```bash
mosquitto_sub -t 'telemetry/+/+' &
python -m simulator
```
3-4 saniye sonra Ctrl+C bas. Beklenen: "Shutdown sinyali alındı: 2" log, sonra "engine kapanıyor" benzeri, sonra temiz exit (0). Publisher disconnect olmuş olmalı.

- [x] **Step 4.7: Commit**

```bash
git add src/simulator/engine.py tests/unit/test_engine.py
git commit -m "$(cat <<'EOF'
feat(engine): asyncio add_signal_handler + shutdown Event pattern

SIGINT/SIGTERM artık loop.add_signal_handler ile asyncio.Event set ediyor;
run_device tick başında is_set() kontrol edip temiz çıkıyor. signal.signal
pattern'i tamamen kaldırıldı (Iter 2a/2b'nin blocking dünyası).

Windows fallback: NotImplementedError yakalanıyor (KeyboardInterrupt
asyncio.run tarafından sarmalanıyor, publisher.close finally'de çalışıyor).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: N Cihaz Paralel Spawn — `asyncio.gather(*tasks)`

Engine artık `devices[0]` yerine TÜM cihazları paralel task'lar halinde başlatır. Paylaşılan publisher, ortak `engine_boot_at`. `_validate_devices` zaten N cihazı kabul ediyor (Task 2).

**Files:**
- Modify: `src/simulator/engine.py` (single-device blok → loop + asyncio.gather)
- Create: `tests/fixtures/devices_multi.yaml` (2 cihaz, farklı seed)
- Modify: `tests/unit/test_engine.py` (multi-device test ekle)

- [x] **Step 5.1: `tests/fixtures/devices_multi.yaml` yarat**

```yaml
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [5, 5]
      raising:  [10, 10]
      holding:  [60, 60]
      lowering: [10, 10]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
  - id: device_002
    type: telescopic_mast_v1
    seed: 7
    target_height_mm: 5000
    state_durations:
      idle:     [5, 5]
      raising:  [10, 10]
      holding:  [60, 60]
      lowering: [10, 10]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
```

- [x] **Step 5.2: Failing test — 2 cihaz, her biri 6 sensör × N tick yayın yapar**

`tests/unit/test_engine.py` SONUNA ekle:

```python
def test_run_spawns_all_devices_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """2 cihaz fixture'ı: her cihaz 2 tick × 6 sensör = 12 publish, toplam 24."""
    import asyncio as _asyncio

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=2,
        seed=None,  # YAML'deki per-device seed kullan
        clock=clock,
    )

    # 2 cihaz × 2 tick × 6 sensör = 24 publish
    assert mock_publisher.publish_reading.call_count == 24

    # Her iki cihaz da yayın yaptı (device_id alanı kontrolü)
    device_ids = {c.kwargs["device_id"] for c in mock_publisher.publish_reading.call_args_list}
    assert device_ids == {"device_001", "device_002"}
```

- [x] **Step 5.3: Testi koş, FAIL gör (engine hâlâ tek cihaz çalıştırıyor)**

```bash
pytest tests/unit/test_engine.py::test_run_spawns_all_devices_in_parallel -v
```
Beklenen: FAIL — yalnızca device_001'in publish'leri var (12), 24 değil.

- [x] **Step 5.4: `engine.run()` içindeki single-device bloğunu multi-device loop'a çevir**

`engine.run()` içinde mevcut:
```python
_validate_devices(devices)
device = devices[0]  # Iter 3 ara durum

sensors: list[BaseSensor] = [
    SENSOR_REGISTRY[sc.name](sc) for sc in device.sensors
]

rng = random.Random(seed if seed is not None else device.seed)
engine_boot_at = clock()
initial_duration = rng.uniform(*device.state_durations.idle)
runtime = DeviceRuntimeState(...)
```

Bloğunu ŞUNUNLA DEĞİŞTİR:

```python
_validate_devices(devices)

engine_boot_at = clock()  # Tüm cihazlar için ortak referans (spec § 5)
tick_interval = 1.0 / engine_config.tick_hz

publisher = _make_publisher(mqtt_config)
publisher.connect()

# Her cihaz için: sensors + rng + runtime üret (cihazlar arasında shared state YOK).
# rng `runtime.rng` üzerinden taşınır — run_device içinde noise da oradan akar.
device_setups: list[tuple[DeviceConfig, DeviceRuntimeState, list[BaseSensor]]] = []
for device in devices:
    device_sensors: list[BaseSensor] = [
        SENSOR_REGISTRY[sc.name](sc) for sc in device.sensors
    ]
    effective_seed = seed if seed is not None else device.seed
    device_rng = random.Random(effective_seed)
    initial_duration = device_rng.uniform(*device.state_durations.idle)
    device_runtime = DeviceRuntimeState(
        state=DeviceState.IDLE,
        state_entered_at_monotonic=engine_boot_at,
        current_state_duration_s=initial_duration,
        position_mm=0.0,
        cycle_count=0,
        rng=device_rng,
        started_at_monotonic=engine_boot_at,
        clock=clock,
    )
    device_setups.append((device, device_runtime, device_sensors))
```

Sonra `_amain` içindeki tek-cihaz `await run_device(...)` çağrısını şununla değiştir:

```python
async def _amain() -> None:
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _set_shutdown(signum: int) -> None:
        logger.info("Shutdown sinyali alındı: {}", signum)
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _set_shutdown, sig)
        except NotImplementedError:
            logger.warning("add_signal_handler {} desteklenmiyor (Windows?)", sig)

    tasks = [
        asyncio.create_task(
            run_device(
                device=d, runtime=r, sensors=s, publisher=publisher,
                tick_interval=tick_interval,
                shutdown_event=shutdown, max_iterations=max_iterations,
            ),
            name=f"run_device:{d.id}",
        )
        for (d, r, s) in device_setups
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        publisher.close()
```

ÖNEMLİ: `publisher = _make_publisher(...); publisher.connect()` artık `_amain` ÖNCESİNDE (yukarıdaki blokta), bu zaten doğru — `_amain` closure üzerinden publisher'ı görür.

- [x] **Step 5.5: Multi-device testi koş, PASS gör**

```bash
pytest tests/unit/test_engine.py::test_run_spawns_all_devices_in_parallel -v
```
Beklenen: PASS.

- [x] **Step 5.6: Tüm engine testlerini koş — mevcut tek-cihaz testleri kırılmamalı**

```bash
pytest tests/unit/test_engine.py -v
```
Beklenen: tüm engine testleri PASS. `devices_minimal.yaml` hâlâ 1 cihaz içerir, multi-device kod path 1 cihazlı listede de doğru çalışır.

- [x] **Step 5.7: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit
ruff check src/simulator tests/unit
```
Beklenen: 82 passed, mypy clean, ruff clean.

- [x] **Step 5.8: Commit**

```bash
git add src/simulator/engine.py tests/fixtures/devices_multi.yaml tests/unit/test_engine.py
git commit -m "$(cat <<'EOF'
feat(engine): spawn N devices in parallel via asyncio.gather

engine.run() artık devices listesinin tamamını paralel asyncio task'ları
olarak başlatır. Her cihaz kendi DeviceRuntimeState + random.Random(seed) +
sensor instance listesine sahip; publisher ve engine_boot_at paylaşılır
(spec § 3 Iter 3 + § 5 invaryant: tüm cihazlar için ortak boot anı —
task scheduling jitter senaryo pencerelerini kaymasın diye).

devices_multi.yaml fixture: 2 cihaz, farklı seed, 6 sensör.
Test: 2 tick × 2 cihaz × 6 sensör = 24 publish çağrısı doğrulanır.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Aynı Seed Determinizm Regresyon Testi

Spec § 3 Iter 3 bitti kriteri #2: iki cihaz aynı seed + aynı state_durations + aynı tick sayısı → birebir aynı value dizileri. Bu test per-device RNG izolasyonunun garantisini doğrular.

**Files:**
- Create: `tests/fixtures/devices_same_seed.yaml`
- Modify: `tests/unit/test_engine.py` (regresyon testi ekle)

- [x] **Step 6.1: `tests/fixtures/devices_same_seed.yaml` yarat**

Task 5'teki `devices_multi.yaml`'ın AYNISI ama `device_002`'nin `seed: 7` yerine `seed: 42`:

```yaml
devices:
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [5, 5]
      raising:  [10, 10]
      holding:  [60, 60]
      lowering: [10, 10]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
  - id: device_002
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [5, 5]
      raising:  [10, 10]
      holding:  [60, 60]
      lowering: [10, 10]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
```

- [x] **Step 6.2: Regresyon testi yaz**

`tests/unit/test_engine.py` SONUNA ekle:

```python
def test_same_seed_devices_produce_identical_value_sequences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec § 3 Iter 3 bitti kriteri #2: aynı seed → birebir aynı value dizisi.

    Per-device RNG izolasyonu + ortak engine_boot_at garantisinin testidir.
    Eğer cihazlar shared RNG kullansaydı veya started_at_monotonic'ler kaymış
    olsaydı bu test FAIL ederdi.
    """
    import asyncio as _asyncio

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_same_seed.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=None,
        clock=clock,
    )

    # 2 cihaz × 3 tick × 6 sensör = 36 publish
    assert mock_publisher.publish_reading.call_count == 36

    # device_001 ve device_002'nin (sensor, tick_index) → value haritalarını çıkar
    by_device: dict[str, list[tuple[str, float]]] = {"device_001": [], "device_002": []}
    for call in mock_publisher.publish_reading.call_args_list:
        kw = call.kwargs
        by_device[kw["device_id"]].append((kw["sensor"], kw["value"]))

    # Aynı sensör sırası + aynı value'lar bekleniyor
    assert by_device["device_001"] == by_device["device_002"]


def test_different_seeds_produce_different_value_sequences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negatif kontrol: farklı seed → farklı value dizisi (devices_multi fixture)."""
    import asyncio as _asyncio

    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = _asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",  # seed 42 vs 7
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=None,
        clock=clock,
    )

    by_device: dict[str, list[tuple[str, float]]] = {"device_001": [], "device_002": []}
    for call in mock_publisher.publish_reading.call_args_list:
        kw = call.kwargs
        by_device[kw["device_id"]].append((kw["sensor"], kw["value"]))

    assert by_device["device_001"] != by_device["device_002"]
```

- [x] **Step 6.3: Testleri koş**

```bash
pytest tests/unit/test_engine.py::test_same_seed_devices_produce_identical_value_sequences \
       tests/unit/test_engine.py::test_different_seeds_produce_different_value_sequences -v
```
Beklenen: ikisi de PASS. Eğer same-seed testi FAIL ederse: muhtemelen Task 5'te `device_rng = random.Random(effective_seed)` her cihaz için ayrı oluşturulmadı — engine.py'yi gözden geçir.

- [x] **Step 6.4: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit
ruff check src/simulator tests/unit
```
Beklenen: 84 passed, mypy clean, ruff clean.

- [x] **Step 6.5: Commit**

```bash
git add tests/fixtures/devices_same_seed.yaml tests/unit/test_engine.py
git commit -m "$(cat <<'EOF'
test(engine): same-seed determinism regression + negative control

Spec § 3 Iter 3 bitti kriteri #2: iki cihaz aynı seed → birebir aynı
value dizisi. Per-device RNG izolasyonu + ortak engine_boot_at
garantisinin testi. Negatif kontrol: farklı seed → farklı diziler.

devices_same_seed.yaml fixture (2 cihaz, seed=42 vs seed=42).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Integration Test — 2 Cihaz Paralel Akış

Spec § 3 Iter 3 bitti kriteri #3: 2 cihaz spawn, simüle 10 sn boyunca her ikisinden de mesaj geldiği doğrulanır. `tests/integration/` altında yeni dosya. Paho mock kullanılır (gerçek broker smoke kategorisinde, bu task'ta YOK).

**Files:**
- Create: `tests/integration/__init__.py` (yoksa)
- Create: `tests/integration/test_multi_device_engine.py`

- [x] **Step 7.1: `tests/integration/__init__.py` yarat (boş dosya)**

```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

(Eğer zaten varsa Step atla — `ls tests/integration/__init__.py` ile kontrol et.)

- [x] **Step 7.2: Integration test dosyası yaz**

Create `tests/integration/test_multi_device_engine.py`:

```python
"""2 cihaz paralel integration testi (Iter 3 — spec § 3 bitti kriteri #3).

paho-mqtt mock kullanır; gerçek Mosquitto'ya karşı testler tests/smoke/ (CI dışı).
Simüle 10 saniye: asyncio.sleep no-op + FakeClock manuel advance.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from simulator.engine import run
from tests.unit.test_runtime import FakeClock

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_two_devices_produce_messages_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """devices_multi.yaml ile 2 cihaz, simüle 10 tick, her ikisinden de mesaj akmalı."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=10,
        seed=None,
        clock=clock,
    )

    # 2 cihaz × 10 tick × 6 sensör = 120 publish
    assert mock_publisher.publish_reading.call_count == 120

    # Her cihazdan tam 60 mesaj (10 tick × 6 sensör)
    device_msg_counts: dict[str, int] = {"device_001": 0, "device_002": 0}
    for call in mock_publisher.publish_reading.call_args_list:
        device_msg_counts[call.kwargs["device_id"]] += 1
    assert device_msg_counts == {"device_001": 60, "device_002": 60}


def test_two_devices_interleave_within_each_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Her tick'te iki cihaz da ilerlemeli (biri diğerini tamamen bitirmesin).

    Sonraki 6 publish'in (1 cihazın 1 tick'i) hep aynı device_id'den geldiği bir
    durum varsa ve 6'nın katı pozisyonlarda hep aynı cihaz ardışık geliyorsa
    asyncio task'ları doğru interleave etmiyor. asyncio.gather'ın doğal davranışı
    her await'te diğer task'a yield etmektir, bu zaten doğru — test bu invariantı
    regresyon olarak korur.
    """
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=None,
        clock=clock,
    )

    device_id_sequence = [
        c.kwargs["device_id"] for c in mock_publisher.publish_reading.call_args_list
    ]
    # Her iki cihaz da yayın yaptı
    assert set(device_id_sequence) == {"device_001", "device_002"}
    # Bir cihaz, diğeri başlamadan tüm tick'lerini bitirmedi:
    # device_001'in son indeksi device_002'nin ilk indeksinden ÖNCE geliyorsa serileşmiş demektir.
    first_d2 = device_id_sequence.index("device_002")
    last_d1 = len(device_id_sequence) - 1 - list(reversed(device_id_sequence)).index("device_001")
    assert first_d2 < last_d1, (
        "Cihazlar serileşmiş çalıştı (biri tamamen bittikten sonra diğeri başladı); "
        "asyncio.gather paralelizmi düzgün çalışmıyor."
    )


def test_topic_disambiguation_uses_device_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Her cihazın mesajları kendi device_id'sini taşır (spec § 7 topic şeması)."""
    mock_publisher = MagicMock()
    monkeypatch.setattr("simulator.engine._make_publisher", lambda c: mock_publisher)

    original_sleep = asyncio.sleep
    monkeypatch.setattr("simulator.engine.asyncio.sleep", lambda _s: original_sleep(0))

    clock = FakeClock(0.0)
    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_multi.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=1,
        seed=None,
        clock=clock,
    )

    # Her publish çağrısının device_id'si {device_001, device_002} kümesinde
    for call in mock_publisher.publish_reading.call_args_list:
        assert call.kwargs["device_id"] in {"device_001", "device_002"}
```

- [x] **Step 7.3: Integration testleri koş**

```bash
pytest tests/integration/test_multi_device_engine.py -v
```
Beklenen: 3 passed.

- [x] **Step 7.4: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration
ruff check src/simulator tests/unit tests/integration
```
Beklenen: 87 passed, mypy/ruff clean. (mypy ve ruff'a `tests/integration` da eklendi.)

- [x] **Step 7.5: Coverage kontrolü**

```bash
pytest tests/ --cov=src/simulator --cov-report=term-missing -q
```
Beklenen: ≥%80 coverage. Eğer altındaysa hangi engine satırları kapsanmamış incele.

- [x] **Step 7.6: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_multi_device_engine.py
git commit -m "$(cat <<'EOF'
test(integration): 2 device parallel run + interleaving + topic disambiguation

Spec § 3 Iter 3 bitti kriteri #3: 2 cihaz, simüle 10 sn (asyncio.sleep
no-op), her ikisinden de tam 60 mesaj. Interleaving testi: bir cihaz
diğeri başlamadan tüm tick'lerini bitirmiyor (asyncio.gather paralelizmi
regresyon koruyucusu). Topic disambiguation: her publish doğru device_id
taşır.

paho-mqtt mock'lanır; gerçek Mosquitto smoke kategorisinde (CI dışı).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `devices.yaml.example` Genişletme + Manuel Uçtan Uca Doğrulama + Milestone

3 cihazlı örnek config + mosquitto'ya karşı manuel doğrulama + CLAUDE.md "Mevcut Faz" güncellemesi + milestone commit. Bitti kriteri #1 (3 cihaz paralel) bu task'ta uçtan uca gözlenir.

**Files:**
- Modify: `config/devices.yaml.example`
- Modify: `CLAUDE.md` (Mevcut Faz bölümü)
- Modify: `docs/plans/2026-05-28-faz1-iterasyon3-asyncio-multi-device.md` (bu dosya — tamamlandı işaretleri)

- [x] **Step 8.1: `config/devices.yaml.example` 3 cihaza genişlet**

Mevcut tek cihaz config'i (Iter 2b sonu) ŞUNUNLA DEĞİŞTİR:

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

  - id: device_002
    type: telescopic_mast_v1
    seed: 7
    target_height_mm: 6000
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

  - id: device_003
    type: telescopic_mast_v1
    seed: 123
    target_height_mm: 4500
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

- [x] **Step 8.2: `config/devices.yaml` lokal kopyasını güncelle**

`config/devices.yaml` `.gitignore`'da olduğu için repo dışı. Manuel smoke için lokal kopyala:
```bash
cp config/devices.yaml.example config/devices.yaml
```
(Eğer mevcut bir lokal yaml'i overwrite ediyorsan onayını al.)

- [x] **Step 8.3: Manuel uçtan uca — mosquitto açık + python -m simulator**

İki ayrı terminal kullan.

Terminal A:
```bash
mosquitto_sub -v -t 'telemetry/+/+'
```
Bu, hem topic'i hem payload'ı gösterir.

Terminal B:
```bash
python -m simulator
```

Beklenen Terminal A çıktısı (saniyede 18 satır — 3 cihaz × 6 sensör):
```
telemetry/device_001/motor_current   {"device_id":"device_001","timestamp":"...","state":"idle","sensor":"motor_current","value":0.47,"unit":"A"}
telemetry/device_002/motor_current   {"device_id":"device_002","timestamp":"...","state":"idle","sensor":"motor_current","value":0.51,"unit":"A"}
telemetry/device_003/motor_current   {"device_id":"device_003","timestamp":"...","state":"idle","sensor":"motor_current","value":0.49,"unit":"A"}
...
```

10-15 saniye gözle. Beklenen davranışlar:
- 3 cihazın topic'leri DAİMA görünür (biri kaybolmaz)
- Her cihaz IDLE → RAISING geçişini bağımsız olarak yapar (state alanı zamanla değişir)
- `device_id` alanı topic'le tutarlı
- Ctrl+C → "Shutdown sinyali alındı: 2" log, temiz çıkış

EĞER bir cihaz yayın yapmıyorsa veya hata varsa: STOP, Task 5'e geri dön.

- [x] **Step 8.4: `CLAUDE.md` "Mevcut Faz" bölümünü güncelle**

`CLAUDE.md` içinde "## Mevcut Faz" başlığı altındaki:
```
**Faz 1 — Iterasyon 3: asyncio + Çoklu Cihaz** (sıradaki)
```
satırını şununla değiştir:
```
**Faz 1 — Iterasyon 4: Üç Arıza Senaryosu** (sıradaki)
```

"Iterasyon 3 (sıradaki) — Plan henüz yazılmadı" bölümünün TAMAMINI şununla değiştir:

```markdown
### Iterasyon 3 (asyncio + Çoklu Cihaz) — Tamamlandı (2026-05-28)

Engine asyncio loop'a geçti. `engine.run()` artık `asyncio.run(_amain(...))` çağırıyor;
`async def run_device(...)` per-cihaz task'ı. N cihaz `asyncio.gather(*tasks)` ile paralel.
Paylaşılan tek `MQTTPublisher`, ortak `engine_boot_at` (regresyon testi için). SIGINT/SIGTERM
`loop.add_signal_handler` + `asyncio.Event` ile yönetiliyor. `_validate_iteration2b_constraints`
→ `_validate_devices` rename + N cihaz desteği (unique ID, same-seed WARN, her cihaz tam 6
sensör). `pytest-asyncio==0.23.7` dev dep, auto-mode. Toplam ~87 test (71 Iter 2b + ~16 yeni
asyncio/validation/integration). Manuel uçtan uca: 3 cihaz paralel akıyor, topic
disambiguation doğru, SIGINT temiz shutdown.

### Iterasyon 4 (sıradaki) — Plan henüz yazılmadı

Kapsam (spec § 3 Iterasyon 4): MechanicalWear / HydraulicLeak / ElectricalFault
senaryoları + istatistiksel imza testleri (`scipy.stats`).
```

- [x] **Step 8.5: Bu plan dosyasının tüm checkbox'larını `[x]` yap**

`docs/plans/2026-05-28-faz1-iterasyon3-asyncio-multi-device.md` dosyasındaki tüm `- [ ]` ifadelerini `- [x]` yap (sed veya manuel editör — global replace). Plan dosyası bir milestone artifact'i; tamamlanmış bir iterasyonun progres izi olarak repo'da kalır.

- [x] **Step 8.6: Tam suite son kez**

```bash
pytest tests/ -q
mypy src/simulator tests/unit tests/integration
ruff check src/simulator tests/unit tests/integration
```
Beklenen: 87 passed, mypy/ruff clean.

- [x] **Step 8.7: Milestone commit**

```bash
git add config/devices.yaml.example CLAUDE.md docs/plans/2026-05-28-faz1-iterasyon3-asyncio-multi-device.md
git commit -m "$(cat <<'EOF'
milestone: Faz 1 Iterasyon 3 (asyncio + çoklu cihaz) tamamlandı 🎉

3 cihaz paralel akıyor (config/devices.yaml.example genişletildi).
CLAUDE.md Mevcut Faz güncellendi: Iter 4 (3 arıza senaryosu) sıradaki.
Iter 3 plan dosyası tüm checkbox'larıyla milestone artifact'i olarak kaldı.

Bitti kriterleri (spec § 3 Iter 3):
1. ✅ 3 cihaz YAML, paralel akış (manuel smoke onaylı)
2. ✅ Aynı seed → birebir aynı value (test_same_seed_devices_produce_identical_value_sequences)
3. ✅ 2 cihaz integration test, simüle 10 sn (test_two_devices_produce_messages_concurrently)
4. ✅ 71 mevcut + ~16 yeni unit test yeşil, coverage ≥%80

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Iter 3 Sonu — Bitti Kriterleri (spec § 3 ile birebir)

- [x] **Kriter 1:** `config/devices.yaml.example` 3 cihaz içeriyor, üçü de paralel akıyor (Task 8.3 manuel smoke).
- [x] **Kriter 2:** Aynı seed iki cihaz → birebir aynı value dizisi (Task 6).
- [x] **Kriter 3:** 2 cihaz integration test, simüle 10 sn (Task 7).
- [x] **Kriter 4:** 71 Iter 2b testi yeşil + yeni asyncio engine testleri (Task 1-7 boyunca).

Her task'ın sonunda DiscIPLİN (CLAUDE.md kuralı): tam pytest suite + mypy(src+tests) + ruff(src+tests) yeşil — per-file değil.

---

## Memory Güncellemesi (Iter 3 sonu, plan-dışı)

Iter 3 tamamlandıktan sonra `project_active_phase.md` memory'sini güncelle:
- `Active phase` → "Faz 1 — Iterasyon 4: 3 fault scenarios (next, plan not yet written)"
- Iteration plan satırı → Iter 3 ✅ DONE işareti
- "Iter 3 design questions to settle in brainstorming" bloğunu KALDIR (kararlar verildi, spec'te)

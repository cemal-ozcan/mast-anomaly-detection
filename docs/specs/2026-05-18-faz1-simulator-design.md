# Faz 1 — Simulator Tasarım Dokümanı

**Tarih:** 2026-05-18
**Durum:** Onaylanmış tasarım — implementasyon planı hazırlanacak
**Faz referansı:** `docs/ROADMAP.md` § Faz 1
**Domain referansı:** `docs/DOMAIN.md`
**Mimari referansı:** `docs/ARCHITECTURE.md`

Bu doküman Faz 1 (Simulator) boyunca tek hakemdir. İmplementasyonda bir karar belirsizleşirse önce buraya bakılır; spec ile çelişen kod kabul edilmez. Spec değişirse önce bu doküman güncellenir, sonra kod.

---

## 1. Amaç ve Kapsam

Endüstriyel teleskopik mast cihazlarının sentetik telemetri verisini üreten, MQTT üzerinden yayınlayan ve içine kontrollü arıza senaryoları enjekte edilebilen bir Python servisi tasarlamak.

**Kapsam içi:**
- Tek cihaz tipi (`telescopic_mast_v1`)
- 6 sensör (motor_current, motor_voltage, hydraulic_pressure, motor_temperature, mast_position, vibration)
- Normal çalışma döngüsü: IDLE → RAISING → HOLDING → LOWERING → IDLE
- 3 arıza senaryosu: mekanik aşınma (A), hidrolik kaçak (B), elektriksel bağlantı (C)
- YAML config'den cihaz/sensör/senaryo tanımları
- Çoklu cihaz desteği (N cihaz paralel)
- 1 Hz yayın frekansı
- Per-cihaz deterministik RNG (seed)
- pytest test paketi (%80+ kapsama)

**Kapsam dışı (Faz 1):**
- Gerçek broker'a karşı integration testleri (smoke kategorisinde, CI dışı)
- Sensör başına farklı frekans
- LLM/ML/RAG (CLAUDE.md kalıcı kapsam dışı)
- Cihaza komut gönderme (CLAUDE.md "gözlem modu" kuralı)
- Dashboard/depolama (Faz 2-3)

---

## 2. Kuzey Yıldızı ve Tasarım Disiplini

CLAUDE.md prensibi: *"Çalışan, anlaşılır, küçük bir parça; çalışmayan büyük bir sistemden her zaman daha değerlidir."*

Faz 1 bu prensibe **walking skeleton + iterasyon** modelinde uyar. Her iterasyon kendi başına çalışır ve test edilir; sonraki iterasyona ancak kullanıcı onayı ile geçilir. Sona kalmış test borcu birikmesin diye testler her iterasyonun parçasıdır (CLAUDE.md "her özellikle paralel test").

---

## 3. İterasyon Planı ve Kabul Kriterleri

### Iterasyon 1 — Walking Skeleton

**Kapsam:**
- Tek sensör sınıfı: `MotorCurrentSensor` (sabit IDLE baseline + Gauss gürültü, state machine yok)
- `MQTTPublisher` paho-mqtt wrapper'ı
- `engine.py` 1 Hz blocking loop, tek cihaz (henüz Device wrapper sınıfı yok — engine doğrudan sensör + publisher'ı yönetir)
- `__main__.py` entry point (`python -m simulator`)
- Minimum YAML config: broker bilgisi + tek cihaz + tek sensör

İterasyon 1 henüz `DeviceRuntimeState` veya state machine içermez. Bunlar Iterasyon 2'de eklenir.

**Bitti kriterleri:**
1. `python -m simulator` çalışır, çökmez.
2. `mosquitto_sub -t telemetry/+/motor_current` ile mesajlar görülür.
3. Mesaj formatı § 7'deki JSON şemasına uyar.
4. `tests/unit/test_motor_current_sensor.py` ve `tests/unit/test_mqtt_publisher.py` yeşil.

### Iterasyon 2 — Tüm Sensörler + State Machine

**Kapsam:**
- 6 sensör hepsi (§ 6 tablo)
- `DeviceState` enum (IDLE/RAISING/HOLDING/LOWERING)
- `DeviceRuntimeState` mutable runtime modeli (§ 5)
- `compute_position()` ve state transition algoritması
- Sensörlerin durum başına davranış formülleri (DOMAIN.md referanslı)
- Sensörler arası **implicit korelasyon** (state ortak girdi)

**Bitti kriterleri (ölçülebilir, DOMAIN.md referanslı):**
1. IDLE durumunda 10 ardışık tick'in ≥9'unda `motor_current ∈ [0, 1] A` (DOMAIN.md sat. 58).
2. RAISING kararlı kısmında `motor_current ∈ [5, 15] A` (DOMAIN.md sat. 58).
3. RAISING başlangıcının ilk 2 saniyesinde `hydraulic_pressure ≥ 100 bar` (DOMAIN.md sat. 60).
4. HOLDING durumunda `mast_position` `target_height_mm ± 1 mm` aralığında sabit.
5. Tam bir IDLE→RAISING→HOLDING→LOWERING→IDLE döngüsü 85-450 saniye arasında tamamlanır (§ 5 state süre tablosuna göre).
6. Test paketi: her sensör için durum-başına davranış testi + state machine transition testi (`tests/unit/`).

### Iterasyon 3 — Çoklu Cihaz Desteği

**Kapsam:**
- Engine asyncio loop'a geçer
- Her cihaz `async def run_device(...)` task'ı, paralel
- Her cihazın kendi `DeviceRuntimeState` ve `random.Random(seed)` instance'ı
- YAML'de N cihaz tanımlanabilir
- **Paylaşılan tek `MQTTPublisher` instance** — per-device değil. Gerekçe: `paho.mqtt.client.publish()` thread-safe, kendi network loop'una sıraya alır; N cihaz için N TCP bağlantısı kaynak israfıdır ve Faz 2 ingestion zaten tek subscriber olarak okuyacak.
- **Cihaz ID disiplini:** `device.id` değerleri unique olmalı (aynı topic'e iki yayıncı çakışmasın). Birden fazla cihazda aynı `seed` varsa engine boot'ta WARN log basar, hata değil — § 3 Iter 3 bitti kriteri #2 (deterministik regresyon) bu durumu meşru kullanım olarak içerir.
- **Validation refactor:** `_validate_iteration2b_constraints` → `_validate_devices`. Cihaz sayısı ≥1, her cihaz tam 6-sensör seti (§ 6 disiplini Faz 1 boyunca mutlak), ID'ler unique. Iter 2b'nin "tam 1 cihaz" katı kuralı düşer.
- **Shutdown:** `loop.add_signal_handler(SIGINT|SIGTERM, shutdown.set)` + `asyncio.Event`. Her `run_device` döngüsü tick başında `shutdown.is_set()` kontrol eder; engine `await asyncio.gather(*tasks)` sonrası `publisher.close()` çağırır. § 11 satırı zaten bu yöne işaret ediyordu, Iter 3 implementasyonu somutlaştırır.
- **`started_at_monotonic` ortak referans:** Tüm cihazlar için `started_at_monotonic = engine_boot_at` (engine'in tüm cihazları spawn etmeden önce bir kez okuduğu `clock()` snapshot'ı). Her cihaz kendi asyncio task'ında ayrı `clock()` çağırmaz — yoksa task scheduling jitter'ı `device_elapsed_s`'i kayar, bitti kriteri #2'nin (aynı seed → birebir aynı value) regresyon testi geçmez. § 5 `started_at_monotonic` semantiği Iter 3'te "cihaz spawn anı" yerine "engine boot anı" olarak okunur; per-cihaz başlangıç ofseti gerekirse Faz 9+ YAML alanıyla eklenir (şu an YAGNI).

**Bitti kriterleri:**
1. YAML'de 3 cihaz tanımlanır, üçü de bağımsız topic'lere (`telemetry/{device_id}/...`) yayın yapar; mesajlar paralel akar (tek cihazın gecikmesi diğerlerini bloklamaz).
2. İki cihaz aynı seed + aynı state_durations + aynı tick sayısı ile çalıştırılınca yayınlanan `value` dizileri birebir aynı (regresyon testi — per-device RNG izolasyonu garantisinin doğrulaması).
3. Integration test: 2 cihaz spawn, simüle 10 saniye (`asyncio.sleep` no-op'lanır, gerçek wall-clock değil) boyunca her ikisinden de mesaj geldiği doğrulanır (`tests/integration/`).
4. `tests/unit/` mevcut 71 test yeşil kalır + yeni asyncio engine testleri eklenir. Toplam kapsama ≥%80.

**Integration test broker stratejisi:** paho-mqtt mock kullanılır — gerçek Mosquitto'ya karşı testler ayrı bir **smoke** kategorisindedir, CI'da çalışmaz, sadece lokal/manuel. Gerekçe: Faz 1'in test odağı simulator'ın mesaj üretimi; gerçek broker davranışı Faz 2 (ingestion) sorumluluğu. Network bağımlılığı CI flakiness yaratır.

### Iterasyon 4 — Üç Arıza Senaryosu

İterasyon 2'nin 2a/2b'ye bölünmesindeki pattern burada da uygulanır: önce altyapı + 1 senaryo (4a), sonra kalan 2 senaryo + istatistiksel test seti (4b). Plan ayrı dosyalarda yazılır, her biri kendi onay döngüsünden geçer.

#### Iterasyon 4a — Senaryo Altyapısı + MechanicalWear

**Kapsam:**
- `config.py`: `ScenarioWindow` dataclass + `DeviceConfig.scenarios: list[ScenarioWindow]` field + YAML loader scenarios bloğunu okur
- `src/simulator/scenarios/` package: `base.py` (`FaultScenario` ABC + `ScenarioContext`), `__init__.py` (`SCENARIO_REGISTRY` + `active_scenarios_at` helper — § 8)
- `MechanicalWear` (A) senaryosu (§ 9 A formülü)
- `engine.run_device` compute order'ına `fault.modify` entegrasyonu: clean → modify (per-active-scenario) → noise (§ 8 kritik fiziksel sıra)
- Per-senaryo state filtering: senaryonun `modify` metodu başında inline `if runtime.state not in active_states: return clean_value` (kapsüllü, engine sade)
- Params validation: `FaultScenario.__init__(self, params)` içinde required key check → eksikse boot-time `ValueError` (§ 11 early-exit)
- Unit testler: `tests/unit/test_scenarios/test_mechanical_wear.py` (sabit girdi → modify çıktısı), `test_config.py` ScenarioWindow validation, engine integration test (`tests/unit/test_engine_*.py` — fault.modify gerçekten çağrılıyor)
- **Bitti kriteri (4a):** MechanicalWear için 1 istatistiksel imza testi (`tests/scenarios/test_mechanical_wear_signature.py`): RAISING durumunda `motor_current` ortalaması baseline'a göre +%15..+%30, t-testi p<0.05. Spec § 12 senaryo imza testleri tablosu A.

#### Iterasyon 4b — HydraulicLeak + ElectricalFault + Tam İmza Seti

**Kapsam:**
- `HydraulicLeak` (B) senaryosu (§ 9 B)
- `ElectricalFault` (C) senaryosu (§ 9 C)
- Unit testler her senaryo için (per-state modify behavior)
- İstatistiksel imza testleri (`tests/scenarios/`): B (Spearman ρ<0, p<0.05) + C (F-testi p<0.05)
- `requirements.txt`'ye `scipy==1.17.1` explicit pin (scikit-learn 1.5.0'ın transitif getirdiği versiyon ile hizalı; tests/scenarios içinde `scipy.stats.ttest_1samp`, `spearmanr`, `f.cdf` kullanılır)
- devices.yaml.example genişlet: en az 1 cihazda `scenarios:` bloğu (manuel smoke için)
- Milestone commit + CLAUDE.md "Mevcut Faz" güncellemesi (Faz 1 tamamlandı → Faz 2 sıradaki)

**Iter 4 birleşik bitti kriterleri (istatistiksel imza testleri):**
1. **A (mekanik aşınma)**: Scenario aktif + ramp_up_s sonrasında, 60+ örnek üzerinde RAISING durumundaki `motor_current` ortalaması baseline'a göre %15-30 yüksek. Tek örnek t-testi p<0.05. (Iter 4a)
2. **B (hidrolik kaçak)**: HOLDING penceresinde 60+ örnek üzerinde `hydraulic_pressure` zaman serisine lineer regresyon: eğim negatif ve Spearman korelasyon p<0.05. (Iter 4b)
3. **C (elektriksel)**: Scenario aktif iken `motor_voltage` standart sapması baseline'ın 3 katı (F-testi p<0.05). (Iter 4b)
4. Her senaryo için unit test (`tests/unit/test_scenarios/`): sabit girdi → beklenen modifikasyon. (Iter 4a + 4b)

---

## 4. Mimari ve Dosya Düzeni

Yaklaşım A onaylandı: bileşen ayrımlı, asyncio. Plugin registry (Yaklaşım C) reddedildi — YAGNI. Monolitik (Yaklaşım B) reddedildi — sorumluluk dağılımı bozulur.

```
src/simulator/
├── __main__.py           # python -m simulator entry
├── config.py             # YAML yükleyici → DeviceConfig, MQTTConfig, EngineConfig
├── runtime.py            # DeviceRuntimeState, advance(), compute_position()
├── engine.py             # asyncio loop, cihaz orkestrasyonu
├── publisher.py          # MQTTPublisher (paho-mqtt wrapper)
├── sensors/
│   ├── __init__.py       # SENSOR_REGISTRY: dict[str, type[BaseSensor]]
│   ├── base.py           # BaseSensor ABC
│   ├── motor_current.py
│   ├── motor_voltage.py
│   ├── hydraulic_pressure.py
│   ├── motor_temperature.py
│   ├── mast_position.py
│   └── vibration.py
└── scenarios/
    ├── __init__.py       # SCENARIO_REGISTRY: dict[str, type[FaultScenario]]
    ├── base.py           # FaultScenario ABC + ScenarioContext
    ├── mechanical_wear.py
    ├── hydraulic_leak.py
    └── electrical_fault.py
```

`SENSOR_REGISTRY` ve `SCENARIO_REGISTRY` decorator/runtime keşif değil — YAML'deki ad-string'ini sınıfa eşleyen düz `dict`. Yeni sensör eklemek dosya açıp dict'e bir satır eklemek demektir; daha fazla indirection yok.

---

## 5. Veri Modelleri

### Immutable Config (YAML'den okunur)

```python
from enum import StrEnum  # Python 3.11+ resmi pattern; str mixin + auto value

class DeviceState(StrEnum):
    IDLE = "idle"
    RAISING = "raising"
    HOLDING = "holding"
    LOWERING = "lowering"

@dataclass(frozen=True)
class SensorConfig:
    name: str
    unit: str
    baseline: float       # IDLE baseline; durum başına davranış sensör sınıfında
    noise_std: float

@dataclass(frozen=True)
class StateDurations:
    idle: tuple[float, float]      # [min_s, max_s]
    raising: tuple[float, float]
    holding: tuple[float, float]
    lowering: tuple[float, float]

@dataclass(frozen=True)
class ScenarioWindow:
    name: str                                # registry key
    start_after_s: float
    duration_s: float
    params: Mapping[str, float] = field(default_factory=dict)

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

### Mutable Runtime

```python
from collections.abc import Callable
from dataclasses import dataclass, field
import time

@dataclass
class DeviceRuntimeState:
    state: DeviceState
    state_entered_at_monotonic: float       # clock() snapshot
    current_state_duration_s: float          # KRİTİK: transition'da BİR KEZ seçilir
    position_mm: float
    cycle_count: int
    rng: random.Random                       # per-device, seed'li
    started_at_monotonic: float              # cihaz engine'de spawn edildiği an
    clock: Callable[[], float] = field(default=time.monotonic)  # test edilebilirlik (DI)

    @property
    def elapsed_in_state_s(self) -> float:
        return self.clock() - self.state_entered_at_monotonic

    @property
    def device_elapsed_s(self) -> float:
        """Cihaz spawn olduğundan beri geçen toplam süre — senaryo pencereleri için."""
        return self.clock() - self.started_at_monotonic
```

**Clock DI gerekçesi:** State geçişleri zamana bağlı; testler `clock=FakeClock(0)` ile deterministik kontrol sağlar. Production'da default `time.monotonic` — wall clock değişikliklerinden bağımsız. Bu pattern monkeypatch sihrinden temiz: dependency açıkça görünür, mocklama explicit. Üretim kodu test paketinden import yapmaz; `FakeClock` `tests/unit/test_runtime.py` içinde tanımlı.

### Çıktı

```python
@dataclass(frozen=True)
class TelemetryReading:
    device_id: str
    timestamp_utc: datetime
    state: DeviceState
    sensor: str
    value: float
    unit: str
```

### Sensör Sözleşmesi

```python
class BaseSensor(ABC):
    config: SensorConfig

    def __init__(self, config: SensorConfig):
        self.config = config

    @abstractmethod
    def compute(self, runtime: DeviceRuntimeState, position_mm: float) -> float:
        """
        Bu sensör için bu tick'teki TEMİZ (arızasız, gürültüsüz) değer.

        Sensör instance'ı internal state tutabilir (örn. motor_temperature
        son sıcaklığı saklar). Sözleşme: aynı sensör instance'ı + aynı
        runtime tick sırası → aynı çıktı sırası (deterministik). RNG yok.
        """
```

**Stateful sensör notu:** `motor_temperature` lineer ısınma/soğuma için önceki tick'in değerine ihtiyaç duyar — instance attribute olarak son değerini saklar. Diğer 5 sensör stateless (sadece `runtime` + `position_mm`'den hesaplar). Test edilebilirlik korunur çünkü her testte yeni sensör instance'ı oluşturulur, başlangıç state'i belirlidir.

**Tick interval varsayımı (Iterasyon 2b kararı):** Stateful sensörler `delta_per_tick = 1.0 s` sabit varsayımıyla yazılır (engine `tick_hz=1.0` ile uyumlu). Sensör compute() çağrısı başına 1 saniyelik fiziksel zaman geçtiği varsayılır. Engine farklı `tick_hz` ile çalıştırılırsa stateful sensörlerin ısınma hızı orantısız olur. Iterasyon 4'te scenario timing gerektiğinde `BaseSensor.compute()` sözleşmesine `dt: float` parametresi eklenir veya engine'den `tick_interval` sensora inject edilir.

### Kritik İnvaryantlar

1. **`current_state_duration_s` sadece state transition anında seçilir** ve o durum süresince değişmez. Sensörler ve `compute_position()` bu sabit değeri runtime state'ten okur, kendileri rastgele seçmez. Aksi halde her tick yeni bir doğrusal denklem → kaos.
2. **`runtime.clock()` kullanılır** (default `time.monotonic`), `time.time()` değil. Wall clock değişiklikleri (NTP, manuel saat ayarı) elapsed hesabını bozmaz. Test'lerde `clock=FakeClock(0)` inject edilir.
3. **Per-device RNG**: Cihazlar birbirinin rastgelelik durumunu etkilemez. Aynı seed ile aynı çıktı → regresyon testleri mümkün.
4. **State geçişi tek yönlü**: IDLE → RAISING → HOLDING → LOWERING → IDLE.
5. **Sensor instance state**: Stateful sensörlerin (örn. `motor_temperature._current_temp_c`) instance attribute'ları cihazın yaşam süresi boyunca taşınır; state machine transition'ları reset etmez. Test'lerde her test fresh sensor instance oluşturur, böylece başlangıç state'i belirli kalır.

### State Süre Aralıkları (default, YAML override edilebilir)

| State | Min (s) | Max (s) | Gerekçe |
|---|---|---|---|
| IDLE | 5 | 30 | Rastgele bekleme süresi |
| RAISING | 10 | 60 | DOMAIN.md sat. 152 "10-60 saniye" |
| HOLDING | 60 | 300 | DOMAIN.md "uzun süreli" → demo için sıkıştırılmış |
| LOWERING | 10 | 60 | RAISING ile simetrik |

Toplam döngü: 85-450 saniye.

---

## 6. Sensör Tablosu

**Yapılandırma kuralı:** YAML `devices.yaml` içindeki `baseline` alanı **yalnızca IDLE durumu** içindir. Diğer durumlardaki davranış (RAISING'de inrush + kararlı akım, HOLDING'de tutucu basınç, vb.) sensör sınıfının kendi `compute()` metodunda kodlanır, config'den okunmaz. Gerekçe: bu değerler fiziksel formüllerin parçasıdır (örn. inrush 5-10× nominal), tek skaler olarak config'de temsil edilemez. Sensör genişletmek isteyen biri yeni sınıf yazar, parametre matrisini şişirmez (YAGNI). Aşağıdaki tablodaki RAISING/HOLDING değerleri DOMAIN.md aralıklarından seçilmiş ve sensör sınıflarında sabit-kodlanacak değerlerdir.

| Sensör | Birim | IDLE baseline | RAISING kararlı | HOLDING | Gürültü std | DOMAIN ref |
|---|---|---|---|---|---|---|
| motor_current | A | 0.5 | 8.0 (5-15 aralığı) | 0.5 | 0.1 | sat. 58 |
| ↳ LOWERING için | A | — | 8.0 (RAISING ile aynı kategori — DOMAIN.md "hareket halinde 5-15A" hem RAISING hem LOWERING'i kapsar) | — | — | sat. 58 |
| motor_voltage | V | 24.0 | 24.0 | 24.0 | 0.2 | sat. 21 |
| hydraulic_pressure | bar | 10 (5-20) | 150 (100-200) | 80 (50-150) | 2 | sat. 60 |
| ↳ LOWERING için | bar | — | 80 (HOLDING ile aynı kategori — motor enerjili tutucu basınç) | — | — | sat. 60 |
| motor_temperature | °C | 25 (çevre) | motor enerjili durumlarda (RAISING, HOLDING, LOWERING) lineer artış 0.08 °C/s, üst sınır 35 | IDLE'da lineer azalış 0.04 °C/s, alt sınır 25 | 0.5 | sat. 67 |
| mast_position | mm | 0 | 0 → target lineer | target | 1 | sat. 63 |
| vibration | g | 0.05 | 0.3 (0.1-0.5 RMS) | 0.05 | 0.01 | sat. 64 |
| ↳ LOWERING için | g | — | 0.3 (RAISING ile aynı kategori — motor enerjili hareket) | — | — | sat. 64 |

Tüm değerler DOMAIN.md aralıklarının içinde. Her sensör kendi `compute(runtime, position)` metodunda state'e göre baseline'ı seçer ve geçiş anlarında yumuşatma yapar (örn. RAISING'in ilk saniyesinde inrush peak).

---

## 7. MQTT Şeması

**Topic:** `telemetry/{device_id}/{sensor_name}`
Örnek: `telemetry/device_001/motor_current`

**Payload (JSON):**
```json
{
  "device_id": "device_001",
  "timestamp": "2026-05-18T15:30:00.123Z",
  "state": "raising",
  "sensor": "motor_current",
  "value": 8.7,
  "unit": "A"
}
```

**Timestamp üretim kuralı (tek doğru biçim):**

```python
def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
```

Format: `YYYY-MM-DDTHH:MM:SS.sssZ` (UTC, ISO 8601, milisaniye çözünürlüklü, `Z` suffix). Bu fonksiyon `publisher.py` veya `engine.py` içinde tek bir yerde tanımlanır ve her yerden o çağrılır — duplikasyon yok. Faz 2 (ingestion) ve Faz 3 (dashboard) bu formatı parse eder.

**QoS:** 1 (en az bir kez teslim) — mqtt.yaml.example'da zaten tanımlı.

**Topic seçim gerekçesi:** Per-sensör topic, endüstriyel MQTT IoT standardı. Debug ergonomisi yüksek (`mosquitto_sub -t telemetry/+/motor_current`). Per-sensör dedektörler temiz subscribe yapar. Çok-değişkenli analiz storage katmanından okunarak yapılır — MQTT'nin işi değil. Bu tercihin alternatifi (`telemetry/{device_id}` + sensor dict payload) reddedildi.

---

## 8. Tick Akışı ve Hesaplama Sırası

Her saniye, her cihaz için:

```
1. asyncio.sleep(1.0 / tick_hz)
2. _advance_state_machine(runtime, device_config.state_durations)
3. runtime.position_mm = compute_position(runtime, device_config.target_height_mm)
4. device_t = runtime.device_elapsed_s
5. active_windows = active_scenarios_at(device_config.scenarios, device_t)
6. for sensor in sensors:
       clean = sensor.compute(runtime, runtime.position_mm)
       for scenario, window in active_windows:
           ctx = ScenarioContext(
               runtime=runtime,
               scenario_elapsed_s=device_t - window.start_after_s,
           )
           clean = scenario.modify(sensor.name, clean, ctx)
       noisy = clean + runtime.rng.gauss(0, sensor.config.noise_std)
       reading = TelemetryReading(...)
       publisher.publish(reading)
```

`active_scenarios_at()` — `scenarios/__init__.py` içinde tanımlı saf bir helper fonksiyon. İmza:

```python
def active_scenarios_at(
    windows: list[ScenarioWindow],
    device_elapsed_s: float,
) -> list[tuple[FaultScenario, ScenarioWindow]]:
    """device_elapsed_s anında aktif olan (start_after_s ≤ t < start_after_s+duration_s)
    senaryoları döndürür. Ayrı bir Scheduler sınıfı yok — durum tutmayan bir fonksiyon yeterli."""
```

**Kritik:** `ScenarioContext` her senaryo için ayrı oluşturulur — `scenario_elapsed_s` her senaryonun kendi `start_after_s`'inden ölçülür. Birden fazla senaryo aynı anda aktif olabilir (örn. mechanical_wear 0-3600s + hydraulic_leak 60-660s); her birinin kendi geçen süresi vardır, tek bir paylaşılan değer kullanılamaz.

**Hesaplama sıralaması — kritik fiziksel sıra:**
1. **Temiz fiziksel değer** (sensör formülü)
2. **Arıza modifikasyonu** (FaultScenario.modify)
3. **Ölçüm gürültüsü** (Gauss, en son)

Bu sıra gerçek dünyayı yansıtır: arıza fiziksel olayı değiştirir, sensör onu okurken üzerine kendi gürültüsünü ekler. Faz 4 dedektörleri bu fiziksel modeli varsayar.

**Çoklu cihaz (Iterasyon 3+):** Yukarıdaki tick döngüsü her cihaz için bağımsız bir `async def run_device(device, runtime, sensors, publisher, shutdown, ...)` task'ında koşar. Cihazlar arasında shared state yok: her cihazın kendi `DeviceRuntimeState` instance'ı, kendi `random.Random(seed)`, kendi sensor instance listesi vardır. `MQTTPublisher` paylaşılır (§ 3 Iter 3 gerekçesi). `publisher.publish_reading(...)` sync metoddur ama `paho.client.publish()` çağrısı non-blocking (internal kuyruğa atar, paho'nun network thread'i yazar) — asyncio event loop'u bloklamaz, async dönüşüm gerekmez.

---

## 9. Arıza Senaryoları

### Sözleşme

```python
class FaultScenario(ABC):
    name: ClassVar[str]                  # registry key

    def __init__(self, params: Mapping[str, float]):
        self.params = params

    @abstractmethod
    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        ...

@dataclass(frozen=True)
class ScenarioContext:
    runtime: DeviceRuntimeState
    scenario_elapsed_s: float            # senaryonun başlamasından geçen süre
```

### Parametre Kalıbı

YAML'de:
```yaml
scenarios:
  - name: hydraulic_leak
    start_after_s: 60
    duration_s: 600
    params:
      leak_rate_bar_per_min: 5.0         # yavaş; 50.0 → hızlı kaçak
      position_sag_mm: 2.0
```

Aynı senaryo kodu farklı parametrelerle "yavaş veya hızlı kaçak" üretir. DOMAIN.md sat. 90 kaçağın "saatler/günler" sürdüğünü söylüyor; simülatörde sıkıştırılmış zaman ölçeği parametre üzerinden ayarlanır.

### A — MechanicalWear (DOMAIN.md sat. 78-83)

```
factor = min(1.0, ctx.scenario_elapsed_s / ramp_up_s) * severity

motor_current      → clean * (1 + factor)              # +%15 ... +%30
mast_position      → clean / (1 + factor * 0.7)         # yavaş yükseliş
vibration          → clean * (1 + factor * 2)
motor_temperature  → clean + factor * 8.0               # max +severity*8 °C
```

Sadece RAISING ve HOLDING'de aktif (IDLE'da motor dönmez → aşınma görünmez).

**Tipik params:** `severity=0.20`, `ramp_up_s=300`.

### B — HydraulicLeak (DOMAIN.md sat. 90-93)

```
if runtime.state == HOLDING:
    held_minutes = runtime.elapsed_in_state_s / 60   # HOLDING'e girişten beri
    pressure_drop = leak_rate_bar_per_min * held_minutes
    hydraulic_pressure → max(5.0, clean - pressure_drop)
    mast_position      → clean - position_sag_mm * held_minutes
```

Kavram tek adla anılır: `runtime.elapsed_in_state_s`. `state == HOLDING` filtresi altında bu değer "HOLDING'e girişten beri geçen süre" anlamına gelir; ayrı bir `elapsed_in_holding_s` adı tanımlanmaz.

RAISING'de pompa basıncı zaten yüksek tutuyor — kaçak görünmez. LOWERING'de basınç zaten düşüyor — modifiye yok.

**Tipik params:** `leak_rate_bar_per_min=5.0`, `position_sag_mm=2.0`.

### C — ElectricalFault (DOMAIN.md sat. 102-106)

```
if runtime.rng.random() < spike_prob:
    motor_current → clean + runtime.rng.uniform(-2, 4)
    motor_voltage → clean + runtime.rng.uniform(-30, 30)
else:
    motor_voltage → clean + runtime.rng.gauss(0, voltage_jitter_std)
```

Bu senaryo **tüm state'lerde aktiftir** (A ve B'den farklı olarak), çünkü elektriksel bağlantı sorunu mekanik harekete bağlı değil. Pratikte RAISING/HOLDING'de daha gözle görülür çünkü motor enerjili.

Determinizm: `runtime.rng` per-device seed'li → testler tekrarlanabilir. Periyodik değil rastgele süreç — DOMAIN.md "düzensiz sıçramalar" tanımına uygun.

**Tipik params:** `spike_prob=0.05`, `voltage_jitter_std=0.6` (baseline 0.2'nin 3 katı).

---

## 10. Config Dosyaları

Üç ayrı dosya, ayrı sorumluluklar:

| Dosya | Sorumluluk |
|---|---|
| `config/mqtt.yaml` | Broker bağlantısı, topic prefix'leri, QoS |
| `config/devices.yaml` | Cihaz listesi, sensörler, state süreleri, senaryo pencereleri |
| `config/simulator.yaml` | Engine tick hızı, log seviyesi |

`.example` dosyaları repo'da; gerçek dosyalar `.gitignore`'da (CLAUDE.md güvenlik kuralı).

`devices.yaml` örnek:

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
    scenarios:
      - name: hydraulic_leak
        start_after_s: 60
        duration_s: 600
        params:
          leak_rate_bar_per_min: 5.0
          position_sag_mm: 2.0
```

---

## 11. Hata Yönetimi

`except Exception:` yasak (CLAUDE.md). Spesifik tipler yakalanır.

| Hata | Davranış | Gerekçe |
|---|---|---|
| Config dosyası yok / `yaml.YAMLError` | Erken çık (exit 2), Loguru ERROR + dosya yolu | Boot-time hata gizlenmez |
| Şema validation hatası (`ValueError`, `KeyError`) | Erken çık, eksik/yanlış alanı mesajda göster | Dataclass `__post_init__` doğrular |
| `KeyError` registry lookup (bilinmeyen sensör/senaryo adı) | Erken çık, geçerli isimleri listele | Tipik typo |
| MQTT broker boot-time bağlanamıyor | Loguru WARN + retry, exponential backoff max 30 s | Broker geç açılıyor olabilir |
| MQTT runtime disconnect | paho-mqtt `reconnect_delay_set` ile otomatik | Servis ayağa kalkmalı |
| Sensör `compute()` istisna (spesifik tip) | Loguru ERROR, o sensör için tick'i atla, devam et | Bir sensör buggy ise tüm cihaz düşmesin |
| asyncio task crash | Loguru CRITICAL, engine durur, exit 1 | Sistemli yeniden başlatma (systemd / docker restart) |
| SIGINT / SIGTERM | Engine `asyncio.run()` içinde `asyncio.get_running_loop().add_signal_handler(SIGINT/SIGTERM, shutdown.set)` ile shutdown event'i set eder. Cihaz task'ları event'i kontrol edip döngüden çıkar. `MQTTPublisher.close()` → `paho.disconnect()` + son mesajların flush'ı. Engine exit 0. (Iter 2a/2b'deki `signal.signal` Iter 3'te asyncio pattern'i ile değiştirilir — Python 3.10+ `get_event_loop` deprecated.) | Container/systemd ortamında temiz kapanma — açık MQTT bağlantısı/yarım mesajlar kalmasın |

---

## 12. Test Stratejisi

Her iterasyonun **kendi testleriyle** kapanır — sona kalmış test borcu yok. CLAUDE.md "her özellikle paralel test" prensibi.

### Klasör Yapısı

```
tests/
├── unit/          # Sensör + senaryo + state machine, izole
├── integration/   # Engine + publisher uçtan uca (paho mock / test-loop)
├── scenarios/     # Senaryo imza testleri (istatistiksel)
└── fixtures/      # Deterministik YAML config + seed'li çıktı snapshot'ları
```

### Saat Mock Pattern: `FakeClock`

State geçişleri ve zamana-bağlı senaryolar test edilebilir kılmak için `DeviceRuntimeState.clock` field'ı dependency injection kullanır (default `time.monotonic`). Test'lerde `FakeClock` instance inject edilir:

```python
class FakeClock:
    """Test-only: zamanı manuel kontrol et."""

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds
```

Üretim kodu `FakeClock`'u import etmez; sınıf `tests/unit/test_runtime.py` veya `tests/conftest.py` içinde tanımlı. Bu pattern monkeypatch yerine açık DI sağlar — mocklama imzada görünür.

### Unit Test Prensipleri

- **Sensörler:** `compute(runtime, position)` deterministiktir (RNG ve gürültü yok). Stateless sensörler için tek tick'lik test yeterli. Stateful sensörler (motor_temperature) için: yeni instance oluştur → bilinen runtime sequence ver → çıktı sequence'ini doğrula. State + elapsed verilip dönen değer aralığı doğrulanır.
- **Senaryolar:** Temiz değer girilir, `modify()` çıktısı doğrulanır. Senaryonun aktif olmadığı durumda değer değişmemeli.
- **State machine `advance()`:** `time.monotonic()` mock'lanır, transition zamanları kontrol edilir, `current_state_duration_s` invaryantı doğrulanır.
- **Publisher:** paho-mqtt mock'lanır, topic + payload doğrulanır.

### Integration Test Prensipleri

- Broker: **paho-mqtt mock veya test-loop**. Gerçek Mosquitto'ya karşı testler `tests/smoke/` (CI dışı, sadece lokal/manuel).
- Deterministik seed ile 60 sn'lik run → mesaj sayısı + sıra + şema fixture snapshot'una karşı doğrulanır.

### Asyncio Test Pattern (Iterasyon 3+)

Engine asyncio'ya geçtiğinde `asyncio.sleep` gerçek wall-clock değerlerini bekler; testlerde bu kabul edilemez (10 sn'lik integration testi 10 sn sürmemeli). Pattern:

- **`pytest-asyncio` (auto mode)** dev dependency olarak eklenir. `@pytest.mark.asyncio` decorator zorunlu değil — auto-mode `async def test_*` fonksiyonlarını yakalar.
- **`asyncio.sleep` no-op'lanır:** Lambda gövdesinde tekrar `asyncio.sleep` yazmak monkeypatch'li sembolü çağırır → sonsuz döngü. Doğru pattern orijinal referansı önceden saklamak:
  ```python
  original_sleep = asyncio.sleep
  monkeypatch.setattr("asyncio.sleep", lambda _s: original_sleep(0))
  ```
  Bu, event loop'a yield eder ama gerçek beklemez — diğer task'lar koşar, deterministik ilerleme sağlanır. Alternatif olarak engine modülünün gördüğü sembol patch'lenebilir (`"simulator.engine.asyncio.sleep"`), ki bu daha dar bir scope sunar.
- **Zaman `FakeClock.advance(1.0)` ile sürülür:** Her tick öncesi (veya tick batch sonrası) test FakeClock'u manuel ilerletir → `runtime.clock()` doğru elapsed döndürür → state machine geçişleri tetiklenir.
- **`max_iterations` parametresi per-device korunur:** Test'te her cihaz N tick sonra normal exit verir; `asyncio.gather(*tasks)` await'i kilitlenmez.
- **Shutdown event testi:** `shutdown.set()` doğrudan çağrılır; tüm task'ların temiz çıktığı `asyncio.wait_for(gather, timeout=...)` ile doğrulanır.

Production'da `clock=time.monotonic` ve gerçek `asyncio.sleep(1.0)` senkronize çalışır (sleep gerçek 1 sn, clock gerçek 1 sn ilerler). Test'te ikisi birden ayrı kontrol edilir.

### Senaryo İmza Testleri (Iterasyon 4)

İstatistiksel hipotez testleri (eşik karşılaştırması değil) — `scipy.stats` kullanılır.

| Senaryo | Test | Eşik |
|---|---|---|
| A | RAISING'de motor_current ortalama artışı | t-testi p<0.05, ortalama ∈ [+15%, +30%] |
| B | HOLDING'de hydraulic_pressure trend | Spearman ρ<0, p<0.05 |
| C | motor_voltage std oranı | F-testi p<0.05, std_aktif ≈ 3*std_baseline |

### Kapsama

`pytest --cov=src/simulator` her iterasyon sonunda yeşil ve toplam %80+.

---

## 13. Açık Kararlar (İlerleyen Fazlara Ertelenenler)

| Konu | Iterasyon | Yön |
|---|---|---|
| Integration broker (mock mı test-loop mu) | 3 | Basitlik+hız lehine; smoke testler CI dışı |
| Birden fazla cihaz tipi | Faz 9+ | Şu an tek tip yeterli, registry yapısı destekliyor |
| Sensör başına farklı frekans | Faz 9+ | Şu an YAGNI; 1 Hz hepsi için yeterli |
| Pompa simülasyonu | Belirsiz | Faz 4'te dedektörler ihtiyaç duyarsa |

---

## 14. Spec'e Karşı Disiplin

- Bu spec Faz 1 boyunca **tek hakemdir**.
- Spec ile çelişen kod kabul edilmez.
- Spec değişikliği önce bu dosyada yapılır, sonra kod izler.
- DOMAIN.md ile çelişen sayısal değer spec'e girmez. Numerik değer eklenirken DOMAIN.md satır referansı zorunludur (bu dokümanın § 6 ve § 9'unda olduğu gibi).
- Bir geliştirici (insan veya AI) sayı önerirse, DOMAIN.md'ye karşı doğrulamadan kabul edilmez.

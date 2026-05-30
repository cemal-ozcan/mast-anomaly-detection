# CLAUDE.md — Proje Brifingi

Bu dosya Claude Code tarafından her oturum başında otomatik olarak okunur. Projenin anayasası niteliğindedir.

---

## Proje Özeti

Endüstriyel teleskopik mast cihazlarından gelen telemetri verisi üzerinde gerçek zamanlı anomali tespiti yapan bir erken uyarı sistemi. Hedef: arıza henüz oluşmadan önce davranışsal sapmaları yakalamak ve teknisyenlere uyarı üretmek.

**Bu prototip aşamasında tamamen sentetik veri ile çalışılır.** Gerçek saha verisi bu kod tabanına asla girmez.

---

## Kuzey Yıldızı — Tek Kural Hepsini Yener

> **Çalışan, anlaşılır, küçük bir parça; çalışmayan büyük bir sistemden her zaman daha değerlidir.**

Bu projede her karar bu prensibe göre alınır. Karmaşık bir çözüm önerirken kendine sor: "Bunun basit hali ne işe yarar? Önce o yeterli mi?" Cevap çoğu zaman evet olur.

---

## Tech Stack ve Gerekçeler

**Python 3.11+** — Tüm servisler Python ile yazılır. Tip ipuçları (type hints) zorunlu.

**MQTT (paho-mqtt + Mosquitto broker)** — Servisler arası iletişim için. Gevşek bağlı mimari, ileride dağıtık sisteme geçiş kolay.

**SQLite** — Başlangıçta tek dosyalık veritabanı yeterli. Prototip büyürse TimescaleDB'ye geçilir; o zamana kadar SQLite kullan.

**Pandas + NumPy** — Veri işleme ve analiz için standart.

**scikit-learn** — Makine öğrenmesi tabanlı anomali tespiti için (Isolation Forest, One-Class SVM).

**Streamlit** — Dashboard için. Saf Python, hızlı prototipleme. Frontend framework'üne girme.

**pytest** — Test framework. Her dedektör için en az bir unit test olmalı.

**Loguru** — Loglama. `print` yerine her zaman Loguru kullan.

**Docker + Docker Compose** — Servisleri container'lara böleceğiz ama önce kod çalışsın, sonra container'la. Erken Docker'a girip kafa karıştırma.

---

## Mimari Prensipler

Sistem **olay güdümlü (event-driven)** bir mimaride çalışır. Her servis bağımsız bir Python süreci olarak yaşar ve MQTT üzerinden iletişim kurar. Bu sayede bir servis çökse diğerleri etkilenmez.

Servisler şunlardır: simulator (sentetik veri üretici), ingestion (MQTT okuyup veritabanına yazan), detectors (anomali tespit motoru), alerts (uyarı yönetimi), dashboard (görselleştirme).

Her servisin **tek bir sorumluluğu** vardır. Simulator sadece veri üretir, başka bir şey yapmaz. Ingestion sadece okur ve kaydeder. Bu disipline sıkı uy.

Anomali tespit motoru **üç katmanlı** çalışır: kural tabanlı, istatistiksel, makine öğrenmesi. Bunlar paralel çalışır ve sonuçları bir füzyon mantığı ile birleştirilir. Detay için `docs/ARCHITECTURE.md` dosyasına bak.

---

## Proje Yapısı

```
mast-anomaly-detection/
├── CLAUDE.md                # Bu dosya — Claude Code brifingi
├── README.md                # İnsan okuyucu için proje tanıtımı
├── docs/                    # Detaylı dokümantasyon
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── DOMAIN.md
│   └── SECURITY.md
├── .claude/                 # Claude Code yapılandırması
│   └── commands/            # Custom slash komutları
├── src/                     # Tüm kaynak kod
│   ├── simulator/           # Sentetik veri üretici
│   ├── ingestion/           # MQTT okuyucu ve veritabanı yazıcı
│   ├── storage/             # Veritabanı şeması ve erişim katmanı
│   ├── detectors/           # Anomali tespit motoru
│   │   ├── rules/           # Kural tabanlı dedektörler
│   │   ├── statistical/     # İstatistiksel dedektörler
│   │   └── ml/              # Makine öğrenmesi dedektörleri
│   ├── alerts/              # Uyarı yönetimi ve önceliklendirme
│   └── dashboard/           # Streamlit dashboard
├── tests/                   # Pytest test paketi
├── notebooks/               # Jupyter deneyleri (üretim kodu değil)
├── data/                    # Sentetik veri ve veritabanı dosyaları (git ignore)
├── requirements.txt
└── pyproject.toml
```

Yeni bir özellik eklerken **mevcut yapıyı bozma**. Yeni bir klasör açmadan önce uygun mevcut klasörü değerlendir.

---

## Kodlama Konvansiyonları

**Tip ipuçları zorunlu.** Tüm fonksiyonlar ve metotlar tipli olsun. `mypy` uyumlu yaz.

**Docstring zorunlu.** Public fonksiyonların ne yaptığı, parametreleri, dönüşü ve gerekiyorsa örneği docstring'de açıklanır. Google stili tercih edilir.

**İsimlendirme:** Modüller `snake_case`, sınıflar `PascalCase`, fonksiyonlar ve değişkenler `snake_case`, sabitler `UPPER_CASE`.

**Dependency injection.** Veritabanı bağlantısı, MQTT istemcisi gibi bağımlılıklar fonksiyona dışarıdan verilir, içeride üretilmez. Bu test edilebilirliği artırır.

**Konfigürasyon dosya odaklı.** Hard-coded değer yok. Eşikler, parametreler, bağlantı bilgileri `config.yaml` veya `.env` dosyasından okunur.

**Loglama disiplinli.** Her servis `loguru` kullanır. Hata, uyarı, bilgi seviyeleri ayrılır. Hassas veri loglara yazılmaz.

**Hata yönetimi.** Geniş `except Exception` yakalama yapma. Beklenen hata tiplerini spesifik yakala.

**Her özellik için test.** Yeni bir dedektör veya servis eklenirken paralel olarak `tests/` altına test eklenir.

---

## Güvenlik Kuralları — Mutlak Kurallar

Bu kurallar pazarlık konusu değildir. Asla ihlal etme.

**Hiçbir gerçek telemetri verisi bu kod tabanına girmez.** Sadece simulator'ın ürettiği sentetik veri kullanılır.

**Hiçbir kimlik bilgisi (parola, API anahtarı, sertifika) commit edilmez.** `.env` dosyaları `.gitignore`'da. Örnek değerler için `.env.example` kullanılır.

**Hiçbir gerçek müşteri, firma, ürün ismi koda veya dokümana girmez.** Domain bilgisini "sektör nötr" şekilde anlat. Örnek: "endüstriyel teleskopik mast" diyebilirsin, belirli bir model veya seri numarası yazamazsın.

**Veritabanı dosyaları, sentetik veri çıktıları `data/` klasöründedir ve `.gitignore` listesindedir.**

Detaylar için `docs/SECURITY.md` dosyasına bak.

---

## Kapsam Dışı — Şu Anda Yapmıyoruz

Bu projenin bu aşamasında **kesinlikle yapmadığımız** şeyler:

- **Büyük dil modeli (LLM) entegrasyonu yok.** Hiçbir Ollama, hiçbir API çağrısı, hiçbir LLM kütüphanesi import edilmez.
- **RAG (Retrieval-Augmented Generation) sistemi yok.** Vektör veritabanı, embedding modeli, doküman indeksleme yok.
- **Fine-tuning yok.** Hiçbir model fine-tune edilmiyor.
- **Bulut servisi yok.** AWS, Azure, GCP, hiçbiri kullanılmaz. Her şey lokal.
- **Cihaz kontrolü yok.** Sistem sadece **gözlem modu** çalışır, hiçbir mastı veya cihazı yönetmez, hiçbir komut göndermez.
- **Otomatik bakım çağrısı yok.** Sistem sadece uyarı üretir, hiçbir tarafa otomatik iş emri açmaz.

Eğer bu listede olan bir şey ileride gerekirse, **önce konuşulur, kuzey yıldızı prensibine göre değerlendirilir, sonra yapılır.** Sessizce ekleme.

---

## Mevcut Faz

**Faz 3 — Streamlit Dashboard** (sıradaki) — Faz 2 tamamlandı (2026-05-30)

- **Spec (tek hakem):** `docs/specs/2026-05-18-faz1-simulator-design.md`
- **Spec (Faz 2):** `docs/specs/2026-05-29-faz2-ingestion-storage-design.md`
- **Tamamlanan iterasyonlar:**
  - `docs/plans/2026-05-18-faz1-iterasyon1-walking-skeleton.md` (7/7 ✅)
  - `docs/plans/2026-05-19-faz1-iterasyon2a-state-machine.md` (9/9 ✅)
  - `docs/plans/2026-05-28-faz1-iterasyon2b-tum-sensorler.md` (8/8 ✅)
  - `docs/plans/2026-05-28-faz1-iterasyon3-asyncio-multi-device.md` (8/8 ✅)
  - `docs/plans/2026-05-28-faz1-iterasyon4a-senaryo-altyapisi-mechanical-wear.md` (6/6 ✅)
  - `docs/plans/2026-05-28-faz1-iterasyon4b-hydraulic-leak-electrical-fault.md` (8/8 ✅)
  - `docs/plans/2026-05-29-faz2-iter2-1-walking-skeleton-ingestion.md` (5/5 ✅)
  - `docs/plans/2026-05-29-faz2-iter2-2-sqlite-repository.md` (7/7 ✅)
  - `docs/plans/2026-05-30-faz2-iter2-3-batch-writer-resilience.md` (7/7 ✅)
- **Yürütme modu:** subagent-driven (her task ayrı subagent + two-stage review)
- **Çalıştırma:**
  - Simulator: `pip install -e .` editable install gerekli; sonra `python -m simulator` MQTT'ye N cihaz × 6 sensör × 1 Hz paralel yayın yapar (devices.yaml.example varsayılan 3 cihaz).
  - Ingestion (Iter 2.3): `python -m ingestion` mesajları BatchWriter kuyruğuna alır; ayrı drainer thread batch (`insert_batch`) ile SQLite'a yazar (`data/telemetry.db`, boot'ta idempotent migration, broker kopmasında paho reconnect). Doğrula: `sqlite3 data/telemetry.db "SELECT COUNT(*) FROM telemetry"`. Throughput smoke (opt-in): `RUN_SMOKE=1 SMOKE_DURATION_S=5 pytest tests/smoke/` (gerçek Mosquitto gerekir).
  - **Not (manuel smoke):** Aynı broker'da iki ingestion instance'ı aynı `client_id`'yi (`mast-anomaly-subscriber`) paylaşır → biri diğerini broker'dan düşürür. Manuel test tek instance ile yapılmalı; throughput smoke izole `smoke/+/+` namespace + `smoke` client_id kullanır (çakışma yok).
  - **Env not:** Python 3.11.15 `.pth` dosyalarını silent skip ediyor (security hardening). Eğer `python -m simulator` veya `python -m ingestion` ImportError verirse `PYTHONPATH=src python -m ...` ile çalıştır, ya da `python3.11 -m venv .venv --clear && pip install -r requirements.txt -e .` ile venv'i yeniden oluştur.
- **Test/lint disiplini:** Her task sonunda tam suite + `mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios` + `ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios`.

### Iterasyon 1 (Walking Skeleton) — Tamamlandı (2026-05-19)

Tek `motor_current` sensörü, 1 Hz Gauss gürültülü MQTT yayını, SIGINT/SIGTERM graceful shutdown, 17 unit test. Sabit `state="idle"`.

### Iterasyon 2a (State Machine) — Tamamlandı (2026-05-28)

State machine altyapısı: `DeviceState` StrEnum, `DeviceRuntimeState` (clock DI), `advance_state_machine`, `compute_position`, `BaseSensor` ABC, `SENSOR_REGISTRY`. `motor_current` refactor (`sample()` → `compute(runtime, position)`). 42 unit test.

### Iterasyon 2b (Kalan 5 Sensör) — Tamamlandı (2026-05-28)

6 sensör tam set: motor_current, motor_voltage (sabit 24V), hydraulic_pressure (4 state baseline), motor_temperature (TEK stateful — lineer ısınma/soğuma, instance attribute), mast_position (compute_position passthrough), vibration. Engine N-sensör loop, `_validate_iteration2b_constraints` strict 6-sensör seti. 71 unit test, ~%93 coverage. Manuel uçtan uca: 6 sensör 1 Hz paralel akıyor, JSON şeması doğru, gauss noise + state-bazlı baseline'lar gözlemlendi.

### Iterasyon 3 (asyncio + Çoklu Cihaz) — Tamamlandı (2026-05-28)

Engine asyncio loop'a geçti. `engine.run()` artık `asyncio.run(_amain(...))` çağırıyor;
`async def run_device(...)` per-cihaz task'ı. N cihaz `asyncio.gather(*tasks)` ile paralel.
Paylaşılan tek `MQTTPublisher`, ortak `engine_boot_at` (regresyon testi için). SIGINT/SIGTERM
`loop.add_signal_handler` + `asyncio.Event` ile yönetiliyor. `_validate_iteration2b_constraints`
→ `_validate_devices` rename + N cihaz desteği (unique ID, same-seed WARN, her cihaz tam 6
sensör). `pytest-asyncio==0.23.7` dev dep, auto-mode. Toplam 87 test (71 Iter 2b + 16 yeni:
async sanity 2, validation 6, engine asyncio 5, integration 3). Manuel uçtan uca: 3 cihaz
paralel akıyor, topic disambiguation doğru, SIGINT temiz shutdown.

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

### Iterasyon 4b (HydraulicLeak + ElectricalFault + Tam İmza Seti) — Tamamlandı (2026-05-29)

`HydraulicLeak` (B): sadece HOLDING aktif, `held_minutes = elapsed_in_state_s / 60`,
hydraulic_pressure → max(5.0, clean - leak_rate * held_minutes), mast_position
lineer sag. `ElectricalFault` (C): state filter YOK, per-sensor independent
`runtime.rng.random()` spike check (modify pure), spike branch motor_current
+uniform(-2,4) + motor_voltage +uniform(-30,30), non-spike branch motor_voltage
gauss jitter. SCENARIO_REGISTRY 3 entry tam set. `tests/scenarios/conftest.py`
DRY refactor (CountingClock + patched_engine_clock fixture). 2 yeni istatistiksel
imza: HydraulicLeak Spearman ρ=−0.30/p=3e-04, ElectricalFault Bartlett
p=6e-158/std ratio ~22. `scipy==1.17.1` explicit pin. Toplam 128 test,
%94 coverage. devices.yaml.example device_003'e B+C eklendi → 3 cihaz ×
3 farklı durum manuel demo. **Faz 1 tamamlandı.**

## Faz 1 Closure (2026-05-29)

Faz 1 = simulator (sentetik telemetri üretici). Tek cihaz tipi (telescopic_mast_v1),
6 sensör, 4 state machine, N cihaz paralel (asyncio), 3 fault scenario (A/B/C)
+ istatistiksel imzaları. spec § 1 kapsam içi maddeleri tamamlandı. 128 test
yeşil, %94 coverage. Faz 2 (Ingestion + SQLite) bir sonraki büyük adım.

## Faz 2 (Ingestion + SQLite Storage)

### Iterasyon 2.1 (Walking Skeleton — MQTT Subscriber + Console Log) — Tamamlandı (2026-05-29)

`src/ingestion/` package'ı kuruldu: `config.py` (`IngestionConfig` dataclass + YAML loader),
`message_parser.py` (`IngestedReading` frozen dataclass + `parse_message`), `subscriber.py`
(`MQTTSubscriber` paho wrapper, loop_start background thread, callback delegasyonu),
`__main__.py` (config + subscriber + signal handler + parse-log pipeline). Bozuk JSON /
eksik field → ERROR log + skip (servis çökmez). SIGINT/SIGTERM graceful shutdown
(loop_stop + disconnect). `config/ingestion.yaml.example` ile birlikte 13 yeni unit test
(config 3 + parser 5 + subscriber 3 + main 2). 128 → 141 test, %92 toplam coverage,
ingestion paketi ≥%85. Manuel uçtan uca: simulator + ingestion paralel çalışıyor,
198 mesaj 10 saniyede parse + loglandı, SIGINT temiz exit.

### Iterasyon 2.2 (SQLite + Repository Pattern) — Tamamlandı (2026-05-30)

`src/storage/` package'ı kuruldu (SQLAlchemy 2.0 Core, ORM değil): `schema.py`
(`telemetry` wide tablo Table + composite index `(device_id, sensor, timestamp)`;
DDL ÇALIŞTIRMAZ, sadece expression builder), `engine.py` (`create_sqlite_engine`
factory — parent dizin + WAL/synchronous=NORMAL/foreign_keys=ON pragma connect-event),
`migrator.py` (`apply_migrations` saf fonksiyon + `schema_version` tablosu + çok-statement
`;` split — pysqlite tek-statement davranışı için), `repository.py` (`TelemetryRepository`
— `insert(reading)` tek tek + `count()`/`fetch_recent()` minimal okuma; batch Iter 2.3),
`migrations/001_initial.sql` (runtime DDL'in TEK kaynağı). Ingestion `__main__` orchestration'da
kaldı (engine extraction Iter 2.3'e ertelendi): boot'ta engine + idempotent migration +
repository; handler `repository.insert` çağırır, `OperationalError` → CRITICAL + skip
(tam retry resilience Iter 2.3); engine outer try/finally'de dispose. Test fixture'ları
`migrated_engine`/`in_memory_engine` (StaticPool `:memory:` — connection paylaşımı için).
141 → 155 test (schema 2 + engine 2 + migrator 3 + repository 4 + integration 2; main 2
refactor + 1 OperationalError swallow), ingestion+storage %86.8 coverage (storage %100).
Manuel uçtan uca (gerçek Mosquitto + simulator): 3 cihaz × 6 sensör SQLite'a yazıldı,
EXPLAIN QUERY PLAN composite index kullandı, restart'ta migration no-op + veri append,
SIGINT temiz exit. **Faz 2 Iter 2.2 kapandı.**

### Iterasyon 2.3 (Batch Writer + Resilience + Performance) — Tamamlandı (2026-05-30)

`src/ingestion/batch_writer.py` kuruldu: `BatchWriter` sınıfı (thread-safe `queue.Queue`
buffer + ayrı daemon drainer thread; asyncio DEĞİL — paho callback'leri thread'den gelir)
+ saf `_should_flush` helper (boyut/süre eşiği, deterministik test). Drainer flush koşulu
`max(buffer≥max_size, süre≥flush_interval_s)`; shutdown'da **kuyruğu boşaltıp** (`_drain_queue_into`)
son flush yapar (veri kaybı yok — spec § 8 pseudocode düzeltmesi). SQLite hatası `_flush_with_retry`
ile bounded retry (3x, `sleep` DI); kalıcı fail → CRITICAL + `failed=True` + `shutdown_event.set()`
(graceful kapanma; tam exit-3 orchestration Faz 9+'a ertelendi). `repository.insert_batch`
(Core executemany, `_reading_to_dict` ile `insert` DRY). `subscriber.py` `reconnect_delay_set(1,30)`
(broker kopmasında otomatik backoff reconnect). `__main__` handler artık `batch_writer.enqueue`
(DB yazma drainer'a taşındı; OperationalError handler'dan kalktı); `run()` BatchWriter
start/stop lifecycle (finally: subscriber.stop → batch_writer.stop → engine.dispose).
`tests/smoke/` YENİ kategori: opt-in çift kapı (`RUN_SMOKE=1` env + broker erişilebilirlik),
izole `smoke/+/+` namespace, yapay 1000 msg/sec publisher. 155 → 167 test (default'ta 166
passed + 1 smoke skipped); ingestion+storage %89.2 coverage (storage %100, batch_writer %99).
**Throughput smoke (gerçek Mosquitto, 1000 msg/sec):** sent==written, %0 kayıp (4000/4000,
5003/5003 gözlemlendi). Shutdown-flush no-data-loss unit (50→50) + integration (100→100) ile
kanıtlı. Reconnect mekanizması unit-test'li; canlı broker-restart dokümante manuel.
**Faz 2 Iter 2.3 kapandı.**

## Faz 2 Closure (2026-05-30)

Faz 2 = ingestion + SQLite storage. MQTT subscriber (paho) → parse → BatchWriter kuyruk →
drainer thread → `insert_batch` → SQLite (`telemetry` wide tablo + composite index, script-based
idempotent migration). 1000 msg/sec kayıpsız throughput, reconnect backoff, graceful
shutdown final-flush. 167 test, ingestion+storage %89.2 coverage. ROADMAP Faz 2 kabul
kriterleri karşılandı. **Sıradaki büyük adım: Faz 3 — Streamlit Dashboard.**

Faz seyri: `docs/ROADMAP.md`.

---

## Önemli Davranış Kuralları (Claude Code için)

**Tahminle iş yapma.** Eğer bir karar belirsizse, kullanıcıya sor. Özellikle: dedektör eşik değerleri, sensör türleri, arıza senaryoları gibi domain bilgisi gerektiren konular.

**Tek seferde çok şey yapma.** Bir görev verildiğinde küçük bir adım at, göster, onay al, sonraki adıma geç. Saatlerce kod yazıp sonunda göstermek yerine, parçalar halinde ilerle.

**Dokümanı güncelle.** Mimari kararı değiştirirsen `docs/ARCHITECTURE.md`'yi güncelle. Yeni faza geçtiğinizde `docs/ROADMAP.md`'yi güncelle. Dokümanlar canlıdır, kodla birlikte yaşar.

**Bağımlılık eklerken dikkat et.** Yeni bir `pip install` önerirken kullanıcıya gerekçesini söyle. "Bu kütüphane şu işi yapacak, çünkü manuel yazmak X saat sürer" gibi.

**Performans için erken optimize etme.** Önce çalışsın, sonra ölçeriz, sonra hızlandırırız. Premature optimization yapma.

---

## Yardımcı Dokümanlar

Detay gerektiğinde şu dosyalara başvur:

- `docs/ARCHITECTURE.md` — Sistem mimarisi, katman detayları, veri akışı
- `docs/ROADMAP.md` — Faz planı, milestone'lar, kabul kriterleri
- `docs/DOMAIN.md` — Teleskopik mast domain bilgisi, sensör türleri, arıza senaryoları
- `docs/SECURITY.md` — Güvenlik kuralları, kapalı ağ prensipleri

`.claude/commands/` altında tekrarlayan işler için custom slash komutları var. Yeni komut ekleme ihtiyacı doğarsa kullanıcıya öner.

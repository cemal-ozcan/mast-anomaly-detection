# Faz 2 — Ingestion + SQLite Storage Tasarım Dokümanı

**Tarih:** 2026-05-29
**Durum:** Onaylanmış tasarım — implementasyon planı hazırlanacak
**Faz referansı:** `docs/ROADMAP.md` § Faz 2
**Mimari referansı:** `docs/ARCHITECTURE.md`
**Faz 1 contract referansı:** `docs/specs/2026-05-18-faz1-simulator-design.md` § 7 (MQTT topic + payload şeması)

Bu doküman Faz 2 (Ingestion + Storage) boyunca tek hakemdir. İmplementasyonda bir karar belirsizleşirse önce buraya bakılır; spec ile çelişen kod kabul edilmez. Spec değişirse önce bu doküman güncellenir, sonra kod.

---

## 1. Amaç ve Kapsam

Faz 1'in MQTT'ye yayınladığı sentetik telemetriyi güvenilir şekilde SQLite veritabanına yazan bağımsız bir servis tasarlamak. Servis Faz 1'le aynı süreç olarak çalışmaz; ayrı bir Python süreci olarak `python -m ingestion` ile başlatılır.

**Kapsam içi:**
- MQTT subscriber servisi (`src/ingestion/`)
- SQLite şema + tek wide tablo `telemetry`
- SQLAlchemy Core repository pattern (`src/storage/`)
- Time/size-based batch yazma (max 100 mesaj veya 1 sn)
- Yalın script-based schema migration (`src/storage/migrations/`)
- Auto-reconnect (paho `reconnect_delay_set` exponential backoff)
- SIGINT/SIGTERM graceful shutdown
- pytest test paketi (%80+ kapsama)
- 1000 msg/sec yük testi (smoke kategorisinde, CI dışı)

**Kapsam dışı (Faz 2):**
- Anomali tespit (Faz 4-6)
- Dashboard (Faz 3)
- TimescaleDB (Faz 9+ stretch)
- Alembic migration framework (yalın script yeterli)
- ORM (SQLAlchemy Core SQL builder yeterli)
- Multi-process scaling (Faz 9+)
- Authentication / TLS MQTT (Faz 9+ güvenli ağ)

---

## 2. Kuzey Yıldızı ve Tasarım Disiplini

CLAUDE.md prensibi: *"Çalışan, anlaşılır, küçük bir parça; çalışmayan büyük bir sistemden her zaman daha değerlidir."*

Faz 2 bu prensibe **walking skeleton + iterasyon** modelinde uyar (Faz 1 pattern). Her iterasyon kendi başına çalışır ve test edilir; sonraki iterasyona ancak kullanıcı onayı ile geçilir. Sona kalmış test borcu birikmesin diye testler her iterasyonun parçasıdır.

---

## 3. İterasyon Planı ve Kabul Kriterleri

### Iterasyon 2.1 — Walking Skeleton (MQTT Subscriber + Console Log)

**Kapsam:**
- `src/ingestion/__main__.py` entry point (`python -m ingestion`)
- `src/ingestion/subscriber.py` paho-mqtt wrapper (subscribe, message callback)
- `src/ingestion/message_parser.py` JSON payload → `IngestedReading` dataclass (frozen)
- Minimum config: mqtt.yaml (broker bilgisi mevcut, Faz 1'den) + ingestion.yaml (topic pattern, log level)
- Console log: her mesaj alındığında loguru INFO ile (henüz SQLite yok)
- SIGINT/SIGTERM graceful shutdown

**Bitti kriterleri:**
1. `python -m ingestion` çalışır, çökmez.
2. Simulator paralel çalışırken ingestion her mesajı loguru ile basar.
3. Bozuk JSON payload veya eksik field → ERROR log + mesaj skip, servis devam eder.
4. Ctrl+C → "shutdown" log + temiz exit (0).
5. Unit testler: `tests/unit/test_ingestion_subscriber.py`, `test_ingestion_message_parser.py`. Hedef ≥%85 ingestion paketi coverage.

### Iterasyon 2.2 — SQLite + Repository Pattern

**Kapsam:**
- `src/storage/` package: `engine.py` (SQLAlchemy Core engine factory), `schema.py` (Table tanımı), `repository.py` (`TelemetryRepository` — `insert(reading)` tek tek + minimal okuma `count()` / `fetch_recent(device_id, sensor, limit)` (bitti kriteri 2 & 3 doğrulaması için); `insert_batch` + geniş query API Iter 2.3)
- SQLite şema: tek tablo `telemetry(id INTEGER PRIMARY KEY, device_id TEXT, sensor TEXT, timestamp TEXT, state TEXT, value REAL, unit TEXT)` + composite index `(device_id, sensor, timestamp)`
- `src/storage/migrations/001_initial.sql` — şema tanımı + index
- `src/storage/migrator.py` — `schema_version` tablosu yönetimi + sıralı SQL dosyalarını apply
- Ingestion `__main__` SQLAlchemy engine kurulumu + ilk migration apply + her mesajda `repository.insert(reading)` çağrısı

**Bitti kriterleri:**
1. `python -m ingestion` simulator çalışırken her mesajı SQLite'a yazar (tek tek insert).
2. `sqlite3 data/telemetry.db "SELECT COUNT(*) FROM telemetry"` ile veri doğrulanabilir.
3. `sqlite3 ... "SELECT * FROM telemetry WHERE device_id='device_001' AND sensor='motor_current' ORDER BY timestamp DESC LIMIT 5"` indeks kullanır (EXPLAIN QUERY PLAN ile doğrulanır).
4. Migration tekrar koşturulduğunda no-op (`schema_version` ile idempotent).
5. Servis durdurulup yeniden başlatılınca migration tekrar koşmaz, yeni veriler eski db'ye eklenir.
6. Unit + integration testler: in-memory SQLite ile repository CRUD, migration apply/idempotent, mock paho subscriber ile end-to-end. ≥%85 coverage.

### Iterasyon 2.3 — Batch Writer + Resilience + Performance

**Kapsam:**
- `src/ingestion/batch_writer.py` — `threading.Queue` tabanlı buffer + ayrı drainer thread; flush koşulu `max(buffer_size=100, time_since_last_flush=1s)`. asyncio değil çünkü paho callback'leri background thread'den çağrılır; thread-safe queue ile uyumlu (detay § 8)
- Repository `insert_batch(readings)` metodu (SQLAlchemy Core `insert().executemany` veya `Connection.execute(insert, [...])`)
- paho `reconnect_delay_set(min_delay=1, max_delay=30)` exponential backoff
- Graceful shutdown: shutdown event set olunca buffer'da kalan mesajlar son bir flush ile yazılır (data kaybı yok)
- Performance smoke: 1000 msg/sec için 60 saniyelik yük testi (`tests/smoke/test_ingestion_throughput.py`) — simulator artırılmış cihaz sayısı (örn. 60 cihaz × 6 sensör × 1 Hz = 360/sec) veya yapay yük üretici

**Bitti kriterleri:**
1. 60 cihazlı simulator setup'ında ingestion 60 saniye boyunca kayıpsız çalışır (mesaj sayısı simulator publish sayısı ile eşit ± 1%).
2. Broker yeniden başlatıldığında ingestion otomatik bağlanır, kayıp mesaj sayısı QoS 1 garantisi dahilinde minimumdur.
3. SIGTERM sonrası buffer flush gerçekleşir (test'te `shutdown_event.set()` + buffer'a 50 mesaj koyup flush'ı doğrula).
4. 1000 msg/sec yapay yük (test fixture publisher) altında ingestion gecikme<1s, drop oranı 0.
5. Tüm önceki testler yeşil + yeni batch/resilience/throughput testleri.

---

## 4. Mimari ve Dosya Düzeni

```
src/
├── ingestion/
│   ├── __init__.py
│   ├── __main__.py              # python -m ingestion entry
│   ├── subscriber.py            # paho-mqtt wrapper
│   ├── message_parser.py        # JSON → IngestedReading
│   ├── batch_writer.py          # buffer + drainer (Iter 2.3)
│   └── config.py                # ingestion.yaml yükleyici
│
└── storage/
    ├── __init__.py
    ├── engine.py                # SQLAlchemy Core engine factory
    ├── schema.py                # Table tanımı (sqlalchemy.Table)
    ├── repository.py            # TelemetryRepository (insert, insert_batch, queries)
    ├── migrator.py              # schema_version + apply SQL files
    └── migrations/
        ├── 001_initial.sql      # CREATE TABLE telemetry + index
        └── (future migrations)

tests/
├── unit/
│   ├── test_ingestion_subscriber.py
│   ├── test_ingestion_message_parser.py
│   ├── test_ingestion_batch_writer.py     # Iter 2.3
│   ├── test_storage_repository.py
│   ├── test_storage_migrator.py
│   └── test_storage_schema.py
├── integration/
│   └── test_ingestion_end_to_end.py       # mock paho + tmp SQLite
└── smoke/                                  # YENİ kategori
    ├── __init__.py
    ├── conftest.py
    └── test_ingestion_throughput.py       # 1000 msg/sec, gerçek Mosquitto + tmp DB

config/
├── mqtt.yaml.example            # zaten Faz 1'den var (broker + topic prefix)
└── ingestion.yaml.example       # YENİ: subscribe topic pattern, batch params, db_path
```

Her servisin **tek bir sorumluluğu** vardır (CLAUDE.md):
- `subscriber.py` — sadece MQTT bağlantısı + callback
- `message_parser.py` — sadece JSON → dataclass dönüşümü
- `batch_writer.py` — sadece buffer yönetimi
- `repository.py` — sadece SQL operasyonları
- `migrator.py` — sadece şema versiyonlama

---

## 5. Veri Modelleri

### Immutable Config (YAML'den okunur)

```python
@dataclass(frozen=True)
class IngestionConfig:
    """ingestion.yaml'dan okunur."""
    db_path: Path                            # data/telemetry.db
    subscribe_topic_pattern: str             # telemetry/+/+
    batch_max_size: int = 100                # mesaj sayısı
    batch_flush_interval_s: float = 1.0      # saniye
    log_level: str = "INFO"
```

### Mesaj Modeli

```python
@dataclass(frozen=True)
class IngestedReading:
    """MQTT mesajından parse edilmiş okuma. Simulator'ın TelemetryReading'i ile contract uyumlu."""
    device_id: str
    sensor: str
    timestamp: str                            # ISO 8601 ms (Faz 1 spec § 7 format)
    state: str                                # "idle"/"raising"/"holding"/"lowering"
    value: float
    unit: str
```

**Neden timestamp `str`:** Faz 1 publisher ISO 8601 ms string üretir. Ingestion'da datetime parse etmek YAGNI (SQL `TEXT ORDER BY` ISO 8601 lexicographic sıralama doğal); detector katmanı (Faz 4+) ihtiyaç duyarsa parse eder.

**Neden ayrı `IngestedReading` (Faz 1'in `TelemetryReading`'i değil):** Faz 1 publisher dataclass'ı `state: DeviceState` (StrEnum) ve `timestamp: datetime` kullanıyordu; ingestion gelen JSON string'ten parse eder, type'lar ham. Shared module premature coupling (Faz 1 closure final review notu); ayrı dataclass net.

### SQL Şema (`schema.py` SQLAlchemy Core)

```python
from sqlalchemy import Column, Integer, MetaData, REAL, Table, Text, Index

metadata = MetaData()

telemetry = Table(
    "telemetry",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("device_id", Text, nullable=False),
    Column("sensor", Text, nullable=False),
    Column("timestamp", Text, nullable=False),    # ISO 8601 ms (lexicographic sortable)
    Column("state", Text, nullable=False),
    Column("value", REAL, nullable=False),
    Column("unit", Text, nullable=False),
)

Index("idx_telemetry_device_sensor_ts", telemetry.c.device_id, telemetry.c.sensor, telemetry.c.timestamp)
```

`schema_version` tablosu (migrator yönetir):

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

---

## 6. MQTT Subscriber Kontratı

**Topic pattern:** `telemetry/+/+` (Faz 1 spec § 7 — `telemetry/{device_id}/{sensor_name}`).

**QoS:** 1 (Faz 1 publisher zaten 1; subscriber da 1 ki broker mesaj queue garantilesin).

**paho callback:**
```python
def on_message(client, userdata, msg):
    try:
        reading = parse_message(msg.payload)
        # Iter 2.1: logger.info(reading)
        # Iter 2.2: repository.insert(reading)
        # Iter 2.3: batch_writer.enqueue(reading)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.error("Bozuk mesaj atlandı: {} payload={}", e, msg.payload[:200])
```

**Spesifik exception tipleri:** CLAUDE.md kuralı, `except Exception:` yasak.

**Connection:**
- paho `loop_start()` background thread başlatır (loop_forever blocking değil)
- `reconnect_delay_set(min_delay=1, max_delay=30)` Iter 2.3'te eklenecek
- Main loop SIGINT/SIGTERM bekler, gelince `client.loop_stop()` + `client.disconnect()`

---

## 7. SQLite Şema ve Index Stratejisi

**Tek wide tablo:** Per-sensor tablo ya da per-device tablo schema explosion yapar (6 sensör × N cihaz × yeni eklenenler). Tek tablo + composite index basit + esnek.

**Index seçim gerekçesi:** Dedektörler (Faz 4+) tipik olarak "şu cihazın şu sensörünün son N örneği" sorgular → `(device_id, sensor, timestamp)` composite index ideal. Sadece `timestamp` üzerinde tek-kolon index sorulmadı (zaman-bazlı agregate sorgu Faz 5'te).

**Type seçimleri:**
- `id`: AUTOINCREMENT INTEGER PK (insertion sırası, optional debug)
- `timestamp`: TEXT (ISO 8601 lexicographic sıralı) — REAL Unix epoch alternatif düşünüldü ama parse/format her query'de overhead
- `value`: REAL (float64)
- `state/sensor/device_id/unit`: TEXT (kısa, indexlenmesi gerekenler)

**SQLite pragma'lar (`engine.py` engine factory'de set):**
- `journal_mode=WAL` (Write-Ahead Log — concurrent read while write)
- `synchronous=NORMAL` (FULL overkill prototip için; NORMAL crash safety var)
- `foreign_keys=ON` (Faz 2'de FK yok ama prensip için)

---

## 8. Batch Yazma Mantığı (Iter 2.3)

**Buffer:** `threading.Queue` (paho callback'ler background thread'den çağrıldığı için thread-safe queue gerek; asyncio.Queue thread-safe değil paho'yla doğrudan uyumlu değil).

**Drainer:** Ayrı thread (`threading.Thread(target=drain_loop)`) — koşullar:
1. Buffer ≥ `batch_max_size` (örn. 100) → hemen flush
2. Son flush'tan beri ≥ `batch_flush_interval_s` (örn. 1.0s) → flush
3. Shutdown event set → son bir flush + thread çıkar

**Pseudocode:**
```python
def drain_loop(queue, repository, shutdown_event, max_size, flush_interval_s):
    buffer = []
    last_flush = time.monotonic()
    while not shutdown_event.is_set():
        try:
            reading = queue.get(timeout=0.1)
            buffer.append(reading)
        except Empty:
            pass
        now = time.monotonic()
        if len(buffer) >= max_size or (buffer and now - last_flush >= flush_interval_s):
            repository.insert_batch(buffer)
            buffer.clear()
            last_flush = now
    # Final flush
    if buffer:
        repository.insert_batch(buffer)
```

**Performance hedefi:** 1000 msg/sec × max 1s flush latency = en kötü 1000 mesaj/batch. SQLAlchemy Core `connection.execute(insert, [...rows])` PER-batch atomic transaction. SQLite WAL mode ~5000-10000 insert/sec ev hardware'da rahatlıkla yapar.

**Final flush kuyruğu da boşaltır (düzeltme):** Yukarıdaki pseudocode shutdown'da yalnız `buffer`'ı flush eder — ama kuyrukta `queue.get()` edilmemiş mesajlar kalabilir. Veri kaybını önlemek için drainer, while döngüsünden çıkınca önce kuyruğu tamamen `get_nowait()` ile `buffer`'a boşaltır, sonra flush eder. Bu bitti kriteri 3'ün (SIGTERM → kalan mesajlar yazılır) gereğidir.

---

## 9. Migration Mekanizması

**Yalın script-based** (Alembic değil):

`migrations/` klasörü altında `NNN_description.sql` dosyaları (3 haneli zero-padded). `migrator.py` shape:

```python
def apply_migrations(engine: Engine, migrations_dir: Path) -> None:
    """schema_version tablosunu kontrol et, eksik migration'ları uygula."""
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"))
        applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_version")).all()}
    
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version in applied:
            continue
        sql = sql_file.read_text()
        with engine.begin() as conn:
            conn.execute(text(sql))
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :t)"),
                {"v": version, "t": _now_iso()},
            )
        logger.info("Migration applied: {}", sql_file.name)
```

**Çok-statement SQL dosyaları:** Bir `.sql` dosyası birden fazla statement içeriyorsa (örn. `001_initial.sql` = CREATE TABLE + CREATE INDEX), `conn.execute(text(sql))` tek statement çalıştırır (pysqlite driver davranışı) — kalan statement'lar sessizce atlanır. Bu yüzden migrator dosyayı `;` ile statement'lara böler ve her birini ayrı `conn.execute(text(stmt))` ile çalıştırır (DDL için string-literal `;` riski yok).

**Test:** `tests/unit/test_storage_migrator.py` — boş db → apply → tablo var, version=1; tekrar apply → no-op (version aynı, INSERT atılmaz).

---

## 10. Config Dosyaları

| Dosya | Sorumluluk |
|---|---|
| `config/mqtt.yaml` | Broker bağlantısı (Faz 1'den mevcut, ingestion da okur) |
| `config/ingestion.yaml` | YENİ: subscribe topic pattern, db_path, batch params, log level |

`config/ingestion.yaml.example`:

```yaml
ingestion:
  db_path: data/telemetry.db
  subscribe_topic_pattern: telemetry/+/+
  batch:
    max_size: 100
    flush_interval_s: 1.0
  log_level: INFO
```

`.example` dosyası repo'da; gerçek `ingestion.yaml` `.gitignore`'da.

---

## 11. Hata Yönetimi

CLAUDE.md kuralı: `except Exception:` yasak. Spesifik tipler.

| Hata | Davranış | Gerekçe |
|---|---|---|
| Config dosyası yok / `yaml.YAMLError` | Erken çık (exit 2), Loguru ERROR + dosya yolu | Boot-time hata gizlenmez |
| Şema validation hatası (`KeyError`, `ValueError`) | Erken çık, eksik/yanlış alanı mesajda göster | Dataclass __post_init__ doğrular |
| MQTT broker boot-time bağlanamıyor | Loguru WARN + retry, exponential backoff max 30 s | Broker geç açılıyor olabilir |
| MQTT runtime disconnect | paho `reconnect_delay_set` ile otomatik (Iter 2.3) | Servis ayağa kalkmalı |
| Bozuk JSON payload (`json.JSONDecodeError`) | Loguru ERROR + msg payload (max 200 char) + skip | Bir bozuk mesaj servisi çökertmesin |
| Eksik/yanlış field (`KeyError`, `TypeError`) | Loguru ERROR + skip | Aynı gerekçe |
| SQLite IO error (`sqlite3.OperationalError`) | Loguru CRITICAL + 5 sn bekle, batch'i yeniden dene; 3 başarısız sonra exit | Disk dolu/locked durumu — sessiz kabul edilemez |
| Migration başarısız (`sqlite3.OperationalError`) | Erken çık (exit 3), Loguru CRITICAL + SQL satırı | Bozuk şema durumu derhal bildirilmeli |
| Batch drainer thread crash | Loguru CRITICAL, ana servis SIGTERM tetikler (kendi kendine restart için systemd) | Kuyruktan tüketim durmamalı; yarım çalışmaktansa öl |
| SIGINT / SIGTERM | Shutdown event set, paho `loop_stop` + `disconnect`, drainer son flush, exit 0 | Temiz kapanma; data kaybı yok |

**Iter 2.3 resilience kapsamı (minimal):** Batch drainer'da `insert_batch` `OperationalError` fırlatırsa: CRITICAL log + bounded retry (varsayılan 3 deneme, aralarında `retry_backoff_s` bekleme). Tüm denemeler başarısızsa: CRITICAL log + `BatchWriter.failed = True` + `shutdown_event.set()` → ana servis graceful kapanır (kalıcı disk-full/locked durumunda buffer kaybı kaçınılmaz; loglanır). Tablodaki tam "5 sn bekle + 3x retry + sonra exit 3" ve "drainer crash → ana servise SIGTERM" process-orchestration'ı Faz 9+ production sertleştirmesine ertelendi (prototip için bounded-retry + graceful-shutdown sinyali yeterli).

---

## 12. Test Stratejisi

### Klasör Yapısı

```
tests/
├── unit/                    # Hızlı, mocklu (paho mock, in-memory SQLite)
├── integration/             # Engine + repository uçtan uca, mock paho + tmp dosya SQLite
├── scenarios/               # Faz 1'den, ingestion'a dokunmaz
└── smoke/                   # YENİ kategori — gerçek Mosquitto, CI dışı
```

### Unit Test Prensipleri

- **Subscriber:** paho mock + `on_message` callback fire → parse_message çağrıldı + log basıldı
- **Parser:** geçerli/bozuk JSON, eksik field, yanlış type — her birinde beklenen davranış
- **Repository:** SQLite `:memory:` + insert/insert_batch/select roundtrip
- **Migrator:** boş db → apply → version=1; tekrar apply → no-op
- **Batch writer:** mock queue + mock repository → flush koşulları (size/time/shutdown) ayrı ayrı test edilir

### Integration Test

- wired message handler (`_make_message_handler(repository)`) + `tmp_path` dosya SQLite engine; N sahte `MQTTMessage` doğrudan handler'a fire edilir (paho/run() loop'u test edilmez — sinyal/thread izolasyonu unit kapsamı dışı). N mesaj sonrası SQL'de N satır, `timestamp` sırası korunmuş, restart'ta migration tekrar koşmaz
- 100 mesaj → SQL'de 100 satır var, sıra korunmuş (Iter 2.2'de tek-tek insert; batch flush Iter 2.3)

### Smoke Test (CI dışı)

- Gerçek Mosquitto broker + ayrı simulator subprocess + ingestion subprocess
- 60 saniye boyunca 1000 msg/sec yük altında: simulator publish sayısı ≈ SQL satır sayısı (±1%)
- `pytest tests/smoke/ -v` lokal manuel çağrı

**Opt-in çift kapı:** Smoke testleri default `pytest tests/` run'ında SKIPPED'tir. Çalışması için hem `RUN_SMOKE=1` env değişkeni set olmalı HEM de broker `localhost:1883`'te erişilebilir olmalı (aksi halde skip). Süre `SMOKE_DURATION_S` env ile ayarlanır (default 5s hızlı doğrulama); spec § 13'ün tam 60s/60.000-mesaj kabul run'ı `SMOKE_DURATION_S=60 RUN_SMOKE=1 pytest tests/smoke/` ile manuel çalıştırılır. `smoke` pytest marker'ı kayıtlıdır (`--strict-markers`). Smoke testinde ingestion in-process kurulur (subscriber + batch_writer), yapay paho publisher hedef hızda yayın yapar (subprocess yerine — daha hızlı + deterministik teardown).

**Kriter 1 (kayıpsız yük) yapay publisher ile:** spec § 13 Yaklaşım A — 60-cihazlı simulator yerine test fixture'ında yapay 1000 msg/sec publisher kullanılır (simulator'ı ölçeklemek YAGNI). Kriter 4 ile aynı mekanizma; ikisi tek throughput testiyle karşılanır.

**Kriter 2 (broker restart → reconnect) doğrulaması:** otomatik kill/restart testi kırılgan olduğu için mekanizma (paho `reconnect_delay_set(1, 30)`) unit testle, gerçek broker-restart davranışı dokümante manuel adımla doğrulanır.

### Kapsama

`pytest --cov=src/ingestion --cov=src/storage` her iterasyon sonunda ≥%85.

---

## 13. Performance Hedefi (1000 msg/sec)

ROADMAP § Faz 2 kabul kriteri: "1000 mesaj/saniye yüke dayanabiliyor."

**Mevcut Faz 1 yükü:** 3 cihaz × 6 sensör × 1 Hz = 18 msg/sec (devices.yaml.example default).

**1000 msg/sec için gereken:** ~166 cihaz × 6 sensör × 1 Hz, ya da yapay test fixture publisher. Iter 2.3 smoke test'inde:

**Yaklaşım A (tercih):** `tests/smoke/conftest.py`'de yapay publisher fixture — 1000 msg/sec'lık MQTT publish yapan helper. Simulator'ı 166 cihaza çıkarmak alternatifi var ama YAGNI (simulator demo için 3 cihaz yeterli).

**Bottleneck analizi:**
- paho callback throughput: ~10000 msg/sec rahatça
- json.loads + dataclass construction: ~50000 ops/sec
- SQLite WAL batch insert (100/batch): ~5000 row/sec → 1000 msg/sec batch=100 ile rahat
- Disk I/O: WAL mode + NORMAL sync seviye = SSD'de ~10000 row/sec

Tüm aşamalar 1000 msg/sec hedefini fazlasıyla karşılar.

**Smoke test kabul kriteri:**
- 60 saniye × 1000 msg/sec = 60,000 mesaj publish
- SQL row count ∈ [59,400, 60,000] (≥%99 kayıpsız)
- p99 ingestion latency (publish → SQL committed) < 2 sn

---

## 14. Açık Kararlar (İlerleyen Fazlara Ertelenenler)

| Konu | Faz | Yön |
|---|---|---|
| TimescaleDB'ye geçiş | Faz 9+ | SQLite prototip yeterli; gerçek production yük gelirse |
| Alembic migration framework | Belirsiz | Şu an yalın script yeterli; 5+ migration olunca tekrar değerlendir |
| Authentication / TLS MQTT | Faz 9+ | Lokal ağ varsayımı |
| Multi-process scaling | Faz 9+ | Tek process tek ingestion yeterli (1000 msg/sec sınırın çok altı) |
| Outbox pattern / WAL replication | Faz 9+ | SQLite tek dosya yeterli |
| Schema versioning beyond migration apply (rollback) | Belirsiz | Forward-only şimdilik |

---

## 15. Spec'e Karşı Disiplin

- Bu spec Faz 2 boyunca **tek hakemdir**.
- Spec ile çelişen kod kabul edilmez.
- Spec değişikliği önce bu dosyada yapılır, sonra kod izler.
- Faz 1 spec'i (§ 7 MQTT contract) ingestion için INPUT contract — Faz 2 spec'i bunu değiştiremez (publisher tarafını bozar). Sadece Faz 2 OUTPUT contract'ı (SQL şema) bu spec'in kapsamında.
- Performance hedefleri ROADMAP'ten gelir; spec'i değiştirmek isterse ROADMAP de güncellenir.
- Bir geliştirici (insan veya AI) sayı/karar önerirse, ROADMAP ve Faz 1 spec'iyle çelişmediğini doğrulamadan kabul edilmez.

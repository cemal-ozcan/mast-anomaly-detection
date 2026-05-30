# Faz 4 — Kural Tabanlı Dedektör Tasarım Dokümanı

> Bu doküman Faz 4'ün **tek hakemidir**. Spec ile çelişen kod kabul edilmez. Spec değişikliği önce bu dosyada yapılır, sonra kod izler. Bu spec brainstorming oturumunda (2026-05-30) kararlaştırıldı; **plan + uygulama yeni bir sohbette** (writing-plans → subagent-driven) yapılacak.

---

## 1. Amaç ve Kapsam

Sistemin ilk **anomali tespit katmanı**: domain bilgisinden çıkartılmış deterministik, açıklanabilir kurallarla telemetri penceresinde sapma yakalamak, anomalileri DB'ye yazmak, dashboard'da "aktif uyarılar" göstermek.

**Kuzey Yıldızı:** Çalışan, açıklanabilir, küçük kurallar. Kural katmanı deterministik + hızlı (istatistik/ML Faz 5-6). Sistemin **asıl değeri** burada başlıyor — arıza henüz oluşmadan davranışsal sapmayı yakalamak.

**Kapsam içi (Faz 4):**
- `Detector` ABC + `Anomaly` dataclass (`detect(window: pd.DataFrame) -> list[Anomaly]`, ARCHITECTURE.md § 4)
- Standalone polling dedektör servisi (`python -m detectors`)
- ≥5 kural (eşik / süre / türev / oran / varyans tabanlı), `config/detectors.yaml` ile parametrize
- Anomali tablosu (migration `002`) + repository metodları
- Minimal fusion (aynı device + zaman penceresinde çoklu kural → tek skorlu alert)
- Dashboard "aktif uyarılar" paneli (anomali tablosunu okur)

**Kapsam dışı (sonraki fazlar):**
- İstatistiksel dedektörler (EWMA, 3-sigma, IQR) — Faz 5
- ML dedektörler (Isolation Forest, One-Class SVM) — Faz 6
- Alerts servisi (önceliklendirme, bildirim, ack/resolve) — Faz 5 (Faz 4 yalnız anomaliyi DB'ye yazar + dashboard'da listeler)
- Gelişmiş dashboard görselleri (plotly/anomali overlay/tema) — Faz 4/5 sonrası (kullanıcı kararı 2026-05-30)
- D/E/F senaryolarının simülatöre eklenmesi (simülatör şu an yalnız A/B/C üretir — bkz § 3)

---

## 2. Girdi Gerçeği — Simülatör vs DOMAIN (KRİTİK)

İki gerçek tüm kural/eşik tasarımını şekillendirir:

**(a) Simülatör yalnız A/B/C senaryolarını üretir** (Faz 1): MechanicalWear (A), HydraulicLeak (B), ElectricalFault (C). D (aşırı yük), E (sensör arızası), F (sıcaklık aşımı) **simüle EDİLMİYOR**. Sonuç: **acceptance-test sinyali yalnız A/B/C'den gelir**. D/E/F için universal kural yazılabilir (overtemp threshold, sensor frozen/impossible) ama simülatörle imza-test edilemez — yalnız birim test (sentetik pencere) ile doğrulanır.

**(b) Ölçek uyumsuzluğu:** DOMAIN fiziksel değerler verir (motor akımı 5-15A); simülatör kendi sentetik ölçeğinde üretir (motor_current baseline ~0.5A, devices.yaml SensorConfig). Eşikler **simülatör çıktısına kalibre** edilmeli ki kurallar gerçekten tetiklensin (kabul kriteri 1). DOMAIN imzaları **yönü/sensörü/state'i** belirler (örn. "motor_current RAISING+HOLDING'de baseline'ın ~%25 üstüne çıkar"); simülatör çıktısı **eşik ölçeğini** belirler.

**Eşik stratejisi (memory feedback ile uyumlu — DOMAIN truth source, hand-picked sabitten kaçın):** Kurallar mümkün olduğunca **state-baseline'a relatif** ifade edilir (örn. `value > state_baseline * ratio`, `slope < -threshold`, `rolling_std > k`) ve `config/detectors.yaml`'dan okunur. Baseline'lar config'ten (simülatörün bilinen SensorConfig baseline'ları) veya pencere içi referanstan türetilir. Eşikler Iter 4.2'de simülatörün normal-vs-arıza çıktısı ölçülerek ayrılma noktasına kalibre edilir (istatistiksel imza testleriyle doğrulanır — Faz 1 scenario imza testi deseni).

---

## 3. İterasyon Planı

**Iter 4.1 — Walking Skeleton (Detector arayüzü + Anomali persistence + 1 kural + servis):**
- `src/detectors/base.py`: `Anomaly` frozen dataclass + `Detector` ABC (`detect(window) -> list[Anomaly]`, `name` property).
- `src/storage/`: `migrations/002_anomalies.sql` (anomalies tablosu + index) + repository `insert_anomaly` / `fetch_recent_anomalies`.
- İlk kural (örn. `MotorTemperatureHigh` — basit threshold, deterministik) `src/detectors/rules/`.
- Runner servisi: `src/detectors/service.py` (poll loop) + `src/detectors/__main__.py` (`python -m detectors`). Periyodik `fetch_window` → her aktif dedektör → anomali persist. Signal handler + graceful shutdown (ingestion deseni).
- **Bitti:** `python -m detectors` çalışırken bir cihazın motor_temperature eşiği aşınca anomali DB'ye yazılır; birim test (sentetik window → Anomaly) + integration (tmp DB).

**Iter 4.2 — Kural Seti + Config + İmza Testleri:**
- ≥5 kural, ROADMAP tip dağılımı (eşik / süre / türev / oran / varyans). Aday set (§ 5).
- `config/detectors.yaml(.example)` + `src/detectors/config.py` loader (eşikler/parametreler; hangi kurallar aktif).
- A/B/C **imza testleri**: simülatör senaryosu + dedektör → ilgili kural tetiklenir; normal veri → tetiklenmez (FP). Faz 1 scenario-imza testi deseni (scipy/eşik).
- Eşik kalibrasyonu: normal-vs-arıza ayrımı (config'e yazılır).

**Iter 4.3 — Fusion + Dashboard Alerts Paneli + FP Doğrulama:**
- Minimal fusion: aynı `(device_id, zaman penceresi)`'de tetiklenen çoklu kural → tek alert (katkıda bulunan kural listesi + toplam/maks skor). Gürültü azaltma.
- Dashboard: "Aktif Uyarılar" paneli (`fetch_recent_anomalies` ile son anomaliler tablosu; cihaz/severity/sensör/zaman). `src/dashboard/app.py`'ye eklenir (gözlem modu korunur).
- FP-oranı doğrulama: normal veri akışında saatte birkaç adetten az yanlış pozitif (kabul kriteri 4) — smoke/manuel.

---

## 4. Mimari ve Dosya Düzeni

```
src/detectors/
├── __init__.py
├── __main__.py              # python -m detectors entry (ince)
├── base.py                  # Anomaly dataclass + Detector ABC
├── config.py                # detectors.yaml loader (DetectorConfig)
├── service.py               # poll loop: fetch_window → detect → persist (run() + signal)
└── rules/
    ├── __init__.py          # kural registry (RULE_REGISTRY)
    ├── motor_temperature_high.py
    ├── motor_current_high.py
    ├── hydraulic_pressure_decline.py
    ├── motor_voltage_erratic.py
    ├── vibration_elevated.py
    └── (universal: sensor_frozen / impossible_value)

src/storage/
├── migrations/002_anomalies.sql   # YENİ: anomalies tablo + index
└── repository.py                  # MODIFY: insert_anomaly + fetch_recent_anomalies

src/dashboard/app.py               # MODIFY (Iter 4.3): aktif uyarılar paneli
config/detectors.yaml.example      # YENİ: kural eşikleri/parametreleri + aktif kurallar
tests/unit/, tests/integration/, tests/scenarios/   # kural birim + A/B/C imza testleri
```

İsimlendirme notu: detektör servisi `service.py` (storage/engine.py + simulator/engine.py ile karışmasın). Poll loop run() deseni ingestion `__main__.run()`'a paralel.

---

## 5. Veri Modelleri

### Anomaly (detectors/base.py)
```python
@dataclass(frozen=True)
class Anomaly:
    device_id: str
    rule_name: str            # tetikleyen kural (örn. "motor_temperature_high")
    sensor: str               # ilgili sensör
    severity: str             # "info" / "warning" / "critical" (config-driven)
    score: float              # 0-1 normalize (fusion için)
    window_start: str         # ISO 8601 ms (pencere başı)
    window_end: str           # ISO 8601 ms (pencere sonu / tespit anı)
    value: float              # tetikleyen değer (örn. tepe akım)
    description: str          # insan-okur açıklama (örn. "motor_current %28 baseline üstü")
```

### Detector ABC
```python
class Detector(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def detect(self, window: pd.DataFrame) -> list[Anomaly]: ...
```
`window`: tek cihazın son N saniyelik okumaları, kolonlar `[timestamp, sensor, state, value]` (long format) — runner `fetch_window` çıktısından kurar. Kurallar ilgili sensör(ler)i filtreler.

### anomalies tablosu (002_anomalies.sql)
```sql
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    sensor TEXT NOT NULL,
    severity TEXT NOT NULL,
    score REAL NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    value REAL NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anomalies_device_created ON anomalies (device_id, created_at);
```
Idempotent yazma: aynı (device, rule, window) anomalisi tekrar yazılmasın diye runner dedup eder (in-memory "son yazılan" takibi) — basit; gelişmiş dedup Faz 5.

---

## 6. Aday Kural Seti (≥5, Iter 4.2)

DOMAIN imzalarına dayalı, A/B/C testable işaretli:

| Kural | Tip | Sensör/Mantık | DOMAIN | Test |
|---|---|---|---|---|
| `motor_current_high` | eşik + süre | motor_current state-baseline'ın `ratio`× üstünde, `min_duration_s` boyunca | A, D | A imza ✓ |
| `hydraulic_pressure_decline` | türev | HOLDING'de pressure eğimi `< -slope_threshold` (bar/dk) | B | B imza ✓ |
| `motor_voltage_erratic` | varyans | pencere içi voltage `std > std_threshold` | C | C imza ✓ |
| `vibration_elevated` | oran | vibration baseline'ın `ratio`× üstünde | A | A imza ✓ |
| `motor_temperature_high` | eşik | motor_temperature `> critical_threshold` | F | birim (universal) |
| `sensor_frozen` | süre | bir sensör `N` örnek boyunca aynı değer (donmuş) | E | birim (universal) |

İlk 4 simülatör A/B/C ile imza-test edilir; son 2 universal (birim test). Kesin eşikler `config/detectors.yaml`'da, Iter 4.2 kalibrasyonuyla.

---

## 7. Runtime / Servis (detectors/service.py)

Poll loop (ingestion `run()` deseni):
1. Config + engine + repository kur (`create_sqlite_engine`, `TelemetryRepository`).
2. Aktif dedektörleri registry'den + config'ten kur.
3. Loop: her `poll_interval_s`'de (config), her cihaz (`list_devices`) için son `window_s` pencereyi (`fetch_window` per sensör → birleştir) al, her dedektörü çalıştır, dönen anomalileri (dedup sonrası) `insert_anomaly` ile yaz. Fusion (Iter 4.3) yazımdan önce birleştirir.
4. SIGINT/SIGTERM → graceful shutdown.

Gözlem modu (CLAUDE.md): yalnız okur + anomali yazar; hiçbir cihazı yönetmez, komut göndermez.

---

## 8. Hata Yönetimi

CLAUDE.md: spesifik exception, `except Exception` yasak, loguru.

| Durum | Davranış |
|---|---|
| Config yok / geçersiz | Erken çık + loguru ERROR + dosya yolu |
| Bir kural `detect` içinde hata (`KeyError`/`ValueError`) | O kuralı atla + loguru ERROR; servis + diğer kurallar sürer (bir kural diğerlerini düşürmesin) |
| Boş pencere (cihazda veri yok) | Sessiz skip |
| SQLite okuma/yazma `OperationalError` | loguru ERROR; bounded retry (ingestion deseni) |
| SIGINT/SIGTERM | Graceful shutdown |

---

## 9. Test Stratejisi

- **Birim:** her kuralın `detect(window)`'u — sentetik pandas window (tetikleyen + tetiklemeyen), beklenen Anomaly. `Detector` ABC, config loader, repository (`insert_anomaly`/`fetch_recent_anomalies`).
- **İmza (scenarios):** simülatör A/B/C senaryosu + ilgili kural → tetiklenir; normal veri → tetiklenmez. Faz 1 scenario-imza testi deseni (`tests/scenarios/`).
- **Integration:** tmp DB + sentetik telemetri seed → runner bir tur → anomaliler DB'de.
- **Servis (`service.run()`):** ingestion `run()` gibi ince orchestration — manuel/integration smoke (gerekirse mock).
- **Coverage:** `detectors` paketi ≥%85 (servis run() loop hariç tutulabilir, ingestion deseni).
- Her task sonunda tam suite + mypy + ruff (src/detectors + tests dahil).

---

## 10. Kabul Kriterleri (ROADMAP § Faz 4)

1. Simülatörde bir arıza senaryosu (A/B/C) tetiklendiğinde ilgili dedektör yakalıyor (imza testi + manuel).
2. Anomaliler veritabanına yazılıyor (`sqlite3 ... "SELECT * FROM anomalies"` ile doğrulanır).
3. Dashboard'da "aktif uyarılar" listesi görünüyor (Iter 4.3).
4. Yanlış pozitif oranı kabul edilebilir (normal akışta saatte birkaç adetten az) — FP doğrulama.
5. ≥5 kural (eşik/süre/türev/oran/varyans tipleri). Tüm önceki testler yeşil + yeni testler; mypy + ruff temiz.

---

## 11. İlerleyen Fazlara Ertelenenler

| Konu | Faz |
|---|---|
| İstatistiksel dedektörler (EWMA, 3-sigma, IQR) | Faz 5 |
| ML dedektörler (Isolation Forest, One-Class SVM) | Faz 6 |
| Alerts servisi (önceliklendirme, ack/resolve, bildirim) | Faz 5 |
| Gelişmiş fusion (ağırlıklı skor, çoklu-katman) | Faz 6 |
| D/E/F senaryolarının simülatöre eklenmesi | Belirsiz |
| Dashboard anomali overlay / gelişmiş görsel | Faz 4/5 sonrası |
| ElectricalFault std ratio 22× vs DOMAIN ≈3× — Faz 1 spec § 9 C reconciliation | Faz 4.2 kalibrasyon öncesi değerlendir |

---

## 12. Spec'e Karşı Disiplin

- Bu spec Faz 4 boyunca tek hakemdir.
- Faz 1 (simülatör A/B/C imzaları), Faz 2 (storage/repository), Faz 3 (dashboard) bu fazın **girdi kontratıdır**; Faz 4 bunları okur + genişletir (anomalies tablosu, dashboard paneli), bozmaz.
- Dedektör servisi gözlem modu: hiçbir yazma telemetriye, hiçbir cihaz kontrolü; yalnız `anomalies` tablosuna yazar.
- Eşikler DOMAIN imzalarına dayanır, simülatör çıktısına kalibre edilir; hand-picked sabitlerden kaçınılır (memory feedback).

# Faz 3 — Streamlit Dashboard Tasarım Dokümanı

> Bu doküman Faz 3'ün **tek hakemidir**. Spec ile çelişen kod kabul edilmez. Spec değişikliği önce bu dosyada yapılır, sonra kod izler.

---

## 1. Amaç ve Kapsam

SQLite'a yazılan telemetri verisini **gerçek zamanlı görsel olarak** takip edebilmek. Teknisyen/yönetici bir cihaz seçer, sensörlerinin son X dakikadaki davranışını grafiklerde görür, sayfa otomatik yenilenir.

**Kuzey Yıldızı:** Çalışan, anlaşılır, basit bir dashboard. Streamlit = saf Python, frontend framework'üne girmeyiz (CLAUDE.md). Bu faz **kritik psikolojik milestone'dur** (ROADMAP): bu noktadan sonra elde "çalışan, görülebilir bir sistem" olur.

**Kapsam içi:**
- `src/dashboard/` paketi: `app.py` (Streamlit entry) + `transform.py` (saf helper'lar)
- `TelemetryRepository`'ye iki okuma metodu: `list_devices()`, `fetch_window(device_id, sensor, since)`
- Tek sayfa: sidebar'da cihaz selectbox + zaman-aralığı selectbox; ana alanda 6 sensör line chart'ı (2 kolon)
- Otomatik yenilenme: `st.experimental_fragment(run_every="2s")` (Streamlit 1.36 API; 1.37+'da `st.fragment`)
- Boş/eksik veri durumunda dostça mesaj

**Kapsam dışı (YAGNI — gerekirse önce konuşulur):**
- Multi-page navigation (3 cihaz için tek sayfa + selectbox yeterli)
- Plotly (native `st.line_chart` yeterli; plotly requirements'ta var ama kullanılmaz)
- Custom CSS/JS / frontend framework
- Streamlit `AppTest` (presentation layer manuel smoke ile doğrulanır)
- Alarm/anomali görselleştirmesi (Faz 5+ alerts henüz yok)
- Veri downsampling (prototip veri hacmi küçük; "tümü" yavaşlarsa Faz 9+ polish)

---

## 2. Mimari ve Dosya Düzeni

```
src/
├── storage/
│   └── repository.py            # MODIFY: list_devices() + fetch_window() read metodları
└── dashboard/                   # YENİ paket
    ├── __init__.py
    ├── app.py                   # Streamlit entry: streamlit run src/dashboard/app.py
    └── transform.py             # saf helper'lar: window_to_since, readings_to_frame

tests/
└── unit/
    ├── test_storage_repository.py        # MODIFY: list_devices + fetch_window testleri
    └── test_dashboard_transform.py        # YENİ: window_to_since + readings_to_frame

pyproject.toml                   # MODIFY: packages.find include "dashboard*"
```

**Sorumluluk ayrımı:**
- `transform.py` — saf fonksiyonlar, Streamlit/DB bilmez (tam test edilebilir)
- `repository.py` — sadece SQL okuma (storage'ın tek okuma yüzeyi; Faz 4 dedektörler de kullanır)
- `app.py` — ince presentation/wiring layer (config + engine + repository + transform + Streamlit render)

---

## 3. Veri Akışı

```
simulator → ingestion → SQLite (data/telemetry.db, WAL)
                                      │ (eşzamanlı okuma — WAL concurrent read)
                                      ▼
                          dashboard: read-only sorgular
```

Dashboard ingestion'ın yazdığı **aynı** `data/telemetry.db` dosyasını okur. SQLite WAL modu yazma sürerken eşzamanlı okumaya izin verir (Faz 2 § 7 pragma). Dashboard `engine.connect()` ile read transaction açar.

**db_path kaynağı:** `config/ingestion.yaml`'dan `load_ingestion_config(...).db_path` ile okunur (aynı DB; config-driven, hardcode yok). Test/dev kolaylığı için opsiyonel `DASHBOARD_DB_PATH` env override: set ise onu, değilse ingestion.yaml db_path'ini kullan.

---

## 4. Storage Okuma API'si (`TelemetryRepository`)

Mevcut `insert`, `insert_batch`, `count`, `fetch_recent`'e ek olarak iki read metodu:

```python
def list_devices(self) -> list[str]:
    """telemetry tablosundaki distinct device_id'leri sıralı döndürür.

    Returns:
        Alfabetik sıralı cihaz kimlikleri (veri yoksa boş liste).
    """
    # SELECT DISTINCT device_id FROM telemetry ORDER BY device_id

def fetch_window(
    self, device_id: str, sensor: str, since: str | None
) -> list[IngestedReading]:
    """Bir cihaz+sensör için `since`'ten itibaren okumaları timestamp ASC döndürür.

    Args:
        device_id: Cihaz kimliği.
        sensor: Sensör adı.
        since: ISO 8601 ms cutoff string (YYYY-MM-DDTHH:MM:SS.sssZ) veya None (tümü).
            timestamp >= since olan satırlar döner.

    Returns:
        Eskiden yeniye (ASC — grafik için) sıralı IngestedReading listesi.
    """
    # since None: SELECT ... WHERE device_id=? AND sensor=? ORDER BY timestamp ASC
    # since var: ... AND timestamp >= ? ORDER BY timestamp ASC
```

**Index:** Composite index `(device_id, sensor, timestamp)` her iki sorguyu da (eşitlik + range + sıra) optimal karşılar (Faz 2 § 7).

**`fetch_recent` vs `fetch_window`:** `fetch_recent` limit-tabanlı (DESC, son N), `fetch_window` zaman-tabanlı (ASC, since'ten beri). Dashboard grafik için zaman ekseni ister → `fetch_window`. İkisi de korunur.

---

## 5. Transform Helper'ları (`transform.py`)

Saf, test edilebilir; Streamlit/DB import etmez.

### Zaman aralığı → cutoff

```python
WINDOW_OPTIONS: dict[str, timedelta | None] = {
    "Son 5 dakika": timedelta(minutes=5),
    "Son 15 dakika": timedelta(minutes=15),
    "Son 1 saat": timedelta(hours=1),
    "Tümü": None,
}

def window_to_since(now: datetime, window: str) -> str | None:
    """Seçili pencere etiketinden ISO 8601 ms cutoff string üretir.

    Cutoff formatı publisher ile AYNI olmalı (YYYY-MM-DDTHH:MM:SS.sssZ) ki SQL'deki
    lexicographic `timestamp >= since` karşılaştırması doğru çalışsın.

    Args:
        now: Şimdiki UTC zaman (test için enjekte edilir).
        window: WINDOW_OPTIONS anahtarlarından biri.

    Returns:
        ISO ms cutoff string, veya "Tümü"/bilinmeyen pencere için None.
    """
    delta = WINDOW_OPTIONS.get(window)
    if delta is None:
        return None
    cutoff = now - delta
    return cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
```

**KRİTİK:** Cutoff `...Z` formatında (ms çözünürlük, `+00:00`→`Z`). Publisher (`src/simulator/publisher.py:_now_iso`) telemetri timestamp'lerini bu formatta üretir; aynı sabit-genişlik format lexicographic sıralanabilir, dolayısıyla string `>=` karşılaştırması zaman karşılaştırmasıyla birebir örtüşür. `now` UTC-aware `datetime` olmalı (`isoformat` `+00:00` üretsin).

### Okumalar → DataFrame

```python
def readings_to_frame(readings: list[IngestedReading]) -> pd.DataFrame:
    """IngestedReading listesini st.line_chart için DataFrame'e çevirir.

    Args:
        readings: timestamp ASC sıralı okumalar.

    Returns:
        timestamp (datetime index) + value kolonlu DataFrame. Boş liste → boş DataFrame
        (timestamp, value kolonlarıyla).
    """
    # Boş: pd.DataFrame(columns=["timestamp", "value"]) → set_index("timestamp")
    # Dolu: timestamp string → pd.to_datetime, value float; timestamp index, value kolon
```

Boş girdi boş ama doğru-şemalı DataFrame döndürür (st.line_chart boş frame'de hata vermez).

---

## 6. Streamlit App (`app.py`)

`streamlit run src/dashboard/app.py` ile çalışır. İnce wiring; mantık transform + repository'de.

**Yapı:**
1. **Resource cache** — engine + repository `@st.cache_resource` ile bir kez kurulur (her 2s rerun'da yeniden açılmaz; connection hijyeni + performans):
   ```python
   @st.cache_resource
   def _get_repository() -> TelemetryRepository:
       db_path = ...  # DASHBOARD_DB_PATH env veya ingestion.yaml db_path
       engine = create_sqlite_engine(db_path)
       return TelemetryRepository(engine)
   ```
2. **Sidebar:** başlık + cihaz selectbox (`repository.list_devices()`) + zaman-aralığı selectbox (`WINDOW_OPTIONS` anahtarları, default "Son 15 dakika").
3. **Ana alan — auto-refresh fragment:**
   ```python
   @st.experimental_fragment(run_every="2s")  # Streamlit 1.36; 1.37+ → st.fragment
   def _render_charts(repository, device_id, window) -> None:
       since = window_to_since(datetime.now(UTC), window)
       cols = st.columns(2)
       for i, sensor in enumerate(SIX_SENSORS):
           readings = repository.fetch_window(device_id, sensor, since)
           frame = readings_to_frame(readings)
           with cols[i % 2]:
               st.subheader(sensor)
               st.line_chart(frame, y="value")
   ```
   `SIX_SENSORS` = sabit 6 sensör adı listesi (motor_current, motor_voltage, hydraulic_pressure, motor_temperature, mast_position, vibration — DOMAIN.md / Faz 1 § 6).
4. **Boş durumlar:**
   - Hiç cihaz yok (`list_devices()` boş) → `st.info("Henüz veri yok — simulator + ingestion çalışıyor mu?")`, fragment render etme.
   - Seçili pencere boş ama cihazda veri var → grafik boş görünür; üstte küçük bir not opsiyonel (polish, zorunlu değil — "Tümü" escape hatch).

**Zaman penceresi semantiği:** Pencere wall-clock UTC `now`'a görelidir ("son 15 dakika" = şu andan geriye). Simulator + ingestion canlı çalışırken bu sezgiseldir. Veri bayatsa (ingestion durmuşsa) dar pencereler boş görünebilir; **"Tümü"** seçeneği her zaman mevcut veriyi gösterir (escape hatch).

---

## 7. Hata Yönetimi

CLAUDE.md: `except Exception` yasak, spesifik tipler.

| Durum | Davranış | Gerekçe |
|---|---|---|
| DB dosyası yok | Streamlit `st.error` + "DB bulunamadı: {path}; ingestion çalıştı mı?" | Boot-time net mesaj |
| Tablo boş / cihaz yok | `st.info("Henüz veri yok ...")` | Servis çökmez, kullanıcı yönlendirilir |
| Seçili pencere boş | Boş grafik + opsiyonel not | Normal durum, hata değil |
| `sqlite3.OperationalError` (okuma) | `st.error` + log | Disk/lock; sessiz kabul edilmez |

Dashboard **gözlem modu**dur (CLAUDE.md): hiçbir şey yazmaz, hiçbir cihazı yönetmez.

---

## 8. Test Stratejisi

| Birim | Test | Nasıl |
|---|---|---|
| `transform.window_to_since` | Her pencere → doğru cutoff (format `...Z`, ms); "Tümü" → None; bilinmeyen → None | Enjekte edilmiş sabit `now` (datetime, UTC) |
| `transform.readings_to_frame` | Boş → boş ama doğru-şemalı frame; dolu → timestamp index + value kolon, sıra korunur | Sahte IngestedReading listesi |
| `repository.list_devices` | Boş db → []; çok cihaz → distinct + alfabetik sıralı | `migrated_engine` fixture + insert |
| `repository.fetch_window` | since=None → tümü (ASC); since=cutoff → sadece >= cutoff; device/sensor filtresi; ASC sıra | `migrated_engine` + bilinen timestamp'li satırlar |

`app.py` (Streamlit script) ince presentation layer — **manuel smoke** ile doğrulanır (`streamlit run` + canlı simulator/ingestion + grafik <2s yük + cihaz/pencere değişimi). Bu, Faz 2'deki `__main__.run()` orchestration'ının manuel-smoke ile doğrulanması pattern'iyle tutarlı. `AppTest` (streamlit.testing) prototip için karmaşıklık/flakiness getirdiğinden ertelenir.

**Coverage:** `transform.py` + yeni repository metodları ≥%85. `app.py` coverage hedefe dahil edilmez (script, manuel doğrulanır) — gerekirse pytest cov ölçümünde `app.py` omit edilir veya hedef ingestion+storage+transform üzerinden değerlendirilir.

**mypy/ruff:** `src/dashboard` hedeflere eklenir. `transform.py` temiz tiplenebilir (pandas 2.2 py.typed). `app.py`'de Streamlit dinamik API'si gerekirse gerekçeli `# type: ignore[...]` (minimum) kullanılabilir; ruff temiz olmalı.

---

## 9. Kabul Kriterleri (ROADMAP § Faz 3)

1. `streamlit run src/dashboard/app.py` ile başlatılır, hata vermeden açılır.
2. Simulator + ingestion çalışırken canlı veri görselleşir (cihaz seçilir, 6 sensör grafiği görünür).
3. Sayfa otomatik yenilenir (`st.experimental_fragment run_every`), her grafik 2 saniyenin altında yüklenir.
4. Zaman-aralığı selectbox çalışır (5dk/15dk/1saat/tümü); "Tümü" mevcut tüm veriyi gösterir.
5. Boş db / cihaz yok durumunda dostça mesaj, çökme yok.
6. Unit testler (transform + repository read) ≥%85 coverage; tüm önceki testler yeşil; mypy + ruff temiz.
7. Yöneticiye sunulabilir kalite (temiz layout, sensör başlıkları, okunaklı grafikler).

---

## 10. İlerleyen Fazlara Ertelenenler

| Konu | Faz | Yön |
|---|---|---|
| Plotly zengin grafikler (hover, eksen/birim kontrolü) | Belirsiz | Native line_chart yeterli; "sunulabilir kalite" yetmezse |
| Veri downsampling ("Tümü" çok büyürse) | Faz 9+ | Prototip veri hacmi küçük |
| Multi-page navigation | Belirsiz | Cihaz sayısı artarsa |
| Anomali/alarm overlay | Faz 5+ | Alerts servisi geldiğinde |
| Streamlit AppTest otomasyonu | Belirsiz | Presentation layer manuel yeterli |
| Pencere "son veri timestamp'ine göreli" modu | Belirsiz | Şu an wall-clock now; "Tümü" escape hatch yeterli |

---

## 11. Spec'e Karşı Disiplin

- Bu spec Faz 3 boyunca tek hakemdir.
- Faz 1 spec'i (§ 7 MQTT payload → telemetri timestamp formatı `...Z`) ve Faz 2 spec'i (SQLite şema, repository) bu fazın **girdi kontratıdır**; Faz 3 bunları değiştiremez (sadece okur + repository'ye read metodu ekler).
- Dashboard gözlem modu: hiçbir yazma, hiçbir cihaz kontrolü.

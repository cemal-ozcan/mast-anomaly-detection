# Mimari — Sistem Tasarımı

Bu doküman sistemin teknik mimarisini detaylı anlatır. CLAUDE.md ana brifingdir, bu dosya o brifingin teknik derinleştirilmesidir.

---

## Genel Felsefe

Sistem **olay güdümlü, gevşek bağlı, modüler** bir mimaride tasarlandı. Her servis kendi sürecinde çalışır, diğer servislere doğrudan bağımlı değildir, iletişim mesaj kuyruğu üzerinden olur. Bu mimari endüstriyel telemetri sistemleri için olgun ve standarttır.

Tek bir cihazda da çalışır, dağıtık ortamda da çalışır. İlk aşamada her şey tek bir geliştirme makinesinde (M1 MacBook) çalışacak, mimari aynı kalır.

---

## Katmanlar

Sistem altı katmandan oluşur. Veri katmanlar arasında tek yönlü akar.

### 1. Simulator Katmanı (`src/simulator/`)

Sentetik telemetri üretir. Gerçek teleskopik mast davranışını fiziksel kurallarla modeller: motor akımı, hidrolik basınç, sıcaklık, pozisyon, titreşim gibi sensörlerin zaman serisi değerlerini üretir.

İki mod destekler: **normal mod** (sağlıklı cihaz davranışı), **arıza mod** (önceden tanımlı arıza senaryoları). Bu sayede dedektörler etiketli veri üzerinde test edilebilir.

Çıktı: MQTT broker'a `telemetry/<device_id>/<sensor>` topic'ine JSON formatında yayın.

### 2. Ingestion Katmanı (`src/ingestion/`)

MQTT broker'a abone olur, gelen mesajları doğrular, veritabanına yazar. Hız sınırı, batch yazımı, hata yönetimi burada.

Tek sorumluluğu: **veriyi güvenilir şekilde diske düşürmek.** Hiçbir analiz yapmaz, hiçbir karar vermez.

### 3. Storage Katmanı (`src/storage/`)

SQLite veritabanı şeması, repository pattern ile erişim katmanı. Zaman serisi tabloları, anomali tabloları, cihaz metadata tabloları burada.

Şema migration'ları için basit bir versiyon takip mekanizması (`schema_version` tablosu).

### 4. Detector Katmanı (`src/detectors/`)

Anomali tespit motorunun kalbi. Üç alt katmandan oluşur:

**Kural tabanlı (`rules/`):** Domain bilgisinden çıkartılmış eşik ve mantık kuralları. Örnek: "motor akımı 15A'yi 5 saniyeden uzun aşarsa alarm", "mast yükselme süresi referans değerin %30 üzerine çıkarsa alarm". Deterministik, açıklanabilir, hızlı.

**İstatistiksel (`statistical/`):** Her sensörün geçmiş davranışının istatistiksel modeli (ortalama, standart sapma, çeyrekler, EWMA). Yeni değer modelin çok dışındaysa işaretlenir. 3-sigma kuralı, IQR yöntemi, hareketli ortalama sapması gibi yöntemler.

**Makine öğrenmesi (`ml/`):** Etiketsiz öğrenme (unsupervised) yöntemleri. Isolation Forest başlangıç için, ileride One-Class SVM veya LSTM Autoencoder. Model normal davranışı öğrenir, sapmayı işaretler.

Her dedektör aynı arayüzü uygular: `detect(window: pd.DataFrame) -> List[Anomaly]`. Bu sayede dedektörler kolayca eklenip çıkarılır.

### 5. Alert Katmanı (`src/alerts/`)

Dedektörlerden gelen ham anomalileri **yönetilebilir uyarılara** dönüştürür. Sorumlulukları:

**Füzyon:** Aynı zaman penceresinde birden fazla dedektör tetiklediyse tek bir uyarıya birleştir. Skoru artır.

**Debouncing:** Aynı anomali her saniye tekrarlıyorsa her seferinde uyarı üretme. Akıllı zaman pencereleri.

**Önceliklendirme:** Şiddete göre kritik/yüksek/orta/düşük sınıflandırma.

**Kalıcılık:** Uyarılar veritabanına yazılır, dashboard'da görünür hale gelir.

### 6. Dashboard Katmanı (`src/dashboard/`)

Streamlit ile yazılmış görselleştirme. Sayfalar:

**Filo Sayfası:** Tüm cihazların sağlık durumu, son uyarılar.

**Cihaz Detay:** Bir cihazın sensör grafikleri, anomali geçmişi.

**Uyarı Listesi:** Aktif ve geçmiş uyarılar, filtreleme.

**Sistem Sağlığı:** Pipeline'ın kendi sağlığı (ne kadar veri akıyor, dedektörler ne kadar gecikme ile çalışıyor).

---

## Veri Akışı

```
[Simulator] --MQTT--> [Mosquitto Broker] --MQTT--> [Ingestion]
                                          \
                                           \---> [Detector]
                                                     |
                                                     v
                                              [Alert Manager]
                                                     |
                                                     v
[Dashboard] <---SQL--- [SQLite DB] <---write--- [Ingestion + Alert]
```

Veri akışında iki paralel abone vardır: Ingestion (kayıt amaçlı) ve Detector (analiz amaçlı). İkisi birbirinden bağımsız çalışır.

---

## Konfigürasyon

Tüm yapılandırma `config/` klasöründe YAML dosyalarında tutulur:

`config/devices.yaml` — Simüle edilecek cihazlar ve sensör listesi
`config/detectors.yaml` — Dedektör eşikleri ve parametreleri
`config/mqtt.yaml` — MQTT broker bağlantı bilgileri
`config/storage.yaml` — Veritabanı yolu, retention politikası

Sırlar (parolalar gibi) `.env` dosyasında, kod tabanına commit edilmez.

---

## Hata Yönetimi ve Dirençlilik

Her servis **çökmeye dirençli** tasarlanır. Servis çöktüğünde otomatik yeniden başlar (development'ta script ile, production'da systemd/Docker ile).

MQTT broker erişilemez olursa servisler bekler ve yeniden bağlanır, çökmez.

Veritabanı erişilemez olursa ingestion verileri lokal bir queue'da tampona alır, broker bağlanır bağlanmaz boşaltır.

Dedektör bir veri penceresinde hata verirse o pencereyi atlar, kendini durdurmaz.

---

## Test Stratejisi

**Unit testler:** Her dedektör, her parser, her repository fonksiyonu için. `tests/unit/`.

**Entegrasyon testler:** Simulator → Ingestion → Storage akışının tek seferlik testi. `tests/integration/`.

**Senaryo testler:** Belirli bir arıza senaryosu üretildiğinde sistemin doğru uyarıyı verdiğini doğrulayan testler. `tests/scenarios/`.

Test verisi her zaman sentetiktir, fixture'larda saklanır, gerçek veri kullanılmaz.

---

## Performans Hedefleri

İlk prototipte gerçekçi hedefler:

- Simulator: 10 cihaz x 10 sensör x 10 Hz = 1000 mesaj/saniye üretebilmeli
- Ingestion: 1000 mesaj/saniyeyi kayıp olmadan yazabilmeli
- Detector gecikmesi: Bir veri penceresinin alınmasından uyarı üretilmesine kadar 5 saniyenin altında olmalı
- Dashboard: Bir cihazın son 24 saatlik grafiği 2 saniyenin altında yüklenmeli

Bu hedefler M1 MacBook'ta rahatlıkla karşılanabilir.

---

## Genişleyebilirlik

Sistem ileride şunları desteklemek üzere tasarlandı:

- Yeni cihaz tipleri (sadece config eklenmesi yeterli olur)
- Yeni sensör tipleri (simulator ve dedektörlere ekleme)
- Yeni dedektör algoritmaları (Detector interface'i implement et)
- Farklı dashboard'lar (Streamlit veya Grafana paralelde)
- Üretim dağıtımı (Docker Compose hazır olduğunda)

Şimdi yapmamalıyız ama ileride mümkün:

- Mesaj kuyruğunu Kafka'ya çıkartmak
- Veritabanını TimescaleDB'ye taşımak
- Dedektörleri ayrı container'lara bölmek
- LLM tabanlı tanı asistanı eklemek (bağımsız bir modül olarak)

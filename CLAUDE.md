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

**Faz 1 — Iterasyon 2: State Machine + Tüm Sensörler** (sıradaki)

- **Spec (tek hakem):** `docs/specs/2026-05-18-faz1-simulator-design.md`
- **Tamamlanan iterasyon:** `docs/plans/2026-05-18-faz1-iterasyon1-walking-skeleton.md` (7/7 task ✅)
- **Yürütme modu:** subagent-driven (her task ayrı subagent + two-stage review)
- **Çalıştırma:** `pip install -e .` editable install gerekli; sonra `python -m simulator` MQTT'ye 1 Hz yayın yapar.

### Iterasyon 1 (Walking Skeleton) — Tamamlandı (2026-05-19)

Çalışan parça: tek `motor_current` sensörü, 1 Hz Gauss gürültülü MQTT yayını, SIGINT/SIGTERM graceful shutdown, 17 unit test (≥84% kapsama). State machine yok, sabit `state="idle"`. Paketleme: `src/simulator/` PEP 660 src layout.

### Iterasyon 2 (sıradaki) — Plan henüz yazılmadı

Kapsam (spec § 3 Iterasyon 2):
- 6 sensör (motor_current, motor_voltage, hydraulic_pressure, motor_temperature, mast_position, vibration)
- `DeviceState` enum + `DeviceRuntimeState` (mutable runtime), state machine transitions
- `BaseSensor` ABC + her sensörün durum-bazlı davranış formülleri
- Sensörler arası implicit korelasyon

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

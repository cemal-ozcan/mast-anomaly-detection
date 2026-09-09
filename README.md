# Industrial Telemetry Anomaly Detection

Endüstriyel teleskopik mast cihazlarından gelen telemetri verisi üzerinde gerçek zamanlı anomali tespiti yapan, açık kaynak temelli bir erken uyarı sistemi.

Bu proje **prototip aşamasındadır** ve tamamen sentetik veri ile çalışır.

## Hedef

Arıza henüz oluşmadan önce davranışsal sapmaları yakalayıp teknisyenlere uyarı üreten bir gözlem sistemi. Sistem iki katmanlı anomali tespiti kullanır: sabit eşiklere dayalı kural tabanlı kontrol ve her cihazın kendi geçmişine göre sapma ölçen istatistiksel katman. Makine öğrenmesi tabanlı bir üçüncü katman (Isolation Forest) değerlendirildi; sentetik veri setinde mevcut iki katmanın kapsamına ek bir değer katmadığı görülünce kapsam dışı bırakıldı.

## Felsefe

**Çalışan, anlaşılır, küçük bir parça; çalışmayan büyük bir sistemden her zaman daha değerlidir.**

Bu proje karmaşıklığa değil, biten parçalara odaklanır. Her faz tamamlandığında gösterilebilir bir çıktı vardır.

## Mimari

Sistem dört bağımsız Python servisinden oluşur; aralarında bir MQTT broker (Mosquitto) aracılık eder. Her servis ayrı bir süreç olarak çalışır — biri çökse diğerleri etkilenmez. Uyarı yaşam döngüsü (açık/onaylanmış/kapanmış) ayrı bir servis değildir, detector süreci içinde yönetilir.

```
[Simulator] -> [MQTT Broker] -> [Ingestion] -> [SQLite]
                            -> [Detector (anomali + uyarı yaşam döngüsü)] -> [SQLite]

[Dashboard] <- [SQLite]  (salt-okuma, gözlem modu)
```

Detay için `docs/ARCHITECTURE.md` dosyasına bakın.

## Tech Stack

Python 3.11+, MQTT (Mosquitto + paho-mqtt), SQLite, Pandas, scikit-learn, Streamlit, pytest. Tamamı açık kaynak. Bulut servisi, dış API, LLM çağrısı yok.

## Kurulum

```bash
# Sanal ortam oluştur (python3.11 önerilir)
python3.11 -m venv .venv
source .venv/bin/activate

# Bağımlılıkları kur (editable install gerekli — modüller `python -m ...` ile çalıştırılıyor)
pip install -r requirements.txt -e .

# Mosquitto broker'ı kur (macOS)
brew install mosquitto

# Yapılandırmayı ayarla
cp .env.example .env
```

## Çalıştırma

**Demo (tek komut):**
```bash
./scripts/demo_up.sh      # tüm servisler + temiz baseline; http://localhost:8501
./scripts/demo_down.sh    # temiz kapat
```
15 dakikalık demo akışı ve sorun giderme: **`docs/DEMO.md`**.

**Manuel servisler** (ayrı terminaller, `PYTHONPATH=src` + `.venv`): `python -m ingestion`, `python -m detectors`, `python -m simulator`, `streamlit run src/dashboard/app.py`. (`alerts` ayrı servis değildir — uyarı yaşam döngüsü detector içinde.)

## Dokümantasyon

- `CLAUDE.md` — Claude Code için proje brifingi
- `docs/DEMO.md` — 15 dakikalık demo runbook (çalıştırma + sorun giderme)
- `docs/ARCHITECTURE.md` — Sistem mimarisi detayı
- `docs/ROADMAP.md` — Faz planı ve milestone'lar
- `docs/DOMAIN.md` — Domain bilgisi (sensörler, arıza senaryoları)
- `docs/SECURITY.md` — Güvenlik kuralları ve prensipleri

## Lisans

MIT

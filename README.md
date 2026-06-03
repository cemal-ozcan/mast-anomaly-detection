# Industrial Telemetry Anomaly Detection

Endüstriyel teleskopik mast cihazlarından gelen telemetri verisi üzerinde gerçek zamanlı anomali tespiti yapan, açık kaynak temelli bir erken uyarı sistemi.

Bu proje **prototip aşamasındadır** ve tamamen sentetik veri ile çalışır.

## Hedef

Arıza henüz oluşmadan önce davranışsal sapmaları yakalayıp teknisyenlere uyarı üreten bir gözlem sistemi. Sistem üç katmanlı anomali tespiti kullanır: kural tabanlı, istatistiksel ve makine öğrenmesi.

## Felsefe

**Çalışan, anlaşılır, küçük bir parça; çalışmayan büyük bir sistemden her zaman daha değerlidir.**

Bu proje karmaşıklığa değil, biten parçalara odaklanır. Her faz tamamlandığında gösterilebilir bir çıktı vardır.

## Mimari

Sistem altı bağımsız servisten oluşur. Servisler MQTT broker üzerinden iletişim kurar, her biri ayrı bir Python süreci olarak çalışır.

```
[Simulator] -> [MQTT Broker] -> [Ingestion]
                            -> [Detector]
                                  |
                                  v
                            [Alert Manager]
                                  |
                                  v
[Dashboard] <- [SQLite] <- [Ingestion + Alert]
```

Detay için `docs/ARCHITECTURE.md` dosyasına bakın.

## Tech Stack

Python 3.11+, MQTT (Mosquitto + paho-mqtt), SQLite, Pandas, scikit-learn, Streamlit, pytest. Tamamı açık kaynak. Bulut servisi, dış API, LLM çağrısı yok.

## Kurulum

```bash
# Sanal ortam oluştur
python3 -m venv venv
source venv/bin/activate

# Bağımlılıkları kur
pip install -r requirements.txt

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

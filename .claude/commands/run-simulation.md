---
description: Tüm sistemi başlat ve simülasyon çalıştır
---

# Simülasyon Çalıştırma

Kullanıcı sistemin tamamını çalıştırıp simülasyon yapmak istiyor.

## Sorulacaklar

1. Hangi senaryo? (normal mod / belirli bir arıza senaryosu)
2. Kaç cihaz simüle edilecek?
3. Ne kadar süre çalışacak? (sınırsız / belirli süre)

## Önkoşullar Kontrolü

1. Mosquitto broker çalışıyor mu? Çalışmıyorsa: `brew services start mosquitto`.
2. Veritabanı şeması güncel mi? Migration gerekiyorsa çalıştır (detector ilk açılışta idempotent migration uygular).
3. Yapılandırma dosyaları mevcut mu? (`config/devices.yaml`, `config/detectors.yaml`) — yoksa `cp config/*.yaml.example config/*.yaml`.

## Çalıştırma Sırası

**En kolay yol — tek komut:** `./scripts/demo_up.sh` (bkz. `docs/DEMO.md`). Tüm servisleri + temiz baseline seed'i başlatır. Kapatma: `./scripts/demo_down.sh`.

**Manuel (ayrı terminaller, `PYTHONPATH=src` + `.venv`):**
1. **Mosquitto** (çalışmıyorsa): `brew services start mosquitto`
2. **Ingestion**: `PYTHONPATH=src .venv/bin/python -m ingestion`
3. **Detector**: `PYTHONPATH=src .venv/bin/python -m detectors`  (kural + istatistik katmanları; `alerts` ayrı servis DEĞİL — uyarı yaşam döngüsü detector içinde)
4. **Simulator** (en son): `PYTHONPATH=src .venv/bin/python -m simulator`  (senaryolar `config/devices.yaml`'da tanımlı; `--scenario` argümanı YOK)
5. **Dashboard**: `.venv/bin/python -m streamlit run src/dashboard/app.py`

> Not: önce `cp config/*.yaml.example config/*.yaml` (gitignored runtime config'ler). Demo için `demo_up.sh` bunu + demo config'lerini otomatik yapar.

## İzleme

- Mosquitto loglarını izle (mesaj akıyor mu)
- Dashboard'u tarayıcıda aç: `http://localhost:8501`
- Anomali tetiklendiğinde dashboard'da görünmeli

## Durdurma

Tüm servisleri durdururken sırayı tersten izle:
1. Simulator'ı durdur (veri akışı kessin)
2. Dashboard, Detector, Ingestion'ı durdur (veya tek komut: ./scripts/demo_down.sh)
3. Mosquitto'yu durdur

## Sorun Giderme

- Veri akmıyor: Mosquitto bağlantısı, topic adları kontrol edilsin
- Veri akıyor ama veritabanına yazılmıyor: Ingestion logları kontrol edilsin
- Anomali tespit edilmiyor: Detector eşik değerleri kontrol edilsin, simulator senaryosu doğru mu

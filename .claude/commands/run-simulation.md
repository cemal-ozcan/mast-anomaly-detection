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

1. Mosquitto broker çalışıyor mu? Çalışmıyorsa başlat.
2. Veritabanı şeması güncel mi? Migration gerekiyorsa çalıştır.
3. Yapılandırma dosyaları mevcut mu? (`config/devices.yaml`, `config/detectors.yaml`, `config/mqtt.yaml`)

## Çalıştırma Sırası

Servisleri aşağıdaki sırayla başlat (her birini ayrı bir terminal/process'te):

1. **Mosquitto** (henüz çalışmıyorsa): `mosquitto -c config/mosquitto.conf`

2. **Ingestion**: `python -m src.ingestion`

3. **Detector**: `python -m src.detectors`

4. **Alert Manager**: `python -m src.alerts`

5. **Dashboard**: `streamlit run src/dashboard/app.py`

6. **Simulator** (en son başlat, böylece diğerleri hazır olsun): `python -m src.simulator --scenario <senaryo>`

## İzleme

- Mosquitto loglarını izle (mesaj akıyor mu)
- Dashboard'u tarayıcıda aç: `http://localhost:8501`
- Anomali tetiklendiğinde dashboard'da görünmeli

## Durdurma

Tüm servisleri durdururken sırayı tersten izle:
1. Simulator'ı durdur (veri akışı kessin)
2. Dashboard, Alert, Detector, Ingestion'ı durdur
3. Mosquitto'yu durdur

## Sorun Giderme

- Veri akmıyor: Mosquitto bağlantısı, topic adları kontrol edilsin
- Veri akıyor ama veritabanına yazılmıyor: Ingestion logları kontrol edilsin
- Anomali tespit edilmiyor: Detector eşik değerleri kontrol edilsin, simulator senaryosu doğru mu

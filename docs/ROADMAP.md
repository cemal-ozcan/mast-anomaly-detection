# Yol Haritası — Faz Planı

Bu doküman projenin fazlarını ve her fazın kabul kriterlerini tanımlar. Bir fazın kabul kriterleri karşılanmadan bir sonraki faza geçilmez.

---

## Faz 0 — Kurulum

**Durum:** Tamamlandı

**İçerik:** Proje klasör yapısı, dokümantasyon, Claude Code yapılandırması, slash komutları.

**Çıktı:** Bu dosya yapısı.

**Kabul kriteri:** `CLAUDE.md`, `docs/`, `.claude/commands/` ve `src/` klasör iskeleti hazır.

---

## Faz 1 — Simulator

**Hedef:** Sentetik telemetri üreten cihaz simülatörünü yazmak.

**Kapsam:**
- Tek bir cihaz tipi simüle eden Python servisi
- En az 5 sensör (motor akımı, hidrolik basınç, sıcaklık, pozisyon, titreşim)
- Normal mod: fiziksel olarak makul, gürültülü ama sağlıklı zaman serileri
- Arıza modu: en az 3 farklı arıza senaryosu (her biri farklı sensör imzası bırakır)
- MQTT broker'a yayın
- Yapılandırma dosyasından cihaz ve sensör tanımları okuma

**Kabul kriteri:**
- `python -m simulator` çalıştırıldığında MQTT'ye veri akmaya başlar
- `mosquitto_sub` ile mesajlar görüntülenebilir
- Yapılandırmadan arıza senaryosu seçilip tetiklenebilir
- Unit testler %80 üstü kapsama oranıyla geçer

---

## Faz 2 — Ingestion ve Storage

**Hedef:** MQTT'den gelen veriyi güvenilir şekilde SQLite'a yazmak.

**Kapsam:**
- MQTT abone servisi
- SQLite şema tanımı (telemetri tabloları)
- Repository pattern ile veri erişim katmanı
- Batch yazma optimizasyonu
- Şema migration mekanizması

**Kabul kriteri:**
- Simulator çalışırken Ingestion veriyi kayıpsız yazıyor
- SQL sorgusu ile veri doğrulanabiliyor
- 1000 mesaj/saniye yüke dayanabiliyor
- Servis çöktüğünde otomatik yeniden başlıyor

**İlerleme:**
- ✅ Iter 2.1 — Walking skeleton (MQTT subscriber + console log) — Tamamlandı 2026-05-29
- ✅ Iter 2.2 — SQLite + repository pattern + script-based migration — Tamamlandı 2026-05-30
  (`telemetry` wide tablo + composite index + `TelemetryRepository.insert`; 155 test, %86.8 ingestion+storage coverage)
- ⏳ Iter 2.3 — Batch writer + resilience (reconnect backoff) + 1000 msg/sec smoke testi (sıradaki)

Detay: `docs/specs/2026-05-29-faz2-ingestion-storage-design.md`.

---

## Faz 3 — Basit Dashboard

**Hedef:** Veriyi görsel olarak takip edebilmek.

**Kapsam:**
- Streamlit dashboard
- Cihaz listesi sayfası
- Cihaz detay sayfası (sensör grafikleri, son 24 saat)
- Otomatik yenilenme

**Kabul kriteri:**
- `streamlit run dashboard/app.py` ile başlatılır
- Simulator çalışırken canlı veri görselleşiyor
- Her grafik 2 saniyenin altında yükleniyor
- Yöneticine sunulabilir kalitede

Bu faz **kritik psikolojik bir milestone'dur.** Bu noktadan sonra "çalışan bir sistem" elinde var.

---

## Faz 4 — Kural Tabanlı Dedektör

**Hedef:** İlk anomali tespit katmanını eklemek.

**Kapsam:**
- Dedektör arayüzü (`Detector` abstract class)
- Kural motoru (YAML'den okunur)
- En az 5 farklı kural (eşik, süre, türev, oran tabanlı)
- Anomali objesi ve veritabanı şeması

**Kabul kriteri:**
- Simulator'da bir arıza senaryosu tetiklendiğinde dedektör yakalıyor
- Anomaliler veritabanına yazılıyor
- Dashboard'da "aktif uyarılar" listesi görünüyor
- Yanlış pozitif oranı kabul edilebilir seviyede (saatte birkaç adetten az)

---

## Faz 5 — İstatistiksel Dedektör

**Hedef:** Veriyle "kendi kendine" öğrenen ikinci katman.

**Kapsam:**
- Her sensör için baseline istatistik (ortalama, std, IQR)
- Hareketli pencere (rolling window) bazlı dedektör
- 3-sigma kuralı dedektörü
- IQR tabanlı dedektör
- Baseline'ı zamanla güncelleme mekanizması

**Kabul kriteri:**
- Sistem N saat normal veri gördükten sonra baseline'ı öğreniyor
- Sentetik arızalar yakalanabiliyor
- Kural tabanlı dedektörle tutarlı sonuçlar (overlap analizi)

---

## Faz 6 — Makine Öğrenmesi Dedektörü

**Hedef:** scikit-learn ile Isolation Forest dedektörü.

**Kapsam:**
- Veri ön işleme pipeline'ı (scaling, feature engineering)
- Isolation Forest eğitimi (normal veri üzerinde)
- Model kaydetme/yükleme
- Çoklu sensörlü çok değişkenli anomali tespiti
- Tahmin servisi (real-time)

**Kabul kriteri:**
- Model normal veriden öğreniyor
- Test setinde anomalileri yakalıyor
- Üretim ortamında düşük gecikmeyle çalışıyor (<100ms tahmin başına)

---

## Faz 7 — Alert Manager

**Hedef:** Üç dedektörün çıktısını yönetilebilir uyarılara dönüştürmek.

**Kapsam:**
- Füzyon mantığı (çoklu dedektör tetikleyince tek uyarı)
- Debouncing (tekrar eden uyarıları sustur)
- Önceliklendirme
- Uyarı yaşam döngüsü (yeni, görüldü, kapalı)

**Kabul kriteri:**
- Bir arıza senaryosu birden fazla dedektörü tetiklediğinde tek bir uyarı oluşuyor
- Dashboard'da uyarı durumu yönetilebiliyor
- Yanlış pozitif oranı önceki fazlara göre düşüyor

---

## Faz 8 — Pilot ve Demo

**Hedef:** Gösterilebilir, biten bir prototip.

**Kapsam:**
- Birkaç gerçekçi senaryo demo edilebilir hale getir
- Dokümantasyon tamamla
- Sunum materyali hazırla
- Bilinen sınırlamaları belgele

**Kabul kriteri:**
- Yöneticiye/firmaya 15 dakikada gösterilip anlatılabiliyor
- En az 3 farklı arıza senaryosu canlı demo edilebiliyor
- Kod kalitesi review için hazır

---

## Faz 9+ — Genişleme (Stretch Goals)

Stajyerlik süresine ve ilgi durumuna göre opsiyonel:

- Docker Compose ile tüm sistemi paketleme
- TimescaleDB'ye geçiş
- Grafana entegrasyonu
- Çoklu cihaz tipi desteği
- LSTM Autoencoder dedektörü
- Web API (FastAPI)

**Önemli:** Bu fazlara geçmeden önce Faz 8'in **tamamen bitmiş** olması şart. Yarım kalmış büyük vizyondan, biten küçük bir prototip her zaman daha değerli.

---

## Faz Geçiş Disiplini

Bir fazı bitirmiş sayabilmek için:

1. Kabul kriterlerinin **hepsi** karşılanmış olmalı
2. Yazılan kod için unit testler yazılmış olmalı
3. Dokümantasyon güncellenmiş olmalı (özellikle ARCHITECTURE.md değişti ise)
4. Git'te düzgün commit'lerle teslim edilmiş olmalı

Bir fazda takılınca sonraki faza atlamak yerine, takılınan noktayı kullanıcıyla konuşarak çözmek esastır.

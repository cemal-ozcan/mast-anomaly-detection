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

**İlerleme — Faz 2 TAMAMLANDI (2026-05-30):**
- ✅ Iter 2.1 — Walking skeleton (MQTT subscriber + console log) — Tamamlandı 2026-05-29
- ✅ Iter 2.2 — SQLite + repository pattern + script-based migration — Tamamlandı 2026-05-30
  (`telemetry` wide tablo + composite index + `TelemetryRepository.insert`; 155 test, %86.8 ingestion+storage coverage)
- ✅ Iter 2.3 — Batch writer (drainer thread) + resilience (reconnect backoff, bounded retry) + graceful shutdown flush + 1000 msg/sec throughput smoke — Tamamlandı 2026-05-30
  (167 test, %89.2 ingestion+storage coverage; smoke: 1000 msg/sec %0 kayıp)

Tüm kabul kriterleri karşılandı: kayıpsız yazım, SQL doğrulama, 1000 msg/sec yük, reconnect.
Detay: `docs/specs/2026-05-29-faz2-ingestion-storage-design.md`. **Sıradaki: Faz 3.**

---

## Faz 3 — Basit Dashboard ✅ TAMAMLANDI (2026-05-30)

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

**Sonuç:** `src/dashboard/` (transform helper'ları + Streamlit app), `TelemetryRepository` read API (`list_devices` + `fetch_window`). `streamlit run src/dashboard/app.py` → cihaz + zaman-aralığı selectbox, 6 sensör line chart, `st.experimental_fragment` 2s otomatik yenileme. Gözlem modu (read-only). 180 test, headless boot + graceful degradation doğrulandı. **Sıradaki: Faz 4.**

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

**Durum:** ✅ TAMAMLANDI (2026-05-31)

**İlerleme:**
- ✅ Iter 4.1 — Walking skeleton (`Detector` ABC + `Anomaly` + `anomalies` tablosu + repository + 1 kural + `python -m detectors` poll servisi) — 2026-05-30
- ✅ Iter 4.2 — 6 kural (5 tip: eşik/süre/türev/oran/varyans) + `config/detectors.yaml` loader + `build_detectors` + config-driven servis + A/B/C imza testleri + eşik kalibrasyonu — 2026-05-30
- ✅ Iter 4.3 — Write-side fusion (device+pencere çoklu kural → tek `fused(N)` satır) + epizot debounce + dashboard "Aktif Uyarılar" paneli + canlı FP doğrulama — 2026-05-31

**Tüm kabul kriterleri karşılandı:** (1) arıza senaryosu (A/B/C) tetiklendiğinde dedektör yakalıyor (imza testleri + canlı smoke), (2) anomaliler `anomalies` tablosuna yazılıyor, (3) dashboard "Aktif Uyarılar" listesi görünüyor, (4) yanlış pozitif kabul edilebilir (canlı clean cihaz 0 anomali + epizot debounce: 250s kaçak = 1 satır), (5) ≥5 kural (6 kural / 5 tip). 257 test, detectors %96.4, mypy strict + ruff temiz. **Sıradaki: Faz 5.**

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

**Spec (tek hakem):** `docs/specs/2026-05-31-faz5-statistical-detector-design.md` — on-the-fly rolling baseline + aynı servise entegre + tek uzun pencere (recent-vs-rest). 2 iterasyon.

**İlerleme:**
- ✅ Iter 5.1 — İstatistiksel altyapı (`statistical/base` recent-vs-rest split + (sensor,state) gruplama) + `ThreeSigma` (on-the-fly rolling μ±k·σ) + `statistical` config bloğu + poll servisinin iki-pencere'ye (kural 120s + istatistik 3600s) geçişi; istatistik anomalileri kural anomalileriyle `fused(N)`'de birleşir — 2026-05-31. 277 test, statistical %96-100. Canlı smoke: `three_sigma:motor_current` tetiklendi. "Baseline güncelleme mekanizması" on-the-fly rolling ile otomatik.
- ⏳ Iter 5.2 — `IQR` dedektörü + A/B/C istatistiksel imza testleri + **overlap analizi** (kabul kriteri 3: kural ve istatistik aynı arızada tutarlı) — sıradaki

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

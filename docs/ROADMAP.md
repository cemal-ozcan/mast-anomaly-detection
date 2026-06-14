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

**Tüm kabul kriterleri karşılandı (2026-05-31):**
- (1) Sistem ~N saat normal veri sonrası baseline'ı öğreniyor — on-the-fly rolling + abstain (warmup). ✅
- (2) Sentetik arızalar yakalanabiliyor — **A/B doğrudan** (mean/median kayması, imza testleri + canlı smoke); **C (ElectricalFault) bir varyans arızasıdır → merkezi-eğilim dedektörlerine tamamlayıcıdır**: statistical sessiz (tasarım), kural katmanı `motor_voltage_erratic` yakalar. ✅
- (3) Kural tabanlı dedektörle tutarlı (overlap): A'da `motor_current_high` + `three_sigma:motor_current` → `fused(N)`. ✅

**İlerleme:**
- ✅ Iter 5.1 — İstatistiksel altyapı (`statistical/base` recent-vs-rest split + (sensor,state) gruplama) + `ThreeSigma` (on-the-fly rolling μ±k·σ) + `statistical` config bloğu + poll servisinin iki-pencere'ye (kural 120s + istatistik 3600s) geçişi; istatistik anomalileri kural anomalileriyle `fused(N)`'de birleşir — 2026-05-31. 277 test, statistical %96-100. Canlı smoke: `three_sigma:motor_current` tetiklendi. "Baseline güncelleme mekanizması" on-the-fly rolling ile otomatik.
- ✅ Iter 5.2 — `IQR` dedektörü (robust Q1/Q3 ± m·IQR, median) + STATISTICAL_REGISTRY/config + çok-segmentli `build_statistical_window` harness + gelişmiş kaçak fixture + A/B/C istatistiksel imza testleri (C tamamlayıcı) + **overlap analizi** (fused) — 2026-05-31. 293 test, mypy strict + ruff temiz. Canlı smoke: `fused(2)` (`three_sigma:motor_current` + `iqr:motor_current`), clean cihaz 0 FP. İmza eşikleri gerçek simülatör çıktısıyla ölçülerek kalibre edildi; durağan-değil sensörler (mast_position/motor_temperature) `sensors=[...]` ile harness artefaktından dışlandı.

**Faz 5 ✅ DONE. Sıradaki: Faz 6 — ML dedektörler.**

---

## Faz 6 — Makine Öğrenmesi Dedektörü ⏸️ ERTELENDİ (stretch)

> **Karar (2026-06-03):** Faz 6 (ML) **atlandı, Faz 9+ stretch'e ertelendi.** Gerekçe (objektif değerlendirme):
> simülatör yalnız A/B/C arızası üretiyor ve ikisi de mevcut iki katmanca (kural + istatistik) yakalanıyor →
> Isolation Forest'ın değer önermesi (öngörülmeyen/çok-değişkenli anomali) sentetik veride karşılığı yok;
> aynı generator'dan eğitim+test methodolojik olarak zayıf; ML kalan fazlar içinde en yüksek karmaşıklık /
> en düşük marjinal tespit değeri. Kuzey yıldızı gereği önce yönetilebilir uyarı (Faz 7) + demo (Faz 8).
> ML, gerçek/çeşitli veri geldiğinde ya da minimal on-the-fly versiyonla ileride değerlendirilir.

**Hedef (ertelendi):** scikit-learn ile Isolation Forest dedektörü.

**Kapsam (ertelendi):** Veri ön işleme pipeline'ı; Isolation Forest eğitimi; model kaydetme/yükleme;
çok-değişkenli anomali; tahmin servisi.

**Kabul kriteri (ertelendi):** Model normal veriden öğreniyor; test setinde anomali yakalıyor; <100ms/tahmin.

---

## Faz 7 — Alert Manager ✅ DONE (2026-06-03)

**Hedef:** Dedektörlerin çıktısını yönetilebilir uyarılara dönüştürmek.

**Kapsam:**
- Füzyon mantığı (çoklu dedektör tetikleyince tek uyarı) — ✅ Faz 4.3'ten (`fuse_anomalies`)
- Debouncing (tekrar eden uyarıları sustur) — ✅ Faz 4.3'ten (epizot debounce)
- Uyarı yaşam döngüsü (yeni→görüldü→kapalı) — ✅ Iter 7.1
- Önceliklendirme — ⏸️ ertelendi (kapsam dışı; istenirse Iter 7.2)

**Tüm kabul kriterleri karşılandı (2026-06-03):**
- (1) Bir arıza birden fazla dedektörü tetiklediğinde tek uyarı (`fused(N)`) — ✅ regresyon korundu.
- (2) Dashboard'da uyarı durumu yönetilebiliyor — ✅ Iter 7.1: active→acknowledged→resolved, ack/resolve butonları + durum filtresi + detector auto-resolve + canlı smoke.
- (3) Yanlış pozitif/gürültü oranı düşüyor — ✅ (dürüst çerçeve): auto-resolve + resolved'ı varsayılan görünümden çıkarma gürültüyü azaltır; ham FP'yi Faz 4 debounce düşürmüştü; açık önceliklendirme/suppression ertelendi.

**İlerleme:**
- ✅ Iter 7.1 — migration 003 (`anomalies` status/acknowledged_at/resolved_at) + saf `src/alerts/` paketi (lifecycle + Alert) + repository ack/resolve/resolve_open/fetch_alerts (atomik SQL WHERE) + detector `_detect_once` auto-resolve (re-arm) + dashboard durum kolonu/filtre/yönetim (fragment dışı) — 2026-06-03. 308 test, mypy strict + ruff temiz. Canlı smoke: arıza→`active`→temizlenme→`resolved` auto-resolve doğrulandı. Spec: `docs/specs/2026-06-03-faz7-alert-manager-design.md`.

**Faz 7 ✅ DONE. Sıradaki: Faz 8 — Pilot/Demo** (Faz 6 ML stretch'e ertelendi).

---

## Faz 8 — Pilot ve Demo (devam ediyor)

**Hedef:** Gösterilebilir, biten bir prototip.

**Kapsam:**
- Birkaç gerçekçi senaryo demo edilebilir hale getir
- Dokümantasyon tamamla
- Sunum materyali hazırla
- Bilinen sınırlamaları belgele
- (Iter 8.2) Dashboard görsel zenginleştirme (KPI, cihaz sağlık, anomali overlay, tema)

**Kabul kriteri:**
- Yöneticiye/firmaya 15 dakikada gösterilip anlatılabiliyor — ✅ Iter 8.1 (`docs/DEMO.md` beat-script + tek-komut `demo_up.sh`)
- En az 3 farklı arıza senaryosu canlı demo edilebiliyor — ✅ Iter 8.1 (mechanical_wear + hydraulic_leak + electrical_fault canlı tespit; device_001 temiz 0 FP; kural+istatistik `fused` overlap; auto-resolve)
- Kod kalitesi review için hazır — ✅ (335 test, mypy strict + ruff temiz)

**İlerleme:**
- ✅ Iter 8.1 — Demo orkestrasyon (`scripts/demo_up.sh`/`demo_down.sh` + `seed_demo_baseline.py`) + `config/devices.demo.yaml` (temiz + A/B/C choreographed + kısa-arıza auto-resolve) + `config/detectors.demo.yaml` (reduced baseline + statistical `sensors` daraltma, canlı smoke kalibrasyonu) + `docs/DEMO.md` runbook + run-simulation/README düzeltme — 2026-06-03. Canlı demo smoke: 0 FP + ≥3 senaryo + overlap + auto-resolve doğrulandı. `src/` değişmedi. Spec: `docs/specs/2026-06-03-faz8-iter8-1-demo-orchestration-design.md`.
- ✅ Iter 8.2 — Dashboard görsel zenginleştirme (komuta merkezi: KPI `st.metric` + filo sağlık kartları renk-kodlu rozet/state/değer + grafik üstü Altair anomali overlay [bant + kural etiketi + hover/zoom] + `.streamlit/config.toml` açık kurumsal tema + cihaz-özeti uyarı akışı [Iter 8.1 flicker yumuşatma]) — 2026-06-14. Streamlit-native (yeni saf modüller `dashboard/fleet.py` + `dashboard/charts.py`; `storage.fetch_latest_readings` read-only, gözlem modu korundu). 335 test + mypy strict + ruff temiz; canlı veri smoke (pencere-içi 0 FP, auto-resolve, 4-katman overlay, downsample 32k→1000). Spec/plan: `docs/specs/2026-06-03-faz8-iter8-2-dashboard-visual-design.md` + `docs/plans/2026-06-03-faz8-iter8-2-dashboard-visual.md`. **Not:** proje bu iterasyonda iCloud-bozulması nedeniyle `~/Desktop`'tan iCloud-dışı `~/Projects/`'e taşındı (CLAUDE.md altyapı dersi).

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

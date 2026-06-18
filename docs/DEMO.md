# Demo Runbook — Teleskopik Mast Anomali Tespiti (Faz 8)

15 dakikada uçtan-uca: 2-katmanlı tespit (kural + istatistik) + füzyon + yönetilebilir uyarı yaşam döngüsü.

## Önkoşullar
- Python venv: `python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt -e .`
- Mosquitto (macOS): `brew install mosquitto`
- Boş portlar: 1883 (MQTT), 8501 (dashboard).

## Tek Komutla Çalıştırma
```bash
./scripts/demo_up.sh          # 5 süreç + temiz baseline seed; mosquitto'yu gerekiyorsa başlatır
# Tarayıcı: http://localhost:8501
./scripts/demo_down.sh        # temiz kapat (mosquitto'ya dokunmaz)
```
`demo_up.sh` `config/devices.yaml` ve `config/detectors.yaml`'ı demo sürümleriyle DEĞİŞTİRİR (eskisini `.bak`'a yedekler) ve `data/telemetry.db`'yi `data/telemetry.db.pre-demo`'ya arşivler. Loglar: `logs/demo/`.

## Cihaz ve Senaryo Tablosu

| Cihaz | Senaryo | Arıza Kodu | Beklenen Uyarı | Açıklama |
|---|---|---|---|---|
| device_001 | temiz | — | *(uyarı yok)* | 0 FP referansı; tüm demo boyunca sessiz kalır |
| device_002 | mechanical_wear | A | `motor_current_high` | Mekanik aşınma → motor akımı tırmanışı → birleşik kural+istatistik tespiti |
| device_003 | hydraulic_leak | B | `hydraulic_pressure_decline` | Hidrolik sızıntı → basınç düşüşü → kural-katmanı tespiti |
| device_004 | electrical_fault | C | `motor_voltage_erratic` | Elektriksel arıza → voltaj titreşimi → kural-katmanı tespiti (varyans arızası; istatistik kör, kural tamamlar) |
| device_005 | temperature_overshoot | F | `motor_temperature_high` | Sıcaklık kritik eşiğe (95°C) tırmanış. Gerçekçi termal model: normal ~40-75°C, kritik 95°C. Erken termal teşhis. |
| device_006 | sensor_fault | E | `sensor_out_of_range` | mast_position aralıklı imkânsız değer (−500mm) → anında yakalama. Sağlamlık göstergesi: bozuk sensöre dayanıklıyız (makine sağlam, sensör bozuk). |

**Demo çerçevesi:** 4 kestirimci arıza (A/B/C/F) + 1 sağlamlık özelliği (E) + temiz referans (device_001).
- **F (termal aşırı ısınma):** erken teşhis — sıcaklık alarm eşiğine ulaşmadan önce trendleri tespit et.
- **E (sensör bütünlüğü):** kestirimci bakım değil, veri-kalitesi/sağlamlık doğrulaması — makine iyi, veri bozuk, sistem bunu ayırt eder.

## 15 Dakikalık Akış (beat-by-beat)
1. **t≈0-60s — Temiz izleme:** Dashboard'da 6 sensör akar, "Uyarılar" boş. Mimariyi anlat: simulator → ingestion → SQLite → kural+istatistik dedektör → fusion → alert lifecycle → dashboard. (İstatistik baseline seed'den hazır.)
2. **t≈60-120s — Kural tespiti:** device_002 (mechanical_wear) → `motor_current_high` `active` uyarı. device_003 (hydraulic_leak) → `hydraulic_pressure_decline`. device_004 (electrical_fault) → `motor_voltage_erratic`. device_001 temiz kalır (FP yok).
3. **t≈90-180s — İki-katman overlap (GEÇİCİ fırsat penceresi):** device_002'de istatistik (`iqr:motor_current` / `three_sigma:motor_current`, +`iqr:vibration`) katılır → `fused(N)` (ör. canlı smoke: `motor_current_high(9.65) + iqr:motor_current(9.96) + vibration_elevated(0.42)`; kural+istatistik aynı arızayı corroborate eder). **Not:** istatistik on-the-fly rolling baseline kullanır; arıza onset'inden kısa süre sonra (current fault-dominant, baseline hâlâ temiz) tetiklenir ve alert kalkınca debounce ile kalır — overlap'i arıza belirir belirmez gösterin. İstatistik yalnız durağan sensörlere daraltıldı (`sensors: [motor_current, vibration, hydraulic_pressure]`); electrical_fault'ta istatistik SESSİZ — varyans arızası kural-katmanı işi (tamamlayıcılık). Overlap görünmezse: kural-katmanı tespiti zaten sağlam; istatistik üretimde ~1 saat baseline ile çalışır (bkz. Bilinen Sınırlar).
4. **t≈120-180s — Termal tırmanış (device_005 / F):** Dashboard grafiğinde `motor_temperature` dramatik yükseliş; ~95°C eşiğini geçtiğinde `motor_temperature_high` uyarısı açılır. Anlatı: "Sıcaklık trendi daha ilk dakikada görünür — bakım müdahalesi için zaman penceremiz var." (Termal model gerçekçi: normal 40-75°C, kritik 95°C — ani sıçrama değil, kademeli tırmanış.)
5. **t≈120-180s — Sensör bütünlüğü (device_006 / E):** mast_position değeri aralıklı olarak −500mm (fiziksel olarak imkânsız) düşer → `sensor_out_of_range` uyarısı **anında** açılır. Anlatı: "Makine sağlam, sensör bozuk — sistem ikisini ayırt ediyor. Bozuk veriye körü körüne güvenmiyoruz." Sağlamlık özelliği olarak vurgula (kestirimci bakım değil).
6. **Yaşam döngüsü (Iter 8.5 — yalnız ACK):** Dashboard'da bir uyarıyı **Gör (ack)** yap (görünümden düşer, açık kalır); durum filtresiyle gez. **Manuel "resolve" YOK** — anlatı: "Çözümü sistem sahiplenir; bir insan canlı gerçek arızayı sessizce kapatamaz. Sensörler temizlenince sistem kendi resolve eder."
7. **t≈3-4dk — Auto-resolve:** device_002 mechanical_wear biter → detector arızanın temizlendiğini görür → uyarı **otomatik `resolved`** (durum filtresinde görünür).

## Skor Anlamı (Iter 8.4 — band-pozisyon)
Tüm dedektörlerde `score` artık **ortak, karşılaştırılabilir** bir band-pozisyondur: **0 = alarm (warn) sınırını yeni geçti, 1 = kritik (trip) seviyesi**. Yani "0.8" her dedektörde aynı şeyi ifade eder (alarm→kritik yolunun %80'i). ISO 20816 bölge (alarm=B/C, trip=C/D) mantığı.
- **Eşik kuralları** (sıcaklık/akım/titreşim/basınç-eğimi/voltaj): trip değerleri gerçek simülatör çıktısıyla kalibre (örn. sıcaklık warn 95°C → trip 130°C).
- **İstatistik** (3σ/IQR): standart çapa — 3σ→6σ, IQR→Tukey far-out (3·IQR). Aşırı sapmada skor **1.0'a satüre** olur (dürüst; gerçekten çok sapmış).
- **Sensör-sağlığı** (`sensor_out_of_range`, `sensor_frozen`): ikili "veri geçersiz" → **skor 1.0** (band-pozisyon değil).
- **Füzyonda** gösterilen skor **temsilci** uyarınınkidir (en-kötü-kazanır; ödünç max yok).

## Bilinen Sınırlar
- **İstatistik üretimde ~1 saat baseline ister** — demo'da seed + reduced `baseline_window_s` (300s) ile canlı gösterilir; overlap GEÇİCİdir (rolling baseline).
- **Faz 6 (ML) atlandı** → Faz 9+ stretch (sentetik veride marjinal tespit değeri düşük).
- **Alert lifecycle (Iter 8.5 — DB-tek-hakikat reconciliation):** Faz 7'nin iki bilinen sınırı **çözüldü**: (1) manuel-resolve divergence'ı yok (P2: manuel resolve kaldırıldı — yalnız ack; çözümü detector sahiplenir); (2) detector restart orphan'ı yok (durum her poll DB'den okunur → restart normal reconciliation yolu). **Korunan (bilinçli, Faz 7 § 2.3):** eskalasyonda cihaz başına >1 açık uyarı (kötüleşme = çözülme değil) — update-in-place Iter 8.6.
- `demo_up.sh` runtime config'leri overwrite eder (`.bak`'tan geri al).
- **Tespit flicker'ı (kozmetik):** arıza gelişirken (ramp) pencere-istatistiği eşiği aralıklı aşar → kural-seti dalgalanır → debounce birkaç resolve/re-arm satırı üretebilir (uyarı listesinde tekrar). Tespit doğru; gürültü kozmetik (Iter 8.2 / ileride yumuşatılabilir).
- **`sensor_frozen` kuralı korunuyor (birim-testli):** donmuş sensörü de tespit ediyoruz — ama canlı demoda gösterilmiyor (device_006 imkânsız-değer senaryosu zaten sağlamlık açısını kapatıyor).
- **D (aşırı yük) bilinçli kapsam dışı:** gerçek bir arıza durumu, ancak tespiti A=mekanik aşınma ile birebir örtüşür (aynı `motor_current_high` imzası) → şişirilmiş sayı yerine net, ayırt edilebilir tespit tercih edildi.

## Sorun Giderme
- **Port dolu (8501/1883):** önceki demo açık olabilir → `./scripts/demo_down.sh`; mosquitto: `brew services list`.
- **ImportError:** `.venv` aktif + `pip install -e .`; launcher zaten `PYTHONPATH=src` kullanır.
- **İki ingestion / mesaj kaybı:** aynı anda tek demo instance (client_id collision). `demo_up.sh` başta eskiyi kapatır.
- **Servis ayağa kalkmadı:** `logs/demo/<servis>.log`'a bak (launcher zaten liveness-check ile erken uyarır).

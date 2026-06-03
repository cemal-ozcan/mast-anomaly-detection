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

## 15 Dakikalık Akış (beat-by-beat)
1. **t≈0-60s — Temiz izleme:** Dashboard'da 6 sensör akar, "Uyarılar" boş. Mimariyi anlat: simulator → ingestion → SQLite → kural+istatistik dedektör → fusion → alert lifecycle → dashboard. (İstatistik baseline seed'den hazır.)
2. **t≈60-120s — Kural tespiti:** device_002 (mechanical_wear) → `motor_current_high` `active` uyarı. device_003 (hydraulic_leak) → `hydraulic_pressure_decline`. device_004 (electrical_fault) → `motor_voltage_erratic`. device_001 temiz kalır (FP yok).
3. **t≈90-180s — İki-katman overlap (GEÇİCİ fırsat penceresi):** device_002'de istatistik (`iqr:motor_current` / `three_sigma:motor_current`, +`iqr:vibration`) katılır → `fused(N)` (ör. canlı smoke: `motor_current_high(9.65) + iqr:motor_current(9.96) + vibration_elevated(0.42)`; kural+istatistik aynı arızayı corroborate eder). **Not:** istatistik on-the-fly rolling baseline kullanır; arıza onset'inden kısa süre sonra (current fault-dominant, baseline hâlâ temiz) tetiklenir ve alert kalkınca debounce ile kalır — overlap'i arıza belirir belirmez gösterin. İstatistik yalnız durağan sensörlere daraltıldı (`sensors: [motor_current, vibration, hydraulic_pressure]`); electrical_fault'ta istatistik SESSİZ — varyans arızası kural-katmanı işi (tamamlayıcılık). Overlap görünmezse: kural-katmanı tespiti zaten sağlam; istatistik üretimde ~1 saat baseline ile çalışır (bkz. Bilinen Sınırlar).
4. **Manuel yaşam döngüsü:** Dashboard'da bir uyarıyı **Gör (ack)**, başkasını **Çöz (resolve)** yap; durum filtresiyle açık/kapalı gez.
5. **t≈3-4dk — Auto-resolve:** device_002 mechanical_wear biter → detector arızanın temizlendiğini görür → uyarı **otomatik `resolved`** (durum filtresinde görünür).

## Bilinen Sınırlar
- **İstatistik üretimde ~1 saat baseline ister** — demo'da seed + reduced `baseline_window_s` (300s) ile canlı gösterilir; overlap GEÇİCİdir (rolling baseline).
- **Faz 6 (ML) atlandı** → Faz 9+ stretch (sentetik veride marjinal tespit değeri düşük).
- **Alert lifecycle (Faz 7 § 9):** süregelen arızayı manuel resolve → kural-seti değişene dek yeni uyarı açılmaz; detector restart / auto-resolve DB hatası → orphan açık uyarı (manuel kapat); eskalasyonda cihaz başına >1 açık uyarı.
- `demo_up.sh` runtime config'leri overwrite eder (`.bak`'tan geri al).
- **Tespit flicker'ı (kozmetik):** arıza gelişirken (ramp) pencere-istatistiği eşiği aralıklı aşar → kural-seti dalgalanır → debounce birkaç resolve/re-arm satırı üretebilir (uyarı listesinde tekrar). Tespit doğru; gürültü kozmetik (Iter 8.2 / ileride yumuşatılabilir).

## Sorun Giderme
- **Port dolu (8501/1883):** önceki demo açık olabilir → `./scripts/demo_down.sh`; mosquitto: `brew services list`.
- **ImportError:** `.venv` aktif + `pip install -e .`; launcher zaten `PYTHONPATH=src` kullanır.
- **İki ingestion / mesaj kaybı:** aynı anda tek demo instance (client_id collision). `demo_up.sh` başta eskiyi kapatır.
- **Servis ayağa kalkmadı:** `logs/demo/<servis>.log`'a bak (launcher zaten liveness-check ile erken uyarır).

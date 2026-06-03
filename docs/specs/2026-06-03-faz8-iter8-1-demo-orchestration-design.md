# Faz 8 Iter 8.1 — Demo Orkestrasyon + Senaryolar + Runbook Tasarım Dokümanı

> Bu doküman Faz 8 Iter 8.1'in **tek hakemidir**. Spec ile çelişen kod kabul edilmez. Spec değişikliği önce bu dosyada yapılır, sonra kod izler. Brainstorming oturumunda (2026-06-03) kararlaştırıldı; **plan + uygulama** writing-plans → subagent-driven ile yapılacak (Faz 4-7 deseni).

---

## 1. Amaç ve Kapsam

Faz 1-7 ile çalışan bir uçtan-uca sistem var (simulator → ingestion → SQLite → kural+istatistik dedektör → fusion → alert yaşam döngüsü → dashboard). Ama **güvenilir bir demo çalıştırma yolu yok**: servisler ayrı terminallerde elle başlatılıyor ve `run-simulation` komut dokümanı gerçeğe uymuyor (çalıştırılabilir `alerts` servisi yok; yanlış `python -m src.*` çağrıları). Faz 8 Iter 8.1, **tek komutla güvenilir bir demo** + choreographed senaryolar (iki tespit katmanı + alert lifecycle canlı) + doğru runbook üretir.

**Kuzey Yıldızı:** Çalışan, açıklanabilir, küçük. Mevcut servisler/config'ler yeniden kullanılır; ince bir bash launcher + demo-özel config'ler + doküman eklenir. Docker YOK (Faz 9+).

**Kapsam içi (Iter 8.1):**
- `scripts/demo_up.sh` / `demo_down.sh`: tek-komut başlat/durdur (5 süreç: mosquitto + ingestion + detectors + simulator + dashboard).
- Temiz baseline **pre-seed** (istatistik katmanı 15-dk demoda güvenilir + erken tetiklensin).
- `config/devices.demo.yaml` (choreographed filo) + `config/detectors.demo.yaml` (reduced baseline) — commit'li.
- `docs/DEMO.md`: 15-dk runbook (beat-by-beat) + bilinen sınırlar + sorun giderme.
- `.claude/commands/run-simulation.md` gerçeğe göre düzeltme + `README.md` doğru çalıştırma/demo işaretçisi.

**Kapsam dışı (Iter 8.2):** dashboard görsel zenginleştirme (KPI, cihaz sağlık kartları, anomali overlay, tema) — ayrı iterasyon.
**Kapsam dışı (genel):** Docker/Compose (Faz 9+), sunum slaytı (DEMO.md beat-script yeterli), Faz 6 ML (atlandı → stretch).

---

## 2. Temel Kararlar (brainstorming çıktısı, 2026-06-03)

1. **Çalıştırma: bash launcher + runbook.** `demo_up.sh`/`demo_down.sh` tek-komut; `docs/DEMO.md` hem yedek hem 15-dk akış. (Python orchestrator ve "yalnız runbook" elendi.)
2. **Demo senaryosu: ayrı `config/devices.demo.yaml`.** `devices.yaml.example` genel referans olarak kalır; demo'ya özel choreographed filo ayrı commit'li dosyada.
3. **İstatistik katmanı CANLI gösterilir.** `config/detectors.demo.yaml` reduced `baseline_window_s`; ayrıca **demo_up temiz baseline'ı pre-seed eder** (uzun gerçek-zamanlı warmup'ın kırılganlığını önler — self-review kararı, Faz 5/7 smoke deseni).
4. **İki iterasyon:** 8.1 orkestrasyon (bu), 8.2 dashboard zenginleştirme (sonra).
5. **Kalibrasyon zorunlu (Faz 5 dersi):** kesin onset/duration/baseline_window_s/seed-hacmi değerleri uygulama sırasında **gerçek çalıştırmayla ölçülerek** ayarlanır; istatistik baseline-sonrası gerçekten tetikleniyor + auto-resolve gerçekten oluyor mu canlı doğrulanır.

---

## 3. Mimari ve Dosya Düzeni

```
scripts/                          # YENİ dizin
├── demo_up.sh                    # launcher: cleanup → mosquitto → config kopya → seed → 4 servis → URL
├── demo_down.sh                  # teardown: pidfile'dan SIGTERM, idempotent
└── seed_demo_baseline.py         # temiz baseline pre-seed (storage repository kullanır)

config/
├── devices.demo.yaml             # YENİ commit'li: temiz + A/B/C choreographed + ≥1 biten arıza
└── detectors.demo.yaml           # YENİ commit'li: detectors.yaml.example + reduced baseline_window_s

docs/DEMO.md                      # YENİ: 15-dk runbook + bilinen sınırlar + sorun giderme
.claude/commands/run-simulation.md # MODIFY: gerçeğe göre düzelt
README.md                         # MODIFY: doğru çalıştırma + demo işaretçisi

tests/unit/test_demo_configs.py   # YENİ: demo config'leri parse + içerik doğrular
```

**Servisler/kod DEĞİŞMEZ.** Iter 8.1 yalnız orkestrasyon + config + doküman + config-doğrulama testi ekler; `src/` altındaki üretim kodu (simulator/ingestion/storage/detectors/alerts/dashboard) **değişmez** (girdi kontratı). Giriş noktaları (`python -m simulator|ingestion|detectors`, `streamlit run`) olduğu gibi kullanılır.

---

## 4. Demo Choreography (15-dk akış, beat-by-beat)

Sürelerin tümü **kalibrasyonla kesinleşir** (§ 2.5); aşağıdaki değerler tasarım hedefidir.

| Beat | ~Zaman | Ne olur / sunucu ne gösterir |
|---|---|---|
| Başlat | t=0 | `./scripts/demo_up.sh` → temiz baseline seed'lenir, 5 süreç ayağa kalkar, dashboard URL yazılır. |
| Temiz izleme | t≈0-60s | Dashboard: akan 6-sensör grafikleri + boş uyarı listesi. Sunucu mimariyi anlatır (3 katman, fusion, lifecycle). İstatistik baseline seed'den HAZIR. |
| Kural tespiti | t≈60-120s | Filoda arızalar başlar: device_002 mechanical_wear → **kural** `motor_current_high` hızlı tetiklenir → dashboard'da `active` uyarı. device_003 hydraulic_leak → `hydraulic_pressure_decline`. device_004 electrical_fault → `motor_voltage_erratic`. |
| İki-katman overlap | t≈120-180s | mechanical_wear'de **istatistik** `three_sigma:motor_current` (+`iqr`) katılır → `fused(N)` (kural+istatistik aynı arızada). electrical_fault'ta istatistik SESSİZ (tamamlayıcı: varyans arızası kural-katmanı işi). |
| Manuel lifecycle | t≈3-5dk | Sunucu dashboard'dan bir uyarıyı **Gör (ack)**, başka birini **Çöz (resolve)** yapar; durum filtresiyle açık/kapalı gezilir. |
| Auto-resolve | t≈4-6dk | En az bir arıza KISA süreli (biter) → detector re-arm → uyarı **otomatik `resolved`** olur, dashboard'da görünür. |
| Kapat | son | `./scripts/demo_down.sh` → temiz kapanış. |

**Net mesaj:** iki-katmanlı tespit (kural hızlı + istatistik öğrenilmiş baseline) + füzyon + yönetilebilir uyarı yaşam döngüsü (manuel + otomatik), uçtan uca canlı, gözlem modu.

---

## 5. Pre-seed (İstatistik-Canlı Güvencesi)

`scripts/seed_demo_baseline.py`: `storage` katmanını kullanarak demo cihazları için **yakın-geçmiş temiz telemetri** (son ~`baseline_window_s` saniye) yazar — her (cihaz, sensör, state) için istatistik dedektörün `min_baseline` eşiğini aşacak kadar örnek. Böylece servisler başlar başlamaz istatistik baseline HAZIR; arıza ~60s'de başlayınca istatistik hızlı tetiklenir (uzun gerçek-zamanlı warmup'a gerek yok). Bu, üretimde "sistem ~1 saattir çalışıyor" durumunu sadık temsil eder.

- demo_up: services'ten ÖNCE seed çalıştırır (DB migration sonrası, simulator başlamadan).
- Seed timestamp'leri `now - baseline_window_s .. now` aralığında (split_recent penceresine düşsün).
- Seed hacmi + (sensor,state) dağılımı **kalibrasyonla** doğrulanır (gerçek çalıştırmada `three_sigma`/`iqr` tetikleniyor mu).
- Seed yalnız `telemetry` yazar (gözlem modu; anomalies'e dokunmaz).

---

## 6. Launcher Mekaniği

**`scripts/demo_up.sh`** (`set -euo pipefail`):
1. **Cleanup-first:** varsa `demo_down.sh`'ı çağır / `data/demo.pids`'teki eski süreçleri kapat → **çift ingestion / client_id collision'ı önle** (`mast-anomaly-subscriber` paylaşımı, memory gotcha).
2. **Mosquitto:** `pgrep -x mosquitto` yoksa başlat (`brew services start mosquitto` ya da `mosquitto -d`); varsa dokunma.
3. **Config'ler:** mevcut runtime `config/devices.yaml`/`config/detectors.yaml` varsa `*.bak`'a yedekle (sessiz clobber yok), sonra `devices.demo.yaml→devices.yaml`, `detectors.demo.yaml→detectors.yaml` kopyala; `config/ingestion.yaml`/`config/mqtt.yaml` yoksa `.example`'dan kopyala.
4. **DB temizliği:** mevcut `data/telemetry.db` varsa `data/telemetry.db.pre-demo`'ya arşivle (tekrarlanabilir demo; sessiz silme yok).
5. **Seed:** `PYTHONPATH=src .venv/bin/python scripts/seed_demo_baseline.py`.
6. **Servisler (sırayla, arka planda):** `ingestion → detectors → simulator → dashboard`; her biri `PYTHONPATH=src .venv/bin/python -m <mod>` (dashboard: `streamlit run src/dashboard/app.py`); PID'ler `data/demo.pids`'e, stdout/stderr `logs/demo/<servis>.log`'a.
7. Dashboard URL'sini (`http://localhost:8501`) ve `demo_down.sh` ipucunu yazdır.

**`scripts/demo_down.sh`** (`set -euo pipefail`, idempotent):
- `data/demo.pids` varsa her PID'e `kill -TERM` (servislerin SIGINT/SIGTERM graceful shutdown'ı var), pidfile'ı sil. Yoksa "zaten kapalı" de, hata verme. **Mosquitto'ya DOKUNMA** (kullanıcının olabilir).

**Env notu:** `.venv/bin/python` + `PYTHONPATH=src` (CLAUDE.md env notu: editable `.pth` silent-skip riskine karşı). `.venv` yoksa launcher anlamlı hata verir.

---

## 7. Config Detayları

**`config/devices.demo.yaml`** — 4 cihaz:
- `device_001`: temiz (senaryosuz) — kontrast, FP yok kanıtı.
- `device_002`: `mechanical_wear` — onset choreography'e göre (~60s); motor_current + vibration yükselir (kural + istatistik).
- `device_003`: `hydraulic_leak` — onset ~60s; hydraulic_pressure düşer (kural türev).
- `device_004`: `electrical_fault` — onset ~60s; motor_voltage varyansı (kural; istatistik sessiz = tamamlayıcı).
- **En az bir arıza KISA `duration_s`** (örn. ~120s) → biter → auto-resolve demo beat'i. (Hangi senaryo: kalibrasyonla; mechanical_wear doğal aday.)
- Kesin `start_after_s`/`duration_s`/`ramp_up_s` **kalibrasyonla**.

**`config/detectors.demo.yaml`** — `detectors.yaml.example` kopyası, tek fark: `statistical.baseline_window_s` düşürülmüş (~120-180s, kalibrasyonla) ki seed'li baseline + reduced pencere ile istatistik demo süresinde tetiklensin. Kural seti + eşikler aynı (üretim kalibrasyonu korunur). `min_baseline`/`min_current` gerekirse demo için düşürülür (kalibrasyon kararı, spec'e not düşülür).

---

## 8. Dokümantasyon

**`docs/DEMO.md`:**
- **Önkoşullar:** `.venv` (`pip install -r requirements.txt -e .`), Mosquitto (homebrew), portlar (1883 MQTT, 8501 dashboard).
- **Tek-komut:** `./scripts/demo_up.sh` → tarayıcıda `http://localhost:8501`; bitince `./scripts/demo_down.sh`.
- **15-dk beat-script:** § 4 tablosu + her beat'te ne söyleneceği/gözleneceği.
- **Bilinen sınırlar:** Faz 7 § 9 (manuel-resolve-süregelen, restart orphan, eskalasyonda >1 açık); ML atlandı (stretch); istatistik üretimde ~1 saat baseline ister (demo'da seed + reduced pencere ile gösterilir); demo_up runtime config'leri overwrite eder (.bak'tan geri al).
- **Sorun giderme:** port dolu, Mosquitto yok, `PYTHONPATH`/`.venv` ImportError, client_id collision (tek demo instance), logs/demo/ nereye bakılır.

**`.claude/commands/run-simulation.md`:** gerçeğe göre düzelt — `python -m src.alerts` KALDIR (alerts çalıştırılabilir servis değil, leaf paket); doğru çağrılar `python -m ingestion|detectors|simulator` (PYTHONPATH=src) + `streamlit run`; demo için `scripts/demo_up.sh`'a yönlendir.

**`README.md`:** "Çalıştırma" bölümünü doğru komutlarla güncelle + "Demo: `./scripts/demo_up.sh` (bkz. `docs/DEMO.md`)".

---

## 9. Test Stratejisi

- **Config-load birim testi** (`tests/unit/test_demo_configs.py`): mevcut simulator devices-config loader'ı `config/devices.demo.yaml`'ı parse eder + 4 cihaz + beklenen senaryolar (mechanical_wear/hydraulic_leak/electrical_fault var, device_001 senaryosuz, ≥1 senaryoda kısa `duration_s`); `detectors.config.load_detector_config(config/detectors.demo.yaml)` parse eder + `statistical.baseline_window_s < 3600` + kural seti dolu. (Loader adları plan tarafından mevcut koddan doğrulanır.) Config typo/şema hatasını yakalar.
- **Launcher sözdizimi:** `bash -n scripts/demo_up.sh scripts/demo_down.sh` (CI yok; task adımı). `shellcheck` varsa çalıştır (yoksa atla).
- **seed script:** küçük + saf-ish; en azından import/`bash -n` benzeri bir "çağrılabilir mi" kontrolü + config-load testiyle dolaylı. (Tam birim testi opsiyonel — storage zaten test edili.)
- **Fonksiyonel doğrulama = controller canlı demo smoke** (asıl kabul gate'i): `demo_up.sh` → 5 süreç up (pid/log kontrol) + dashboard erişilebilir + ≥3 cihazda uyarı (kural) + en az bir `fused` (kural+istatistik overlap) + auto-resolve (`resolved` satır) + `demo_down.sh` temiz kapatır. Faz 5/7 dersi: canlı smoke şart.
- **Coverage:** yeni test edilebilir kod azdır (config doğrulama); orkestrasyon/doküman doğası gereği manuel. mypy/ruff: `test_demo_configs.py` + (varsa) seed script `src/` dışında olduğundan ruff/mypy kapsamına eklenir (`scripts/`).

---

## 10. Kabul Kriterleri (ROADMAP § Faz 8 — Iter 8.1 payı)

1. **Tek komutla çalışır demo:** `./scripts/demo_up.sh` 5 süreci güvenilir başlatır, `demo_down.sh` temiz kapatır (canlı smoke ile kanıtlı).
2. **≥3 arıza senaryosu canlı demo:** mechanical_wear + hydraulic_leak + electrical_fault demo filosunda tespit edilir (kural katmanı), en az birinde kural+istatistik `fused` overlap, biri auto-resolve olur.
3. **15 dakikada anlatılabilir:** `docs/DEMO.md` beat-script + doğru runbook; `run-simulation` skill + README gerçeğe uyumlu.
4. **Bilinen sınırlar belgeli:** DEMO.md'de.
5. Tüm önceki testler yeşil + yeni config testleri; mypy + ruff temiz; `src/` üretim kodu değişmez.

*(ROADMAP § Faz 8'in "dashboard demo-able" ve "sunum materyali" kısmı Iter 8.2 + DEMO.md ile; Iter 8.1 çalıştırma + senaryo + runbook payını karşılar.)*

---

## 11. Bilinen Sınırlar / Riskler (dokümante)

- **İstatistik-canlı kırılganlığı → pre-seed ile çözüldü** (§ 5); yine de seed hacmi/timing kalibrasyon ister (canlı smoke doğrular).
- **Bash launcher taşınabilirliği:** macOS (geliştirme ortamı) hedeflenir; Linux'ta `brew services` farkı olabilir → mosquitto adımı toleranslı (pgrep + fallback), DEMO.md not düşer.
- **Runtime config overwrite:** demo_up `devices.yaml`/`detectors.yaml`'ı değiştirir (.bak yedek + DEMO.md notu).
- **Demo determinizmi:** simülatör seed'li (devices.demo.yaml `seed:`), ama wall-clock onset timing makine hızına çok az duyarlı; canlı smoke'ta doğrulanır.

---

## 12. Spec'e Karşı Disiplin

- Bu spec Faz 8 Iter 8.1 boyunca tek hakemdir.
- Faz 1-7 (tüm servisler + config loader'lar + giriş noktaları) bu iterasyonun **girdi kontratıdır**; Iter 8.1 bunları orkestra eder + demo config/doküman ekler, **`src/` üretim kodunu değiştirmez**.
- Gözlem modu korunur: seed yalnız `telemetry` yazar; demo hiçbir cihaza komut göndermez.
- Kesin sayısal demo parametreleri gerçek çalıştırmayla ölçülür (hand-pick yok — [[feedback_domain_md_truth_source]] ruhu).

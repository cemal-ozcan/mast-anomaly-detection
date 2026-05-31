# Faz 5 — İstatistiksel Dedektör Tasarım Dokümanı

> Bu doküman Faz 5'in **tek hakemidir**. Spec ile çelişen kod kabul edilmez. Spec değişikliği önce bu dosyada yapılır, sonra kod izler. Bu spec brainstorming oturumunda (2026-05-31) kararlaştırıldı; **plan + uygulama** writing-plans → subagent-driven ile yapılacak (Faz 4 deseni).

---

## 1. Amaç ve Kapsam

Dedektör motorunun **ikinci katmanı**: veriden "normal"in modelini öğrenen istatistiksel dedektörler. Kural katmanı (Faz 4) sabit, domain-türevli eşikler kullanır; istatistik katmanı her sensörün **kendi geçmiş davranışından** baseline çıkarır ve sapmaları işaretler. Böylece domain'de önceden tanımlı olmayan davranışsal sapmalar da yakalanır.

**Kuzey Yıldızı:** Çalışan, açıklanabilir, küçük. Eğitim orkestrasyonu / persisted model / ML YOK — on-the-fly rolling baseline (her poll kayan geçmişten yeniden hesap).

**Kapsam içi (Faz 5):**
- İki istatistiksel dedektör: `ThreeSigma` (mean ± k·σ) ve `IQR` (Q1/Q3 ± m·IQR), `Detector` ABC'yi (Faz 4) uygular.
- On-the-fly rolling baseline: cihaz başına uzun pencere (~1h) → (sensor, state)-bazlı robust baseline → güncel tail karşılaştırması.
- Mevcut detector servisine entegrasyon: `config/detectors.yaml`'a `statistical` bloğu; `_detect_once` kural + istatistik dedektörlerini çalıştırıp anomalileri **fusion**'a verir (tek `fused(N)` satır).
- A/B/C istatistiksel imza testleri + **overlap analizi** (kural vs istatistik tutarlılığı).

**Kapsam dışı (sonraki fazlar):**
- ML dedektörler (Isolation Forest, One-Class SVM) — Faz 6.
- Gelişmiş füzyon (ağırlıklı skor, katman-bazlı güven) — Faz 6/7.
- Eğitilmiş + kalıcı baseline (`baselines` tablosu, ayrı eğitim modu) — değerlendirildi, on-the-fly rolling lehine ELENDİ (brainstorming § 2); gerekirse ileride.
- EWMA / artımlı in-memory baseline — elendi (poll-bazlı servise oturmuyor).
- Çevresel bağlam (sıcaklık/nem korelasyonu) — DOMAIN § sonu, ileride.

---

## 2. Temel Kararlar (brainstorming çıktısı, 2026-05-31)

1. **Baseline modeli: on-the-fly rolling.** Eğitim fazı YOK, yeni tablo YOK, persist YOK. Her poll'da uzun pencereden (config `baseline_window_s`) baseline hesaplanır. ROADMAP "baseline güncelleme mekanizması" otomatik (kayan geçmiş). Yeterli geçmiş yoksa dedektör **abstain** eder (warmup → kabul kriteri "N saat sonra öğreniyor"u doğal karşılar). Servis restart'ında kayıp yok (DB'den okur).
2. **Entegrasyon: aynı servis.** Statistical dedektörler `Detector` ABC'yi uygular, `python -m detectors` içinde çalışır, çıktıları aynı `anomalies` tablosuna + fusion'a akar → kural + istatistik anomalileri tek `fused` alert'te birleşir (ARCHITECTURE "katman→fusion").
3. **Pencere mekaniği: tek uzun pencere, recent-vs-rest.** Servis istatistik dedektörlere uzun pencere verir; dedektör içeride baseline (eski) + güncel (tail) olarak böler. **`Detector` ABC DEĞİŞMEZ** (`detect(window) -> list[Anomaly]`); statistical dedektör SAF kalır (timestamp-bazlı split, `now` gerekmez).
4. **Tek `k`/`m`, tüm sensörler.** 3σ/IQR ölçek-bağımsızdır → tek `sigma_k`/`iqr_multiplier` tüm sensörlerde geçerli. Opsiyonel `sensors` filtresiyle daraltılabilir.

---

## 3. İterasyon Planı

**Iter 5.1 — Statistical altyapı + ThreeSigma:**
- `src/detectors/statistical/base.py`: saf baseline helper'ları — `split_recent(window, current_window_s)` (timestamp-bazlı baseline/current ayırma), `(sensor, state)` gruplama, `robust mean/std` hesaplama. Test edilebilir saf fonksiyonlar.
- `src/detectors/statistical/three_sigma.py`: `ThreeSigma(sigma_k, min_baseline, min_current, current_window_s, sensors?, severity)` — `detect(window)` uzun pencereyi böler, (sensor, state) başına baseline μ±k·σ fence, güncel tail mean'i fence dışındaysa `Anomaly`.
- `STATISTICAL_REGISTRY` (`src/detectors/statistical/__init__.py`).
- `src/detectors/config.py`: `StatisticalConfig` (`baseline_window_s`, `current_window_s`, detectors) + `build_statistical_detectors`. `config/detectors.yaml.example`'a `statistical` bloğu.
- `service._detect_once`: cihaz başına KISA pencere (rules, `window_s`) + UZUN pencere (stats, `baseline_window_s`) kurar; iki grup kendi penceresinde çalışır; anomaliler birleştirilir → fusion (mevcut). `run()` her iki dedektör grubunu kurar.
- Birim testler (saf helper'lar + ThreeSigma sentetik pencere).

**Iter 5.2 — IQR + İmza + Overlap:**
- `src/detectors/statistical/iqr.py`: `IQR(iqr_multiplier, min_baseline, min_current, current_window_s, sensors?, severity)` — Q1/Q3/IQR fence, güncel tail median'i dışındaysa `Anomaly`.
- A/B/C **istatistiksel imza testleri** (engine harness): clean baseline + arıza tail → statistical dedektör tetiklenir; clean tail → tetiklenmez.
- **Overlap analizi**: aynı A/B/C arıza penceresinde kural ve istatistik dedektörlerin örtüşmesi (kabul kriteri: tutarlı sonuçlar — ör. MechanicalWear'i hem `motor_current_high` hem `three_sigma:motor_current` yakalar).

---

## 4. Mimari ve Dosya Düzeni

```
src/detectors/
├── statistical/
│   ├── __init__.py          # STATISTICAL_REGISTRY
│   ├── base.py              # saf helper'lar: split_recent, state-partition, robust stats
│   ├── three_sigma.py       # ThreeSigma (Iter 5.1)
│   └── iqr.py               # IQR (Iter 5.2)
├── config.py                # MODIFY: StatisticalConfig + build_statistical_detectors
├── service.py               # MODIFY: _detect_once iki pencere (kısa rules + uzun stats)
├── fusion.py                # DEĞİŞMEZ (mevcut fuse_anomalies kural+istatistik karışık listeyi birleştirir)
└── base.py                  # DEĞİŞMEZ (Detector ABC, Anomaly)

config/detectors.yaml.example # MODIFY: statistical bloğu
tests/unit/detectors/statistical/  # YENİ: birim testler
tests/scenarios/                   # statistical imza + overlap testleri
```

`statistical/` paketi `rules/` ile simetrik (her dedektör tek dosya, registry'de bir satır). `base.py` saf — pandas + numpy, storage/service import etmez.

---

## 5. Baseline Mekaniği

**Recent-vs-rest split.** Uzun pencere (`baseline_window_s`, ~3600s) iki parçaya ayrılır (pencerenin kendi max timestamp'ine göre, `now` gerekmez):
- **Güncel (current)** = `[max_ts − current_window_s, max_ts]` (son ~60s).
- **Baseline** = `[max_ts − baseline_window_s, max_ts − current_window_s]` (geri kalan ~1h). Güncel'i baseline'dan **dışlamak**, gelişen arızanın baseline'ı kirletmesini azaltır.

**(sensor, state)-bazlı.** DOMAIN: aynı sensör değeri state'e göre normal/anormal (motor_current RAISING'de ~8A, HOLDING'de ~0.5A). Her sensör için: güncel tail'de görülen her state için, baseline'da AYNI state'ten ≥`min_baseline` örnek varsa karşılaştır. Güncel tail'de o state'ten ≥`min_current` örnek olmalı (yoksa o (sensor, state) atlanır).

**Robust + agregat.** Güncel tail tek-örnek değil **agregat** ile karşılaştırılır (örüntü-bazlı, DOMAIN § "tekil değil pencere"; ayrıca poll'lar arası flicker'ı önler):
- ThreeSigma: baseline `mean μ`, `std σ` (ddof=1); güncel tail `mean`'i `μ ± sigma_k·σ` dışındaysa → anomali.
- IQR: baseline `Q1`, `Q3`, `IQR=Q3−Q1`; güncel tail `median`'ı `[Q1 − m·IQR, Q3 + m·IQR]` dışındaysa → anomali.

**Durağanlık (stationarity) notu.** 3σ/IQR, (sensor, state) değerlerinin yaklaşık durağan (sabit + gürültü) olduğunu varsayar — motor_current, motor_voltage, vibration, hydraulic_pressure, motor_temperature için geçerli. `mast_position` RAISING/LOWERING'de rampalanır (durağan değil) → baseline varyansı geniş → fence geniş → nadiren tetikler (güvenli/konservatif: FP üretmez, sadece düşük duyarlılık). Gerekirse `sensors` filtresiyle dışlanır. Bu kabul edilebilir minimal davranış; rampalı sensör modellemesi ertelenir.

---

## 6. Dedektör Modelleri

Her ikisi `Detector` ABC (`name` property + `detect(window) -> list[Anomaly]`). Uzun pencereyi alır, § 5'e göre böler/gruplar, sapan her (sensor, state) için bir `Anomaly` döndürür.

**ThreeSigma** — `__init__(sigma_k=3.0, min_baseline=30, min_current=5, current_window_s=60, sensors=None, severity="warning")`. `name="three_sigma"`. Anomali: `rule_name=f"three_sigma:{sensor}"`, `sensor=sensor`, `value=güncel_mean`, `score=min(1.0, (|mean−μ| − sigma_k·σ) / (sigma_k·σ))` (fence dışı aşımın orana normalize, ≥0), `description` baseline/güncel özetler.

**IQR** — `__init__(iqr_multiplier=1.5, min_baseline=30, min_current=5, current_window_s=60, sensors=None, severity="warning")`. `name="iqr"`. Anomali: `rule_name=f"iqr:{sensor}"`, `value=güncel_median`, `score` fence dışı mesafenin IQR'a oranı (≥0, ≤1 clamp), `description`.

**`σ=0` / `IQR=0` korunması:** sabit baseline (örn. motor_voltage gürültüsüz teorik durum) → σ veya IQR 0 olabilir; bu durumda fence sıfır genişlik → herhangi bir fark tetikler. Korunma: σ veya IQR `< _EPSILON` (modül sabiti, `1e-9`) ise o (sensor, state) atlanır (yeterli değişkenlik yok → güvenilir baseline yok). Gerçekte gauss gürültü σ>0 garanti eder ama bu savunmacı kontrol gerekli. (Config param DEĞİL — YAGNI.)

`rule_name` sensörü içerir (`three_sigma:motor_current`) → fusion contributor listesi + debounce/eskalasyon granülaritesi (hangi sensör saptı ayırt edilir).

---

## 7. Config

`config/detectors.yaml`'a yeni `statistical` bloğu (mevcut `detectors`/`rules` bloğunun yanına):
```yaml
statistical:
  baseline_window_s: 3600     # ~1 saat geçmiş baseline
  current_window_s: 60        # son 60s "güncel" pencere
  detectors:
    - name: three_sigma
      enabled: true
      severity: warning
      params: {sigma_k: 3.0, min_baseline: 30, min_current: 5}
    - name: iqr
      enabled: true
      severity: warning
      params: {iqr_multiplier: 1.5, min_baseline: 30, min_current: 5}
```
`current_window_s` config seviyesinde (tüm statistical dedektörlere geçer); `build_statistical_detectors` her dedektörü `RULE`-benzeri `STATISTICAL_REGISTRY[name](severity=..., current_window_s=..., **params)` ile kurar (bilinmeyen ad/bozuk param → ValueError, build_detectors deseni). Opsiyonel `params.sensors: [motor_current, ...]` ile izlenen sensörler daraltılabilir (default: tümü).

---

## 8. Runtime / Servis Entegrasyonu

`_detect_once` cihaz başına **iki pencere** kurar:
1. **Kısa pencere** (`detectors.window_s`, 120s) → kural dedektörleri (Faz 4, değişmez).
2. **Uzun pencere** (`statistical.baseline_window_s`, 3600s) → istatistik dedektörleri.

Her grup kendi penceresinde `detect` çağrılır; dönen anomaliler **tek listede birleştirilir** → mevcut `fuse_anomalies` → epizot debounce → `insert_anomaly`. Yani bir cihazda `motor_current_high` (kural) + `three_sigma:motor_current` (istatistik) aynı turda tetiklenirse → tek `fused(2)` satır (kural+istatistik corroboration).

`run()` hem `build_detectors` (kural) hem `build_statistical_detectors` (istatistik) ile iki grubu kurar; ikisini `_detect_once`'a geçer. Gözlem modu korunur (yalnız telemetry okur, yalnız anomalies yazar). `# pragma: no cover` `run()` gövdesinde kalır; `_detect_once` iki-pencere mantığı birim test edilir.

**Performans notu:** her poll cihaz başına 1h telemetri (≈6 sensör × 3600 satır) sorgulanır. Prototip ölçeğinde (SQLite + composite index, birkaç cihaz) ARCHITECTURE'ın <5s dedektör gecikme hedefi içinde. Erken optimize edilmez (kuzey yıldızı); ileride baseline cache / downsample değerlendirilebilir.

---

## 9. Hata Yönetimi

CLAUDE.md disiplini (spesifik exception, `except Exception` yasak, loguru). Faz 4 deseni korunur:
| Durum | Davranış |
|---|---|
| Yetersiz baseline/current örnek (< min) | O (sensor, state) sessizce atlanır (abstain — warmup veya seyrek state) |
| σ/IQR ≈ 0 (yeterli değişkenlik yok) | O (sensor, state) atlanır (güvenilir fence yok) |
| Bir dedektör `detect` içinde hata (`KeyError`/`ValueError`) | O dedektör atlanır + loguru ERROR; diğerleri sürer (mevcut `_detect_once`) |
| Boş/yetersiz uzun pencere | Sessiz skip |
| Config yok/geçersiz | Erken çık + ValueError (build_detectors deseni) |
| SQLite `OperationalError` | loguru ERROR + skip (mevcut) |

---

## 10. Test Stratejisi

Faz 4 deseni:
- **Birim (saf):** `statistical/base.py` helper'ları (split_recent sınırları, state-partition, robust stats, σ/IQR=0 koruması) — sentetik pencereler. Her dedektör `detect`: sentetik uzun pencere (bilinen baseline + sapan/sapmayan güncel tail), beklenen Anomaly.
- **İmza (scenarios):** A/B/C senaryosu engine harness ile → uzun pencere kur (clean baseline tarihçesi + arıza tail) → statistical dedektör tetiklenir; clean tail → tetiklenmez (FP). Faz 4 `build_detector_window` harness'ı genişletilir (çok-segmentli `build_statistical_window`: clean baseline segment + arıza tail segmenti). **Iter 5.2 uygulama gerçeği (ölçümle doğrulandı, 2026-05-31):**
  - **A (MechanicalWear):** motor_current (z≈19) + vibration (z≈15) → 3σ + IQR POZİTİF.
  - **B (HydraulicLeak):** mevcut 2-dk hold fixture istatistiksel olarak yetersiz (~2.5σ < fence). **Gelişmiş kaçak** (uzun-hold fixture `devices_with_hydraulic_leak_developed.yaml`, ~600s) hydraulic_pressure'ı z≈12'ye düşürür → 3σ + IQR POZİTİF (kabul kriteri 1 "N saat sonra" gelişmiş arıza durumunu temsil eder).
  - **C (ElectricalFault):** **varyans/saçılım arızasıdır** (mean/median sabit, ölçülen z<1.4) → merkezi-eğilim dedektörleri (3σ/IQR) tasarımı gereği KÖR. **Tamamlayıcı katman** olarak ele alınır: statistical SESSİZ (negatif imza testi) + kural katmanı `motor_voltage_erratic` (std/varyans) yakalar. § 9 C ile tutarlı.
  - **Harness artefaktı:** iki-segment stitch farklı fixture state_duration'ları kullanır → durağan-değil `mast_position`/`motor_temperature` segmentler arası kayar (arızadan değil, zamanlamadan). İmza/overlap testleri dedektörü ilgili durağan sensöre `sensors=[...]` ile daraltır (§ 5 filtresi). Üretimde baseline sürekli olduğundan bu artefakt yoktur.
- **Overlap analizi:** aynı arıza penceresinde kural ve istatistik dedektörlerin AYNI arızayı işaretlediğini doğrula (kabul kriteri — tutarlılık). En az bir senaryoda örtüşme gösterilir → **A (MechanicalWear): `motor_current_high` (kural, kısa pencere) + `three_sigma:motor_current` (istatistik, uzun pencere) → `fuse_anomalies` ile tek `fused(N)` (§ 8 iki-pencere mimarisi).**
- **Coverage:** `statistical` paketi ≥%85 (servis `run()` loop hariç, Faz 4 deseni). Her task sonunda tam suite + mypy + ruff (src/detectors/statistical dahil).

---

## 11. Kabul Kriterleri (ROADMAP § Faz 5)

1. Sistem ~N saat (≈`baseline_window_s`) normal veri gördükten sonra baseline'ı öğreniyor (on-the-fly rolling; yeterli geçmiş yoksa abstain → yeterli olunca tetiklemeye başlar). ✅ (5.1 + 5.2)
2. Sentetik arızalar istatistiksel dedektörle yakalanabiliyor: **A/B doğrudan (mean/median kayması) — imza testleri + canlı smoke** (IQR canlı `fused(2)` doğrulandı). **C bir varyans arızasıdır → merkezi-eğilim dedektörlerine tamamlayıcıdır: statistical sessiz (tasarım), kural katmanı (`motor_voltage_erratic`) yakalar** (§ 10). ✅
3. Kural tabanlı dedektörle tutarlı sonuçlar (overlap analizi: A'da `motor_current_high` + `three_sigma:motor_current` aynı arızayı işaretler → `fused(N)`). ✅
4. Yanlış pozitif oranı kabul edilebilir (clean veride istatistik dedektörler tetiklenmez — imza clean tail + canlı smoke device_clean 0 anomali; agregat + recent-dışlama + robust stat FP'yi düşük tutar). ✅
5. ≥2 istatistiksel dedektör (3-sigma + IQR). Tüm testler yeşil (293 passed) + mypy + ruff temiz. ✅

> **Skor normalizasyonu notu (Iter 5.2):** ThreeSigma skoru fence'e (`(deviation−fence)/fence`), IQR skoru IQR'a (`distance/IQR`) normalize edilir (§ 6, bağımsız tanımlı). Fusion `max(score)` aldığından iki katman skorları doğrudan karşılaştırılabilir DEĞİLDİR — gelecekte çok-katman güven-bazlı fusion (Faz 6/7) bunu standardize etmeli.

---

## 12. Bilinen Sınırlar (dokümante)

- **Yavaş arıza drift'i:** saatlerce gelişen arıza eninde sonunda baseline'ı "yeni normal" yapar (her rolling baseline'ın doğası). Robust stat (IQR/median) + güncel-dışlama bunu hafifletir; tam çözüm (eğitilmiş temiz baseline) Faz 6+'a ertelenir.
- **Rampalı sensörler (mast_position):** durağan değil → düşük duyarlılık (FP yok). § 5.
- **Performans:** poll başına 1h yeniden sorgu — prototip ölçeğinde kabul. § 8.

---

## 13. İlerleyen Fazlara Ertelenenler

| Konu | Faz |
|---|---|
| ML dedektörler (Isolation Forest, One-Class SVM, LSTM) | Faz 6 |
| Gelişmiş füzyon (ağırlıklı/güven-bazlı, çok-katman) | Faz 6/7 |
| Alerts servisi (önceliklendirme, ack/resolve, bildirim) | Faz 7 |
| Eğitilmiş + kalıcı baseline (`baselines` tablosu, eğitim modu) | Belirsiz (gerekirse) |
| Çevresel bağlam (sıcaklık/nem korelasyonu) | Belirsiz |
| Baseline cache / downsample (performans) | Gerekirse |

---

## 14. Spec'e Karşı Disiplin

- Bu spec Faz 5 boyunca tek hakemdir.
- Faz 4 (kural dedektörü, Detector ABC, fusion, anomalies tablosu, poll servisi, dashboard) bu fazın **girdi kontratıdır**; Faz 5 bunları okur + genişletir (statistical paket, iki pencere, statistical config bloğu), bozmaz. `Detector` ABC ve `fuse_anomalies` DEĞİŞMEZ.
- Statistical dedektörler gözlem modu: yalnız `telemetry` okur, yalnız `anomalies` yazar.
- Baseline veriden öğrenilir (on-the-fly rolling); hand-picked sabit eşik yok ([[feedback_domain_md_truth_source]] — istatistiksel kriter tercih edilir).

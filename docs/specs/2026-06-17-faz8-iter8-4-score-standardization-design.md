# Faz 8 Iter 8.4 — Skor Standardizasyonu (Band-Pozisyon) Tasarım Dokümanı

> **Tek hakem:** Bu doküman Iter 8.4'ün tasarım kararlarını bağlar. Brainstorming 2026-06-17.
> **Bağlam:** POC sağlamlaştırma çalışmasının 2. iterasyonu (1. = Iter 8.3 arıza kapsamı; sıradaki
> 8.5 yaşam döngüsü kenar durumları). Amaç teknik dürüstlük, GÖRSEL değil.
> **Domain temeli:** Karar, iki bağımsız web-araştırmasının (Claude Code + harici AI brief
> `anomaly-scoring-severity-research.md`) örtüştüğü "yüksek güven" zeminine dayanır — uydurma
> değil, ISO/endüstri pratiği. Kaynaklar § 11.

## 1. Amaç ve Kapsam

Her dedektör `[0, 1]` aralığında bir `score` üretiyor ama **her biri farklı, keyfi bir payda**
kullanıyor (eşik kuralları `2×`, hidrolik `4×`, voltaj `5×`, `sensor_out_of_range` ham `margin`,
3σ `fence`, IQR `IQR`). Sonuç: `score = 0.8` her dedektörde **başka bir şiddet** ifade ediyor →
karşılaştırılamaz, dürüst değil. İki somut belirti:

1. **Karşılaştırılamazlık:** `sensor_out_of_range` ciddi bir veri-bütünlüğü arızası (severity high)
   ama skoru `−500 / [−50, 12000]` marjıyla **≈0.04** çıkıyor; marjinal bir `three_sigma` 0.6
   gösterebiliyor. Dashboard'da yan yana yanıltıcı.
2. **Füzyon tutarsızlığı:** `fuse_anomalies` temsilciyi `(severity, score)` ile seçiyor ama
   gösterilen `score = max(a.score)` **başka bir anomaliden** gelebiliyor → gösterilen sayı,
   gösterilen anomaliye (sensör/değer/severity) ait olmayabiliyor.

Bu iterasyon **çekirdek** üç düzeltmeyi yapar (A + B + C). Genişletmeler (D severity-bant türetme,
E veri-kalitesi ekseni) **bilinçli olarak ertelenir** (§ 9 / Iter 8.6).

**Çerçeve:** Araştırma "altta sürekli büyüklük, üstte kategorik band" + "füzyon = max/öncelik,
asla ortalama" + "sensör-sağlığı = ayrı ikili validity" konvansiyonunu net ortaya koydu
(ISO 13374 katmanlı mimari + ISO 20816 A/B/C/D bölge + ISA-18.2 alarm yönetimi). Çekirdek bu
zemine oturur; tam olasılık-kalibrasyonu (percentile/p-value, Convention 2) ve sağlık-indeksi
ertelenir (POC için band-pozisyon = teknisyen-okunur ve yeterli).

## 2. Temel Kararlar (brainstorming çıktısı, 2026-06-17)

| Karar | Seçim | Gerekçe / reddedilen |
|---|---|---|
| Skor semantiği | **Band-pozisyon** `clamp01((q−warn)/(trip−warn))` | İki kaynak bağımsızca aynı formülde buluştu (ISO 20816 zone mantığı). "0 = alarmı yeni geçti, 1 = kritik". Reddedilen: olasılık/percentile kalibrasyonu (Convention 2 — daha güçlü ama ML-vari, Iter 8.6+ ideali) |
| Skor ölçeği | **`[0, 1]` korunur** | Şema/migration değişmez; 0-100'e geçmek kozmetik, YAGNI |
| Füzyon gösterilen skor | **Temsilcinin kendi skoru** (`top.score`) | Gösterilen tüm alanlar tek anomaliye ait → tutarlı. "En-kötü-kazanır, asla ortalama" (araştırma net). Reddedilen: `max(a.score)` (ödünç skor → tutarsız) |
| Sensör-sağlığı skoru | **Sabit `1.0`** (ikili validity) | "Veri geçersiz" ikili bir durum; ölçeklenmez (araştırma B.5). margin'li 0.04 hatalı |
| Sensör-sağlığı ekseni | **Severity'de kalır** (E ertelendi) | Ayrı veri-kalitesi ekseni + gating + UI = büyük; izole `mast_position`'da pratik kazanç sınırlı → Iter 8.6 |
| İstatistik kritik çapası | **3σ → K=6 (6-sigma), IQR → Tukey 3·IQR** | Standart istatistik sabitleri; sim kalibrasyonu GEREKTİRMEZ (eşik kurallarının trip'lerinden farklı) |
| Eşik kuralı trip'leri | **Gerçek sim çıktısıyla ölçülür** (plan) | Kalıcı kalibrasyon disiplini; hard-coded yok, config-driven |
| Severity bant-türetme (D) | **Ertelendi** (Iter 8.6) | Sabit per-kural severity yerine değerden türetme; severity-first füzyon sıralamasını etkiler → ayrı iş |

## 3. A — Birleşik Band-Pozisyon Skoru

**Yeni saf modül `src/detectors/scoring.py`** (stdlib-only, dedektör/storage import etmez; DRY +
birim-testli leaf):

```python
def band_position_score(q: float, warn: float, trip: float) -> float:
    """q'nun warn→trip bandındaki konumu, [0,1] (warn'da 0, trip'te 1). trip>warn varsayar."""
```

Sözleşme: `trip > warn` (çağıran/config doğrular; `trip <= warn` → ValueError veya boot-guard).
`q < warn` → 0 (kural zaten warn altında tetiklenmez; clamp savunma). `q >= trip` → 1.

**Anlam her dedektörde aynı:** `0` = tetik (alarm) sınırını yeni geçti, `1` = kritik (trip) seviyesi.

| Dedektör | ölçülen `q` | `warn` | `trip` | Kaynak |
|---|---|---|---|---|
| `motor_temperature_high` | tepe °C | mevcut `critical_threshold_c` (95) | `critical_ref_c` (ölçülecek, ~130) | sim (F ~123°C) |
| `motor_current_high` | RAISING ort. A | `threshold_a` (9.0) | `critical_a` (ölçülecek) | sim (A ~10A) |
| `vibration_elevated` | RAISING ort. g | `threshold_g` (0.37) | `critical_g` (ölçülecek) | sim (A ~0.45g) |
| `hydraulic_pressure_decline` | −slope bar/dk | `slope_threshold_bar_per_min` (3.0) | `critical_slope_bar_per_min` (ölçülecek) | sim (B ~5; eski örtük 12) |
| `motor_voltage_erratic` | std V | `std_threshold_v` (1.0) | `critical_std_v` (ölçülecek) | sim (C ~4V; eski örtük 6) |
| `three_sigma` | sapma (σ birimi) | `μ + 3σ` | `μ + Kσ`, K=`sigma_k_critical` (vars. 6.0) | istatistik standardı |
| `iqr` | iç-fence dışı mesafe | `Q3 + 1.5·IQR` | `Q3 + far·IQR`, far=`iqr_multiplier_critical` (vars. 3.0) | Tukey "far-out" fence |

- İstatistik dedektörlerinde band-pozisyon doğal kapanır: 3σ → `(z−3)/(K−3)`; IQR → `mesafe/((far−1.5)·IQR)`
  = far=3.0 için `mesafe/(1.5·IQR)`.
- **Keyfi paydalar (`2×`/`4×`/`5×`/`margin`/`fence`/`IQR`) tümüyle kalkar.** Yerine ya ölçülen kritik
  referans (eşik kuralları) ya da standart istatistik çapa (6σ, Tukey 3·IQR).
- **trip seçimi tetiklemeyi DEĞİŞTİRMEZ** (kural yine `warn`'da tetikler) → FP/TP regresyon riski yok;
  yalnız skorun *büyüklüğü* anlamlanır.

## 4. B — Füzyon Dürüstlüğü

`src/detectors/fusion.py` `fuse_anomalies`:
- Temsilci seçimi DEĞİŞMEZ: `top = max(anomalies, key=_rank)`, `_rank = (severity_rank, score)`
  (en-kötü-kazanır; araştırma "max/öncelik" doğruladı). Band-pozisyon skoru `score` tie-break'i artık
  *anlamlı* (aynı-severity'de yüksek band = daha kötü).
- **TEK DEĞİŞİKLİK:** `score = max(a.score for a in anomalies)` → `score = top.score`. Böylece gösterilen
  tüm alanlar (`device_id`, `sensor`, `value`, `severity`, `score`) **tek bir anomaliye** ait, tutarlı.
- `rule_name=f"fused(N)"`, `window_start=min`, `window_end=max`, description tüm katkılar — DEĞİŞMEZ.

## 5. C — Sensör-Sağlığı Skoru

`sensor_out_of_range` ve `sensor_frozen` = **veri-bütünlüğü / ikili validity** kuralları.
- `sensor_out_of_range`: `score = min(1, excess/margin)` → **`score = 1.0`** (sabit). `excess`/`margin`
  hesabı kalkar (sınır-içi/dışı kararı için karşılaştırma kalır; yalnız skor sabitlenir).
- `sensor_frozen`: zaten `1.0` — DEĞİŞMEZ (tutarlılık için belgelenir).
- **Severity DEĞİŞMEZ** (config'teki high/warning). Ayrı veri-kalitesi eksenine taşıma (E) bu
  iterasyonda YOK → Iter 8.6. Yalnız skor dürüstleşir.
- Bu iki kuralın band-pozisyon DEĞİL **ikili-validity** olduğu kod yorumunda + DEMO/dokümanda belirtilir.

## 6. Mevcut Davranışla Uyum (Regresyon Kapsamı)

- **Tetikleme değişmez** → A/B/C/F/E imza testleri (`tests/scenarios/`) yeşil kalır (skor değil,
  tetiklenme assert ederler; skor assert eden satırlar varsa güncellenir).
- **Skor değeri assert eden birim testler GÜNCELLENİR** (her kural + 3σ + IQR + fusion). Bu beklenen
  ve istenen değişim (eski keyfi skorlar → band-pozisyon).
- **Füzyon temsilci tie-break flip riski:** band-pozisyon skoru same-severity tie-break'i değiştirebilir
  → temsilci aynı-severity başka anomaliye kayabilir (hâlâ dürüst). Canlı demo smoke doğrular.
- **Şema/migration YOK** (`score` zaten float). **Dashboard yapısal değişmez** (skor zaten gösteriliyor;
  artık anlamlı). **Gözlem modu korunur.**
- **Uyarı yaşam döngüsü + debounce DEĞİŞMEZ** (Iter 8.5 ayrı).

## 7. Config

Tüm trip/çapa değerleri **config-driven** (CLAUDE.md: hard-coded yok). `config/detectors.yaml.example`
+ `config/detectors.demo.yaml` paralel güncellenir:
- Eşik kurallarına `critical_*` paramı eklenir (zorunlu; eksikse boot'ta fail-fast — sessiz default yok).
- 3σ'ya `sigma_k_critical` (vars. 6.0), IQR'a `iqr_multiplier_critical` (vars. 3.0) — standart sabitler,
  dokümante varsayılanlı (eksikse standart değer; istatistik çapası "domain magic" değil).
- Builder (`build_detectors` / `build_statistical_detectors`) generic `**params` ile zaten geçirir;
  kural/dedektör `__init__`'leri yeni paramı kabul + `trip > warn` doğrular.

## 8. Dosya Düzeni

| Dosya | Durum | Sorumluluk |
|---|---|---|
| `src/detectors/scoring.py` | YENİ | `band_position_score` saf yardımcı |
| `src/detectors/rules/motor_temperature_high.py` | rework | band-pozisyon + `critical_ref_c` |
| `src/detectors/rules/motor_current_high.py` | rework | band-pozisyon + `critical_a` |
| `src/detectors/rules/vibration_elevated.py` | rework | band-pozisyon + `critical_g` |
| `src/detectors/rules/hydraulic_pressure_decline.py` | rework | band-pozisyon + `critical_slope_bar_per_min` |
| `src/detectors/rules/motor_voltage_erratic.py` | rework | band-pozisyon + `critical_std_v` |
| `src/detectors/rules/sensor_out_of_range.py` | rework | `score = 1.0` |
| `src/detectors/rules/sensor_frozen.py` | yorum | ikili-validity belgelenir (kod değişmez) |
| `src/detectors/statistical/three_sigma.py` | rework | band-pozisyon + `sigma_k_critical` |
| `src/detectors/statistical/iqr.py` | rework | Tukey far-out fence + `iqr_multiplier_critical` |
| `src/detectors/fusion.py` | 1 satır | `score = top.score` |
| `config/detectors.yaml.example` | +param | `critical_*` + istatistik çapaları |
| `config/detectors.demo.yaml` | +param | aynı |
| `tests/unit/...` | güncelle/ekle | scoring birim + kural skor değerleri + fusion top.score + out_of_range=1.0 |
| `docs/DEMO.md` | güncelle | skor anlamı (band-pozisyon) notu |

## 9. Kapsam Dışı / Ertelenen

- **D — Severity'yi banttan türetme** (ISO zone mantığı; sabit per-kural severity yerine değerden):
  Iter 8.6. Severity-first füzyon sıralamasını + config'leri etkiler.
- **E — Sensör-sağlığı = ayrı veri-kalitesi ekseni** (gating + dashboard ayrı gösterim): Iter 8.6.
- **Olasılık/percentile kalibrasyonu** (Convention 2: z→CDF, percentile-rank, "bits of rarity"):
  POC için band-pozisyon yeterli; gerçek-veri/ML fazı.
- **Ağırlıklı sağlık-indeksi / Dempster-Shafer füzyon:** ML/optimizasyon → North Star + "ML yok".
- **0-100 ölçeği, dashboard band-rozeti:** kozmetik; gerekirse 8.6+.

## 10. Kalibrasyon Disiplini (projenin kalıcı dersi)

Eşik kurallarının `trip` değerleri **GERÇEK simülatör çıktısı ölçülerek** belirlenir (throwaway ölçüm
scripti, plan yazımında — Faz 4.2/5.2/8.1/8.3 dersi). İlke: `warn < arıza-tipik-q ≲ trip` olacak şekilde
trip seçilir — skor ne hep ~0 (trip absürt yüksek) ne hep 1 (trip arızanın altında) olsun; arızanın
tipik şiddetinde anlamlı bir orta-bant değer üretsin. İstatistik çapaları (K=6, far=3.0) ölçüm
gerektirmez (standart). **Canlı demo smoke** skorların makullüğünü + 0 FP'yi doğrular.

## 11. Test Stratejisi

| Katman | Test |
|---|---|
| `scoring` birim | `band_position_score`: warn→0, trip→1, orta→0.5, clamp (q<warn→0, q>trip→1), `trip<=warn`→hata |
| Kural birim | Her eşik kuralı: tetikleme eşiğinde skor≈0, kritikte≈1, ara-değerde band-pozisyon; `sensor_out_of_range`→1.0 |
| İstatistik birim | 3σ: z=3→0, z=6→1, z=4.5→0.5; IQR: fence→0, far-fence→1 |
| Füzyon birim | `fused(N)` skoru = temsilcinin (top) skoru; ödünç max YOK |
| İmza/regresyon | A/B/C/F/E tetiklemeleri korunur (skor değil tetik); skor assert eden testler güncellenir |
| Kapanış | **tam suite + mypy strict + ruff + canlı demo smoke (6 cihaz)** |

**Canlı demo smoke kabul:** 001 temiz 0 FP; her arıza doğru uyarı + **makul band-pozisyon skoru**
(örn. F sıcaklık ~0.7-0.9, sensör arızası 1.0); füzyonda gösterilen skor temsilciye ait; temiz teardown.

## 12. Kabul Kriterleri

1. Tüm dedektörler band-pozisyon skoru üretir (`scoring.band_position_score`); keyfi paydalar kalkar.
2. `score = 0.8` her dedektörde "alarm→kritik yolunun %80'i" anlamına gelir (karşılaştırılabilir).
3. Füzyonda gösterilen skor temsilcinin kendi skorudur (ödünç `max()` yok); en-kötü-kazanır korunur.
4. `sensor_out_of_range` skoru 1.0 (ikili validity); `sensor_frozen` 1.0 belgeli.
5. Tüm testler yeşil + mypy strict + ruff temiz + canlı demo smoke (§ 11) geçer; A/B/C/F/E imzaları korunur.
6. trip değerleri config-driven + gerçek sim çıktısıyla kalibre (§ 10); hard-coded yok.

## 13. Spec'e Karşı Disiplin

Uygulama bu spec'ten saparsa önce spec güncellenir. Sayısal trip değerleri **ölçülerek** belirlenir
(§ 10) — spec ilkeyi (band-pozisyon + warn<tipik≲trip) bağlar, plan/uygulama sayıyı kalibre eder.
Mimari kararlar (§ 2) kullanıcı onayı olmadan değişmez.

## 14. Kaynaklar (domain temeli)

İki bağımsız araştırmanın örtüştüğü "yüksek güven" maddeleri:
- **ISO 13374** — durum-izleme katmanlı mimari (State Detection → Health Assessment); "veri kalitesi =
  good/bad/undetermined" etiketi.
- **ISO 20816 / 10816** — titreşim şiddet bölgeleri A/B/C/D; alarm = B/C, trip = C/D; relatif kriter
  baseline × 2.0-2.5; band-pozisyon mantığının kaynağı.
- **ISA-18.2 / IEC 62682** — alarm yönetimi (3-4 öncelik, ≤%5 yüksek, max/öncelik füzyon, deadband).
- **Kriegel/Zimek (SDM 2011), "Interpreting and Unifying Outlier Scores"** — heterojen skorları
  karşılaştırılabilir kılma (Convention 2, ertelenen ideal).
- **Teleskopik mast'a özgü skorlama standardı YOK** (mast = hidrolik aktüatör + motor + yapı →
  bileşen-seviyesi CM ödünç alınır). İki kaynak da doğruladı.
- Harici brief: `~/Downloads/anomaly-scoring-severity-research.md` (35 kaynaklı, çapraz-doğrulandı).

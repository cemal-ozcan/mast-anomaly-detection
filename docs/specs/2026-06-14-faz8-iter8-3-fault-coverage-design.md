# Faz 8 Iter 8.3 — Arıza Kapsamı Tamamlama (F + E) Tasarım Dokümanı

> **Tek hakem:** Bu doküman Iter 8.3'ün tasarım kararlarını bağlar. Brainstorming 2026-06-14.
> **Bağlam:** POC sağlamlaştırma çalışmasının 1. iterasyonu (sıradakiler: 8.4 skor standardizasyonu,
> 8.5 yaşam döngüsü sağlamlaştırma). Amaç teknik, GÖRSEL değil.

## 1. Amaç ve Kapsam

POC'in (mast firmasını gerçek cihaz tahsisine ikna edecek demo) **teknik inandırıcılığını** artırmak.
Mevcut durum: simülatör yalnız 3 arıza üretiyor (A=mekanik aşınma, B=hidrolik kaçak, C=elektrik), ve
2 kural (`motor_temperature_high`, `sensor_frozen`) gerçekçi bir arızayla **hiç tetiklenmiyor** (yalnız
birim-testte yaşıyorlar). Bu iterasyon **2 yeni arıza** ekler ve **uyuyan bir kuralı canlandırır**:

- **F — Sıcaklık Aşımı** (kestirimci arıza): gerçekçi termal model + `motor_temperature_high`'ı canlandırma.
- **E — Sensör Arızası** (sağlamlık özelliği): yeni `sensor_out_of_range` kuralı + imkânsız-değer senaryosu.

**D (aşırı yük) BİLİNÇLİ OLARAK KAPSAM DIŞI** (§ 12): gerçek bir durum ama tespiti A ile birebir örtüşür
(ikisi de `motor_current_high`) → "şişirilmiş arıza sayısı" yerine "net, ayırt edici tespit" tercih edildi.

**Çerçeve (dürüstlük):** A/B/C/F = 4 **kestirimci** arıza (erken teşhis = ticari değer). E = **sağlamlık**
özelliği ("bozuk sensöre dayanıklıyız" savunma kozu), kestirimci bakım değil veri-bütünlüğü. Tüm imzalar —
A/B/C dahil — DOMAIN.md'den türetilmiş kurgu (gerçek mast verisi yok); bu POC fazında kabul, gerçek-veri
fazında kalibre edilecek. Parametre seçimimiz (6 sensör) gerçek teleskopik mast/bom durum-izleme
sistemleriyle örtüşüyor (web araştırması doğruladı: hidrolik basınç, motor akım/voltaj, sıcaklık, titreşim,
pozisyon — sektör standardı).

## 2. Temel Kararlar (brainstorming çıktısı, 2026-06-14)

| Karar | Seçim | Gerekçe / reddedilen |
|---|---|---|
| Tespit iddia seviyesi | **Dengeli** | Senaryolar mevcut kuralları tetikler + yalnız gerçek boşluğa (E) 1 yeni kural. Reddedilen: Minimal (boşluk açık kalır), Tam (yeni kurallar + sentetik-veriye-uydurma riski) |
| D (aşırı yük) | **Atıldı** | Tespiti A ile örtüşür; netlik > sayı |
| E manifestasyonu | **İmkânsız değer** (donma değil) | Canlı demoda çarpıcı; donma ekranda "sakin sensör" gibi görünür. `sensor_frozen` kuralı kodda kalır (birim-testli, belgelenir) |
| E hedef sensörü | **`mast_position`** (self-review) | Hiçbir kural/istatistik dokunmuyor → imkânsız değer YALNIZ `sensor_out_of_range`'i tetikler, tertemiz tek uyarı. (hidrolik basınç olsaydı istatistiği kirletir, uyarı bulanırdı) |
| F çerçevesi | **Kestirimci arıza** | Termal aşırı ısınma gerçek + araştırma destekli; uyuyan kuralı canlandırır |
| E çerçevesi | **Sağlamlık özelliği** | Veri-bütünlüğü; "6. arıza" diye abartılmaz |
| Demo showcase | **6 cihaz canlı** | Dashboard kartları N cihaza ölçekleniyor (Iter 8.2) |
| Termal model | **Gerçekçi yapılır** | Mevcut "normal 35°C" gerçekçi değil (motorlar 60-90°C çalışır); F'e dokunurken taban da düzeltilir |

## 3. Yeni Arıza Senaryoları

Mevcut desen: her arıza `src/simulator/scenarios/` altında `FaultScenario` sınıfı, `SCENARIO_REGISTRY`
kaydı, ilgili state'lerde sensör değerlerini bozar (A/B/C bu deseni izliyor).

### 3a. F — Sıcaklık Aşımı (`temperature_overshoot`) — RAISING + HOLDING
Motor sıcaklığı normal çalışma tavanını aşıp senaryo boyunca kritik eşiğin üstüne **tırmanır** (sürekli
yük / yetersiz soğutma modeli). Tespit: `motor_temperature_high`. DOMAIN.md § F'e dayalı.

### 3b. E — Sensör Arızası (`sensor_fault`) — tüm state'ler
`mast_position` sensörü aralıklı olarak **fiziksel olarak imkânsız** bir değer üretir (örn. negatif yükseklik
−500mm), diğer sensörler normal kalır. Tespit: yeni `sensor_out_of_range` (§ 6a). DOMAIN.md § E (imkânsız
değer varyantı).

## 4. Gerçekçi Termal Model (F'in ön koşulu)

`src/simulator/sensors/motor_temperature.py` şu an taban sıcaklığı ~25-35°C'de tutuyor — gerçekçi değil
(çalışan motorlar 60-90°C). Düzeltme:
- **Normal çalışma sıcaklığı gerçekçi aralığa** taşınır (ısınma RAISING'de, soğuma diğer state'lerde;
  taban kalibrasyonla belirlenir — § 9).
- **F aşımı senaryonun TOPLAMSAL `modify`'ıyla yapılır** (A'nın `clean_value + factor*8.0` deseniyle aynı):
  senaryo, sensörün (tavanlı) temiz değerinin ÜSTÜNE bir aşım deltası ekler (`clean_value + overshoot(elapsed)`)
  → sıcaklık kritik eşiği doğal olarak geçer. **Sensörün tavanı KALDIRILMAZ** (normal-çalışma sınırı olarak
  kalır); yalnız § 4'teki taban sabitleri (ambient/max/rates) gerçekçilik için değişir. Bu sayede sensör saf
  kalır, senaryodan habersizdir (mimari uyum).
- `motor_temperature` istatistiksel dedektör kapsamı DIŞINDA kalır (mevcut FP koruması korunur) → gerçekçi
  taban yeni istatistik FP getirmez; F yalnız kuralla yakalanır (C gibi).

## 5. Mevcut Davranışla Uyum (Regresyon Kapsamı)

Bu iterasyon mevcut çalışan davranışı BOZMAMALI:
- **A/B/C imzaları korunur** (`tests/scenarios/` mevcut imza testleri yeşil kalır) — özellikle gerçekçi
  termal taban, A'nın sıcaklık katkısını yeni eşiğin altında bırakmalı (yanlış `motor_temperature_high` yok).
- **İstatistiksel dedektör kapsamı değişmez** (`[motor_current, vibration, hydraulic_pressure]`) —
  `motor_temperature` ve `mast_position` scope dışı kalır (FP koruması); F kural-only, E izole sensör.
- **Uyarı yaşam döngüsü + fusion/debounce değişmez** (İter 8.5 ayrı ele alır).
- **Gözlem modu korunur:** simülatör/dedektör yalnız üretir/okur; yeni yazma yolu yok.

## 6. Tespit Katmanı

### 6a. Yeni kural: `sensor_out_of_range` (E için)
`sensor_frozen`'ın kardeşi, sensör-sağlığı kuralı. Config-driven, tüm state'lerde çalışır.
- **Mantık:** bir okuma, o sensör için tanımlı `[min, max]` **fiziksel imkânsızlık** sınırlarının dışındaysa
  tetiklenir.
- **KRİTİK: sınırlar "imkânsızlık" sınırıdır, "normal" sınırı DEĞİL.** F'in yüksek sıcaklığı, A/D'nin yüksek
  akımı vb. bu kuralı tetiklemez (anormal ama mümkün → eşik kuralları yakalar). Yalnız fiziksel saçmalık
  (negatif basınç/pozisyon, vb.) tetikler. Sınırlar DOMAIN.md fiziksel aralıklarına geniş marjla dayanır;
  meşru arızaların (özellikle F'in yüksek sıcaklığı) sınır içinde kaldığı kalibrasyonla doğrulanır (§ 9).
- **Severity:** `high` (sensör arızası = güvenilmez veri, ciddi).
- **Skor:** sınır ihlali büyüklüğüne göre `min(1, aşım/marj)` (İter 8.4 skor standardizasyonuyla uyumlu).
- **Config (örnek, kalibre edilecek):**
  ```yaml
  sensor_out_of_range:
    severity: high
    bounds:
      motor_current:       [0, 20]
      motor_voltage:       [0, 40]
      hydraulic_pressure:  [-5, 300]
      motor_temperature:   [-20, 150]   # F'in yüksek sıcaklığı bunu tetiklemez
      mast_position:       [0, 10000]   # negatif/aşırı imkânsız
      vibration:           [0, 5]
  ```

### 6b. Mevcut kuralların durumu
| Arıza | Tespit | Not |
|---|---|---|
| F | `motor_temperature_high` (mevcut, **uyuyordu** → canlanır; eşik gerçekçi-tabana göre yeniden, § 9) | İstatistik göremez (scope dışı) → kural-only |
| E | `sensor_out_of_range` (**yeni**) | `mast_position` izole → yalnız bu kural tetiklenir, tertemiz |
| (donma) | `sensor_frozen` (mevcut) | Canlı demoda yok; birim-testli; "donmuş sensörü de tespit ediyoruz" diye belgelenir |

## 7. Demo Düzeni

`config/devices.demo.yaml` 6 cihaza genişler (kartlar Iter 8.2'den N cihaza ölçekli):

| Cihaz | Senaryo | Demoda |
|---|---|---|
| 001 | temiz | 🟢 0 FP referansı |
| 002 | mechanical_wear (A) | akım + titreşim → `fused` |
| 003 | hydraulic_leak (B) | basınç düşüş trendi |
| 004 | electrical_fault (C) | voltaj düzensizliği |
| 005 | temperature_overshoot (F, **yeni**) | sıcaklık kritik eşiğe tırmanış (en dramatik görsel) |
| 006 | sensor_fault (E, **yeni**) | imkânsız `mast_position` → `sensor_out_of_range` (sağlamlık kozu) |

Onset zamanlamaları mevcut desen gibi koreograflanır (onset 60s, çeşitli süreler — auto-resolve/overlap
gösterimi için). `docs/DEMO.md` beat-script güncellenir: anlatı = **4 kestirimci arıza (A/B/C/F) + 1
sağlamlık (E)** + temiz referans.

## 8. Dosya Düzeni

| Dosya | Durum | Sorumluluk |
|---|---|---|
| `src/simulator/scenarios/temperature_overshoot.py` | YENİ | F senaryosu (FaultScenario) |
| `src/simulator/scenarios/sensor_fault.py` | YENİ | E senaryosu (imkânsız mast_position) |
| `src/simulator/scenarios/__init__.py` | +2 kayıt | `SCENARIO_REGISTRY` |
| `src/simulator/sensors/motor_temperature.py` | rework | Gerçekçi taban + F aşımı |
| `src/detectors/rules/sensor_out_of_range.py` | YENİ | Fiziksel-aralık-dışı kuralı |
| `src/detectors/rules/__init__.py` (veya registry) | +1 kayıt | `RULE_REGISTRY` |
| `config/detectors.yaml.example` | +kural, eşik | `sensor_out_of_range` bounds + `motor_temperature_high` yeni eşik |
| `config/detectors.demo.yaml` | +kural, eşik | aynı |
| `config/devices.demo.yaml` | +2 cihaz | 005 F + 006 E |
| `scripts/seed_demo_baseline.py` | uyarla | Temiz sıcaklık baseline'ı gerçekçi tabana göre |
| `docs/DEMO.md` | güncelle | 6-cihaz beat |
| `tests/scenarios/` | +imza testleri | F + E |
| `tests/unit/` | +birim testler | `sensor_out_of_range` |

## 9. Kalibrasyon Disiplini (projenin kalıcı dersi)

Eşikler **GERÇEK simülatör çıktısı ölçülerek** belirlenir (throwaway ölçüm scripti, plan yazımında),
istatistiksel kriterle: temiz dağılım ile arıza dağılımı net ayrılmalı. **Canlı demo smoke FP'yi yakalar**
(controlled test kaçırabilir — Faz 4.2/5.2/8.1 dersi). Spesifik kalibrasyon noktaları:
- Gerçekçi normal sıcaklık tabanı + `motor_temperature_high` eşiği: **normal < eşik, NET marjla** (eşik,
  max-normal + diğer arızaların sıcaklık katkısının (örn. A'nın +ısısı) üstünde olmalı; F bunu güvenle aşmalı).
- `sensor_out_of_range` bounds: meşru hiçbir değer (özellikle F'in yüksek sıcaklığı, B'nin düşük basıncı)
  sınır dışına çıkmamalı; yalnız senaryo-enjekte imkânsız değer tetiklemeli.
- F senaryosu, demo penceresinde (onset sonrası ~dakikalar) eşiği güvenle aşacak ısınma hızında olmalı.

## 10. Test Stratejisi

| Katman | Test |
|---|---|
| Simülatör senaryoları | F: sıcaklık eşiği aşıyor; E: `mast_position` imkânsız değer üretiyor (mevcut scenario test deseni) |
| İmza testleri (`tests/scenarios/`) | F → `motor_temperature_high` tetiklenir; E → `sensor_out_of_range` tetiklenir + temiz cihaz/diğer arızalar bu kuralları YANLIŞ tetiklemez |
| Yeni kural birim testi | `sensor_out_of_range`: sınır-içi tetiklemez, sınır-dışı tetikler (her sensör), severity, skor |
| Termal regresyon | Gerçekçi taban mevcut motor_temperature testlerini + diğer testleri kırmıyor (güncelle/doğrula) |
| Kapanış | **tam suite + mypy + ruff + canlı demo smoke** |

**Canlı demo smoke kabul (6 cihaz):** 001 temiz **0 FP**; 002/003/004 mevcut imzalar (regresyon); 005 →
`motor_temperature_high`; 006 → `sensor_out_of_range` (yalnız o, tertemiz); temiz teardown.

## 11. Kabul Kriterleri

1. Simülatör 5 arıza üretebiliyor (A/B/C + F + E); D bilinçli yok.
2. F sıcaklık aşımı `motor_temperature_high`'ı canlı tetikliyor (uyuyan kural canlandı); termal model gerçekçi.
3. E imkânsız değer `sensor_out_of_range`'i (yeni) tetikliyor, başka kural/istatistik kirlenmiyor.
4. Demo 6 cihazda çalışıyor; 001 temiz 0 FP; her arıza doğru uyarı.
5. Tüm testler yeşil + mypy strict + ruff temiz + canlı demo smoke (§ 10) geçer.
6. `sensor_frozen` kuralı korunur (birim-testli), DEMO.md'de belgelenir.

## 12. Kapsam Dışı / Ertelenen

- **D (aşırı yük):** atıldı (§ 1/§ 2) — gerekirse gelecekte ayırt edici sinyalle (yüksek-basınç kuralı) eklenebilir.
- **Donma varyantı canlı demo:** `sensor_frozen` kodda kalır ama demoda gösterilmez.
- **Aykırı-değer baseline temizleme:** E'nin imkânsız değeri izole sensörde (`mast_position`) olduğu için
  istatistiği kirletmiyor → baseline-temizleme gerekmiyor (YAGNI; gerçek-veri fazı).
- **Skor standardizasyonu:** İter 8.4.
- **Yaşam döngüsü kenar durumları:** İter 8.5.
- **Yük/eğim/yağ-durumu sensörleri:** gerçek sistemlerde var ama POC kapsamı dışı (gerçek-donanım fazında entegre).

## 13. Spec'e Karşı Disiplin

Uygulama bu spec'ten saparsa önce spec güncellenir. Sayısal eşikler (sıcaklık tabanı/eşiği, bounds) **ölçülerek**
belirlenir (§ 9) — spec ilkeyi bağlar, plan/uygulama sayıyı kalibre eder. Mimari kararlar (§ 2) kullanıcı onayı
olmadan değişmez.

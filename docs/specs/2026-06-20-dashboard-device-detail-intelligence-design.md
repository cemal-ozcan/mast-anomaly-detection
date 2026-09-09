# Dashboard — Cihaz Detayı "Sensör Zekâsı" Tasarım Dokümanı

> **Tek hakem:** Cihaz Detayı sayfasındaki sensör panellerini zenginleştirme. Brainstorming 2026-06-20 (görsel companion mockup onaylandı).
> **Bağlam:** Operasyon Merkezi açılışı + radar grafikler + enstrüman görünüm tamam. Kullanıcı gözlemi: "arkadaki çok-katmanlı analiz (3 katman + ISO skorlama + füzyon) arayüzde görünmüyor; her sensör tek bir çizgiye indirgenmiş." Hedef: Cihaz Detayı'ndaki her sensör panelinin **kendi zekâsını** göstermesi — kritiğe uzaklık skoru + hangi katman(lar) izliyor/yakaladı.
> **Kısıt (CLAUDE.md):** Streamlit-native. Veri/tespit/gözlem-modu DEĞİŞMEZ. Skor/eşik config+detector'dan (uydurma yok). Sektör-nötr.

## 1. Amaç ve Kapsam

**Sorun:** Cihaz Detayı'nda her sensör paneli yalnız ad + durum rozeti + değer + radar grafiği gösteriyor. Arkadaki **3 katmanlı tespit** (kural + istatistik + füzyon) ve **ISO band-pozisyon skoru** tamamen görünmez. Mühendislik değeri arayüze yansımıyor.

**Çözüm:** Her sensör paneline iki dürüst bilgi katmanı ekle (yalnız **Cihaz Detayı** sayfası — landing'deki kompakt kartlar DEĞİŞMEZ; aksi halde 6×6 ızgara olur):
1. **İzleyen / Yakalayan katmanlar** — "Kural · İstatistik" chip'leri; uyarı varsa yakalayan katman vurgulu + gerçek skor.
2. **Kritiğe uzaklık göstergesi** — seviye-eşikli sensörlerde (sıcaklık/akım/titreşim) `band_position_score` ile dolan ince gauge + yüzde; eşiğin altında "Güvenli". Slope/varyans/kuralsız sensörlerde gauge YOK (dürüstlük korunur) — yalnız katman + uyarı skoru.

**Kapsam içi:** `_render_device_detail` panel render (`app.py`), yeni saf `dashboard/detection.py` (katman türetimi), `styles.py` (chip + gauge CSS), gerekirse `overview.py`/saf builder. **Kapsam dışı:** landing kartları; tespit/füzyon/skorlama mantığı (yalnız okunur/gösterilir); yeni bağımlılık; alert drill-down (ayrı iş).

## 2. Temel Kararlar

| Karar | Seçim | Gerekçe |
|---|---|---|
| Yer | **Yalnız Cihaz Detayı** (6 panel/cihaz) | Landing'e koymak 36 ızgara olur (kullanıcı kararı) |
| Kritiğe uzaklık metriği | **`band_position_score(value, warn, trip)`** (detector'ın kendi ISO metriği) | Maks. dürüstlük: detector skoruyla birebir; warn altı=0 ("Güvenli") |
| Gauge kimde | **Yalnız seviye-eşikli sensörler** (level_band var) | Slope/varyans'ta seviye bandı yok → sahte gauge uydurmayız (mevcut dürüstlük kuralı) |
| İzleyen katman kaynağı | **Config'ten türet** (aktif kural sensörü + statistical `sensors`) | Gerçek izleme kapsamı; statik uydurma değil |
| Yakalayan katman | **`rule_name`'den** (Kural / İstatistik / Çoklu katman) + `alert.score` | Uyarı gerçek detector çıktısı |
| Skor gösterimi | Uyarı varsa **gerçek `alert.score`**; sağlıkken seviye sensöründe anlık `band_position_score` | İkisi de gerçek |

## 3. Mimari — Modüller

**Yeni saf modül `src/dashboard/detection.py`** (streamlit/DB import etmez; `detectors.config` okuma modeline bağımlı; unit-testli):
- `RULE_SENSOR: dict[str, str | None]` — kural adı → hedef sensör (`motor_temperature_high→motor_temperature`, `motor_current_high→motor_current`, `vibration_elevated→vibration`, `hydraulic_pressure_decline→hydraulic_pressure`, `motor_voltage_erratic→motor_voltage`; `sensor_frozen→None` [params'tan], `sensor_out_of_range→None` [bounds tümü]).
- `LAYER_RULE = "Kural"`, `LAYER_STAT = "İstatistik"`.
- `watching_layers(config: DetectorConfig | None, sensor: str) -> list[str]` — sensörü izleyen katmanlar:
  - "Kural": aktif (enabled) bir kural bu sensörü hedefliyorsa (RULE_SENSOR doğrudan eşleşme; `sensor_frozen` için `params['sensor']`; `sensor_out_of_range` için `params['bounds']` anahtarları).
  - "İstatistik": aktif bir statistical dedektörün `sensors` param'ı bu sensörü içeriyorsa (param yok/None → tüm sensörler).
  - config None → boş liste.
- `catching_layer(rule_name: str) -> str` — `fused(` ile başlıyor → "Çoklu katman"; `three_sigma:`/`iqr:` → "İstatistik"; aksi → "Kural".

**`band_position_score`** — `detectors.scoring`'ten import (mevcut; dashboard zaten detectors.config/fusion import ediyor → katman döngüsü yok, scoring saf).

**`src/dashboard/styles.py`** (MODIFY): saf builder'lar + CSS:
- `layer_chips_html(watching: list[str], caught: str | None, score: float | None) -> str` — "İzleyen: Kural · İstatistik" (sağlık) veya "Yakalayan: <caught>" vurgulu + `skor {score:.2f}` (uyarı). Boşsa boş string.
- `distance_gauge_html(pct: int, severity: str) -> str` — ince gauge bar (dolum=pct%, renk severity'den: warn/critical/ok) + "%{pct}" veya pct==0 → "Güvenli". `pct` çağrı tarafında `round(band_position_score*100)` (0..100).
- CSS: `.mg-layers`, `.mg-chip`, `.mg-chip--on`, `.mg-gauge`, `.mg-gfill`, `.mg-gpct`. Mevcut palet/mono yeniden kullanılır. Serbest metin html.escape.

**`src/dashboard/app.py`** (MODIFY `_render_device_detail`): her sensör için mevcut `panel_header_html` + grafik arasına:
- `caught`/`score`: bu sensöre ait açık uyarı varsa (`device_alerts` içinde `a.sensor == sensor`, en yüksek severity) `catching_layer(alert.rule_name)` + `alert.score`; yoksa None.
- `layer_chips_html(watching_layers(config, sensor), caught, score)`.
- `band = level_band(config, sensor)`: varsa `pct = round(band_position_score(last_val, band.warn, band.trip)*100)` (uyarı varsa `round(alert.score*100)` — gerçek skor) → `distance_gauge_html(pct, badge)`. Yoksa gauge yok.
- Gözlem modu korunur (yalnız okuma).

## 4. Bileşen Tasarımı

**Panel (sağlıklı, seviye sensörü — örn. Motor Sıcaklığı):**
```
●  Motor Sıcaklığı   NORMAL                     76 °C
   İzleyen:  Kural · İstatistik
   Kritiğe uzaklık  ▕░░░░░░░░░░▏ Güvenli   (uyarı 95° · kritik 130°)
   [ radar grafiği ]
```
**Panel (uyarılı, seviye — örn. Motor Akımı DİKKAT):**
```
●  Motor Akımı   DİKKAT                          9.4 A
   Yakalayan:  **Kural**  ·  skor 0.20
   Kritiğe uzaklık  ▕███░░░░░░░▏ %20   (uyarı 9.0 · kritik 11.0)
   [ radar grafiği ]
```
**Panel (uyarılı, seviye-eşiği yok — örn. Hidrolik KRİTİK):**
```
●  Hidrolik Basınç   KRİTİK                       12 bar
   Yakalayan:  **Kural (eğim)**  ·  skor 1.00
   (gauge YOK — eğim arızası; meta: düşüş sınırı −3/−6 bar/dk)
   [ radar grafiği ]
```

Gauge rengi durum rozetinden (ok→nötr/yeşil dolum yok, warning→amber, critical→kırmızı). 0% → bar boş + "Güvenli".

## 5. Veri Akışı (panel başına, _render_device_detail içinde)

```
device_alerts (cihaza + zaman penceresine filtreli, mevcut)
her sensör:
  last_val = fetch_window(...)[-1].value (mevcut)
  badge = sensor_badge(device_alerts, sensor) (mevcut)
  alert = bu sensöre ait en yüksek severity açık uyarı | None
  caught = catching_layer(alert.rule_name) if alert else None
  score = alert.score if alert else None
  watching = watching_layers(config, sensor)
  band = level_band(config, sensor)
  pct = round((alert.score if alert else band_position_score(last_val, band.warn, band.trip))*100) if band else None
  → panel_header_html + layer_chips_html(watching, caught, score) + (distance_gauge_html(pct, badge) if band) + chart
```

## 6. Test Stratejisi

- **`detection.py` (saf birim):** `watching_layers` — seviye sensörü → ["Kural","İstatistik"] (demo config); motor_voltage → ["Kural","İstatistik"]? (statistical sensors'ta yok → yalnız ["Kural"]); mast_position → statistical yok + kural yok (yalnız sensor_out_of_range bounds → "Kural") → ["Kural"]; disabled kural → düşer; config None → []. `catching_layer` — fused→"Çoklu katman", three_sigma:/iqr:→"İstatistik", motor_temperature_high→"Kural".
- **`styles.py`:** `layer_chips_html` — sağlık (İzleyen + chip'ler), uyarı (Yakalayan + vurgu + skor), html.escape; `distance_gauge_html` — pct=0→"Güvenli", pct>0→"%N" + dolum + severity sınıfı.
- **`band_position_score` reuse:** mevcut scoring testleri yeterli (yeniden test yok).
- **Mevcut testler yeşil;** app.py ince → boot smoke korunur.
- **Canlı doğrulama (closure):** demo_up → Cihaz Detayı: sağlıklı sensörde "İzleyen: Kural · İstatistik" + gauge "Güvenli"; arızalı cihazda (003 hidrolik / 005 sıcaklık) yakalayan katman + gerçek skor + gauge dolu; slope/varyans sensöründe gauge yok ama katman+skor var.

## 7. Değişmeyen Kontratlar

`Anomaly`/`fuse_anomalies`/`Detector`/`_detect_once`/füzyon/skorlama/migration/gözlem modu DEĞİŞMEZ. Dashboard yalnız okur. `band_position_score` salt okunur reuse. Landing (Operasyon Merkezi) kartları DEĞİŞMEZ. Streamlit-native. Sektör-nötr.

## 8. Açık Uçlar / Riskler

- **`band_position_score` warn altı = 0:** sağlıklı seviye sensörü "Güvenli/%0" gösterir (detector ile tutarlı, dürüst). Arıza gelişince gauge dramatik dolar (canlı demo anı). "Eşiğe yaklaşma"yı gauge değil radar grafiği (çizgi amber zone'a yaklaşır) gösterir.
- **`watching_layers` statik kural→sensör haritası:** RULE_SENSOR küçük+stabil; yeni kural eklenince güncellenmeli (yorum düşülür). Statistical `sensors` config'ten dinamik.
- **fused uyarının temsilci sensörü:** yalnız temsilci sensör panelinde "Yakalayan" görünür (mevcut overlay davranışıyla tutarlı); diğer sensörler "İzleyen" gösterir.
- **Skor [0,1] → %:** round; gauge dolum CSS width %.

# Dashboard — İki Sayfa Gezinme + "Radar" Grafikler Tasarım Dokümanı

> **Tek hakem:** Bu doküman dashboard'un ikinci yeniden-tasarım dalgasını bağlar. Brainstorming 2026-06-20.
> **Bağlam:** [Clean Corporate redesign](2026-06-19-dashboard-redesign-clean-corporate-design.md) (Türkçe etiketler,
> durum-odaklı kartlar, KPI bandı, iki-eksen uyarılar) `dashboard-redesign-clean-corporate` dalında uygulandı. Kullanıcı
> canlı görselde iki kök sorun teşhis etti: (1) **tek sayfa** — tüm cihazlar + detay aynı ekranda; (2) **grafikler hiçbir
> şey anlatmıyor** — sadece ham trend; bakan kişi cihazın normal mı anormal mı olduğunu anlayamıyor. Sistem aslında
> "sürekli analiz edip anormal olunca alarm veren erken radar" → ekran da bunu söylemeli.
> **Kısıt (CLAUDE.md):** Streamlit-native (React/özel frontend YOK). Veri/tespit/mantık katmanı DEĞİŞMEZ — sunum.
> Eşik/sayı değerleri **config'ten** okunur (hard-code yok; config = tek hakikat). Sektör-nötr.

## 1. Amaç ve Kapsam

**Sorun:**
1. **Tek sayfa** — filo özeti, uyarılar, yönetim ve seçili cihazın 6 grafiği hep birlikte; yönetici için kalabalık, IT lead için derine inme yolu yok.
2. **Grafikler referanssız** — ham telemetri çizgisi; "iyi mi kötü mü, sınıra ne kadar yakın?" görünmüyor. Erken-uyarı/kestirimci sistemin asıl değeri (eşiğe göre trend) ekranda yok.

**Çözüm:**
- **İki sayfa:** **Filo Genel Bakış** (açılış — bir-bakışta durum) + **Cihaz Detayı** (soldaki menüden cihaz seçilince yalnız o cihaz). Tek `app.py`, Streamlit-native gezinme (ağır multipage framework YOK).
- **"Radar" panelleri (Cihaz Detayı):** her sensör paneli durum etiketi (NORMAL/DİKKAT/KRİTİK) + şu anki değer + gerçek eşiklere göre **yeşil/sarı/kırmızı bölgeli** grafik. Durum etiketi gerçek anomali motorundan; eşikler config'ten.

**Kapsam içi:** sunum/gezinme katmanı — `app.py` (gezinme + cihaz-detay render); `charts.py` (eşik-bölge katmanları); yeni saf `thresholds.py`; `labels.py`/`fleet.py`/`styles.py` küçük saf eklemeler.
**Kapsam dışı:** veri/tespit/reconciliation/`fleet.py` türetim çekirdeği; yeni ağır bağımlılık; slope/varyans'ı dashboard'da yeniden hesaplama (detector mantığını taklit etme — YAGNI + dürüstlük); gerçek firma markası.

## 2. Temel Kararlar (brainstorming, 2026-06-20)

| Karar | Seçim | Gerekçe |
|---|---|---|
| Gezinme | **İki sayfa: Filo → Cihaz Detayı (sol menü seçimi)** | Yönetici "bir bakış" + IT lead "derine in"; her izleyici doğru yoğunluk |
| Gezinme mekanizması | **Tek `app.py` + `st.session_state` sürücülü sol-menü seçimi** (st.navigation/pages YOK) | Mevcut fragment + cache_resource + sys.path bootstrap ile en az sürtünme; basit, sağlam (Kuzey Yıldızı) |
| Cihaz Detay paneli | **A — Referans-bölgeli panel** (durum + eşik + trend tek panelde) | İzleme/SCADA standart deseni; "radar" hissini en iyi veren (görsel companion'da seçildi) |
| Eşik bölgeleri | **Yalnız seviye-eşikli sensörlere** (sıcaklık, akım, titreşim); slope/varyans/kuralsız sensörde bant YOK | Dürüstlük: detector seviye-eşiği kullanmayan sensöre sahte yatay bant uydurmayız |
| Durum etiketi kaynağı | **Gerçek açık uyarılar** (sensöre açık uyarı varsa severity'sinden) | Naif eşik değil; ekrandaki "radar" gerçek çok-katmanlı motordan |
| Eşik değerleri | **`config/detectors.yaml`'tan okunur** | Config = tek hakikat (hard-code yasak); bölgeler gerçek eşiklerle birebir |
| Filo Genel Bakış | **Mevcut hâliyle korunur** (bir-bakışta kartlar — başkan için) | Clean Corporate redesign'da çözüldü; yalnız grafik bloğu detay sayfasına taşınır |

## 3. Mimari — Modüller

**Yeni saf modül `src/dashboard/thresholds.py`** (streamlit/DB import etmez; `detectors.config` okuma modeline bağımlı, unit-testli):
- `LevelBand` (frozen dataclass): `warn: float`, `trip: float`.
- `SENSOR_LEVEL_RULES: dict[str, tuple[str, str, str]]` — seviye-eşikli sensörler → `(rule_name, warn_param, trip_param)`:
  - `motor_temperature` → `("motor_temperature_high", "critical_threshold_c", "trip_c")`
  - `motor_current` → `("motor_current_high", "threshold_a", "trip_a")`
  - `vibration` → `("vibration_elevated", "threshold_g", "trip_g")`
- `level_band(config: DetectorConfig, sensor: str) -> LevelBand | None` — sensör seviye-eşikli ve ilgili kural **enabled** ise config param'larından `LevelBand` üretir; değilse (kuralsız/slope/varyans/disabled/eksik param) `None`. `trip <= warn` ise `None` (çizilemez bölge — savunmacı). Saf: yalnız config nesnesini okur.

**`src/dashboard/labels.py`** (MODIFY): sensör-seviyesi durum sözlüğü ekle:
- `SENSOR_STATUS_LABELS: dict[str,str] = {"ok":"NORMAL","warning":"DİKKAT","critical":"KRİTİK"}` + `sensor_status_label(badge: str) -> str`.
- Gerekçe: bir **mast** "SAĞLIKLI" (mevcut `BADGE_LABELS`), bir **sensör okuması** "NORMAL" daha doğal okunur. DİKKAT/KRİTİK ortak. İki ayrı kavram, tek tutarlı dağıtım.

**`src/dashboard/fleet.py`** (MODIFY): iki saf ekleme — (1) severity→rozet mantığı şu an `derive_device_health` içinde **gömülü** (yeniden-kullanılabilir fonksiyon/dict YOK); onu küçük saf `severity_to_badge(severities: list[str]) -> str` helper'ına **çıkar** ve `derive_device_health` de bunu çağırsın (DRY, davranış aynen korunur). (2) `sensor_badge(device_alerts: list[Alert], sensor: str) -> str` → o sensöre açık uyarıların severity'lerini toplayıp `severity_to_badge` ile `ok|warning|critical` rozetine çevirir (uyarı yoksa `ok`). **Mevcut filo semantiğiyle birebir tutarlı:** yalnız `critical` → `critical`; diğer her açık severity (`high` dahil) → `warning`; yok → `ok`. Türetim çekirdeği (`derive_fleet`/`compute_kpis`) davranışsal olarak DEĞİŞMEZ. `SEVERITY_RANK` gerekirse kanonik kaynaktan (`from detectors.fusion import SEVERITY_RANK`) alınır — `fleet` re-export'undan değil (Iter 8.8 dedup yönü).

**`src/dashboard/charts.py`** (MODIFY): `build_sensor_chart(frame, alerts, sensor, unit, band: LevelBand | None = None)` — yeni opsiyonel `band`:
- `band is None` → mevcut davranış (geriye-uyumlu: yalnız çizgi + anomali overlay).
- `band` verilirse: (a) y-ekseni domain'i **eşikleri kapsayacak** şekilde genişletilir (`[min(data_min, 0/​warn), max(data_max, trip)]` + küçük pay) → çizginin sınıra ne kadar uzak olduğu görünür; (b) üç `mark_rect` bölge: yeşil (taban→warn), sarı (warn→trip), kırmızı (trip→tavan), düşük opaklık; (c) `warn` ve `trip`'te kesikli `mark_rule` + etiket. Anomali overlay katmanları (bant/işaret/etiket) korunur ve bölgelerin üstünde kalır. Renkler mevcut paletten (`SEVERITY_COLORS` + yeşil/sarı sabitleri).

**`src/dashboard/styles.py`** (MODIFY): saf `panel_header_html(sensor_label: str, status_label: str, badge: str, value_str: str, meta_str: str) -> str` — panel üst bloğu: sensör adı + renkli durum pill'i (`badge` → renk sınıfı) + şu anki değer + meta satırı (eşik/limit açıklaması). `html.escape` ile serbest metin kaçışlanır. CSS: `.mg-panel*` sınıfları (başlık, pill, meta) `APP_CSS`'e eklenir. Gerekirse küçük nav/başlık CSS'i (geri-dön butonu, sayfa başlığı).

**`src/dashboard/app.py`** (MODIFY — ince wiring):
- **Gezinme:** sol menüde **tek `st.sidebar.selectbox`** (yeni radio değil — mevcut cihaz-selectbox desenini izler, iki-widget etkileşim riskini en aza indirir) — seçenekler `["🏠 Filo Genel Bakış", *device_labels]`, `key="nav"` ile `st.session_state`'e bağlı. `🏠 Filo` → mevcut `_render_overview` + `_render_alert_management`. Bir cihaz → yeni `_render_device_detail(repository, device_id, window, detector_config)`.
- **Geri dön:** Cihaz Detayı üstünde `← Filoya dön` butonu; `on_click` callback `st.session_state["nav"]`'i filoya set eder (widget-state idiyomu).
- **`_render_device_detail`** (fragment, `run_every="2s"`): başlıkta cihaz adı + rozet; zaman-aralığı seçici; 6 sensör 2×3 (`st.columns(3)`): her hücrede `panel_header_html` (durum=`sensor_badge`, değer=son okuma, meta=eşik/limit metni) + `st.altair_chart(build_sensor_chart(..., band=level_band(config, sensor)))`. Açık uyarılar `_fetch_alerts_safe`'ten (cihaza filtreli). Gözlem modu korunur.
- **Config:** `_get_detector_config()` (`@st.cache_resource`) `config/detectors.yaml`'ı `load_detector_config` ile bir kez okur; dosya yok/bozuksa `None` → tüm `band`'ler `None` (graceful, bölgesiz grafik). Yol `DASHBOARD_DETECTORS_CONFIG` env veya varsayılan `config/detectors.yaml`.
- **Meta metni (sensör tipine göre, dürüst):**
  - seviye (sıcaklık/akım/titreşim): `Şu an {v} · Uyarı {warn} · Kritik {trip}`
  - slope (hidrolik): `Şu an {v} bar · düşüş sınırı {warn}/{trip} bar/dk` (bölge yok)
  - varyans (voltaj): `Şu an {v} V · dalgalanma sınırı {warn} V` (bölge yok)
  - kuralsız (mast_position): `Şu an {v} mm` (bölge yok)
- Fragment yapısı (filo 5s / detay 2s) korunur. Tek-fetch sorgu bütçesi korunur.

## 4. Veri Akışı (Cihaz Detayı)

```
sol menü seçimi (session_state nav) → device_id
  _get_detector_config() (cache) ─┐
  _fetch_alerts_safe() → device_alerts (sensöre filtre)
  her sensör için:
     fetch_window(device, sensor, since) → frame, son değer
     sensor_badge(device_alerts, sensor) → durum rozeti  → panel_header_html
     level_band(config, sensor) → band | None            → build_sensor_chart(band)
  st.columns(3) ızgarasında panel başlığı + grafik
```

## 5. Test Stratejisi

- **`thresholds.py` (saf birim):** `level_band` — seviye sensörü enabled kural → doğru `LevelBand`; slope/varyans/mast_position → `None`; disabled/eksik kural → `None`; `trip<=warn` → `None`. Gerçek `detectors.yaml.example` değerleriyle bir entegrasyon-tadında test (sıcaklık 95/130, akım 9/11, titreşim 0.37/0.50).
- **`charts.py`:** `band=None` → mevcut testler aynen geçer (geriye-uyumluluk); `band` verilince — chart spesifikasyonunda bölge `mark_rect` katmanları + eşik kuralları var, y-domain eşikleri kapsıyor (chart dict introspection mevcut test desenindeki gibi).
- **`labels.py`:** `sensor_status_label("ok")=="NORMAL"` vb. + fallback.
- **`fleet.py`:** `sensor_badge` — o sensöre kritik+uyarı açıkken `critical`; yalnız warning → `warning`; uyarı yok → `ok`; başka sensörün uyarısı bu sensörü etkilemez.
- **`styles.py`:** `panel_header_html` — doğru pill rengi (badge→sınıf), değer/meta gömülü, `html.escape` (meta/`<` kaçışı).
- **Mevcut testler yeşil kalır** (logic değişmez). **app.py** ince → headless boot smoke (boş-DB graceful) korunur; gezinme manuel/canlı.
- **Canlı doğrulama (closure):** `demo_up.sh` → kullanıcı ekran görüntüsü → iterasyon. Hedef: (1) sol menüden cihaz seçince yalnız o cihaz açılıyor + geri dön; (2) seviye sensörlerinde yeşil/sarı/kırmızı bölge + eşik çizgileri render oluyor, çizginin sınıra uzaklığı görünüyor; (3) her panelde durum etiketi doğru; (4) slope/varyans/position'da bant yok ama durum+çizgi var; (5) 6-cihaz demo'da arızalı cihazda doğru panel kırmızı/sarı.

## 6. Değişmeyen Kontratlar

`Anomaly`/`fuse_anomalies`/`Detector`/`_detect_once` reconciliation+deadband+severity-banttan/repository/`fleet.py` türetim çekirdeği/`split_alerts_by_axis`/gözlem modu/veri+tespit katmanı/migration şeması DEĞİŞMEZ. Dashboard yalnız okur + uyarı durumu (ack) yazar. `build_sensor_chart` imza **geriye-uyumlu** genişler (`band` opsiyonel, default `None`). Streamlit-native (yeni bağımlılık yok). Sektör-nötr. Eşikler config'ten.

## 7. Yürütme Notu

Bu ortamda subagent'lar Bash/Write izinsiz → controller-inline implement + salt-okunur reviewer hibridi. Her task TDD (saf helper'lar) + tam suite + mypy strict + ruff + CI yeşil. Görsel doğrulama kullanıcı ekran görüntüleriyle iteratif (canlı `demo_up.sh`). Bağımsız plan-review + final whole-branch review. Aynı `dashboard-redesign-clean-corporate` dalına devam.

## 8. Açık Uçlar / Riskler

- **Füzyon temsilci-sensör:** `fused(N)` uyarısı yalnız temsilci `Alert.sensor`'a atfedilir → o cihazda birden çok sensör anormalse yalnız temsilci paneli işaretlenir (mevcut overlay davranışıyla tutarlı). Kabul; not düşülür. (Gerçek-donanım fazında çok-sensör atıf genişletilebilir.)
- **Cyclic sensör tepe-eşiği:** akım/titreşim eşiği "yükselme-anı tepe ortalaması" üzerine; panelde düz yatay çizgi "tepeler bunu aşmamalı" olarak okunur — dürüst yaklaşım, metinde sensör state'i tooltip'te zaten var. Yanıltma riski düşük; bölge yalnız bu 3 sensörde.
- **Streamlit session_state + fragment etkileşimi:** gezinme `session_state` + geri-dön callback ile; widget-state set idiyomuna uyulur (callback içinde set). Risk düşük; canlı smoke'ta doğrulanır.
- **Config okuma:** dashboard `detectors.yaml` okur (yeni bağımlılık değil, mevcut `detectors.config`); dosya yoksa graceful bölgesiz. Demo'da `demo_up.sh` config'i kopyalar → mevcut.
- **Sürüm:** Streamlit 1.36.0 sabit; CSS/fragment buna göre.

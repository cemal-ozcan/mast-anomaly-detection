# Faz 8 Iter 8.2 — Dashboard Görsel Zenginleştirme Tasarım Dokümanı

> **Tek hakem:** Bu doküman Iter 8.2'nin tasarım kararlarını bağlar. Brainstorming 2026-06-03
> (visual companion ile; girdi: `docs/notes/2026-06-03-faz8-iter8-2-dashboard-improvement-notes.md`).
> Kısıt (CLAUDE.md): **Streamlit-native — React/özel frontend YOK.**

## 1. Amaç ve Kapsam

Mevcut dashboard çalışıyor ama "default Streamlit prototip" görünümünde — yöneticiye 15 dk'da
gösterilecek demo için etkileyici değil. Bu iterasyon dashboard'ı görsel olarak zenginleştirir:
ilk bakışta filo durumu, severity-stilli uyarılar, zengin grafikler + anomali overlay, tema.

**Tek iterasyon** (8.2a/8.2b bölünmesi YOK — kullanıcı kararı): iş tamamen görsel katmanda,
detector/ingestion/storage core'una dokunulmaz (tek istisna: yeni read-only repository metodu, § 6).

## 2. Temel Kararlar (brainstorming çıktısı, 2026-06-03)

| Karar | Seçim | Reddedilen alternatifler |
|---|---|---|
| Bilgi mimarisi | **A: Tek sayfa komuta merkezi** (KPI → filo kartları → uyarı akışı → cihaz grafikleri, tek scroll) | Sekmeli hiyerarşi (wow dağılır), drill-down kartlar (state karmaşıklığı) |
| Tema | **B: Açık kurumsal** (beyaz + lacivert vurgu, pastel severity zeminleri; `.streamlit/config.toml`) | Koyu kontrol odası, lacivert+amber (kullanıcı beyaz tonları tercih etti) |
| Grafik kütüphanesi | **Altair** (Streamlit ile gelir — YENİ BAĞIMLILIK YOK; hover/eşik/bant/zoom yeterli) | Plotly (yeni bağımlılık, marjinal etkileşim artısı) |
| Filo kartları | **B: Bilgi kartı** (rozet + state + son değerler vurgulu + açık uyarı sayısı + kural adı) | Minimal rozet (neden? cevapsız), spark kartı (bilgi tekrarı + maliyet) |
| Anomali overlay | **B: Severity bandı + kural etiketi** + hover tooltip | Yalnız bant (kural tabloda kalır), eşik çizgisi (state-koşullu eşiklerde yanıltıcı) |
| Flicker (Iter 8.1) | **Dashboard-side yumuşatma:** "Cihaz özeti" varsayılan görünümü (cihaz başına en son açık uyarı); ham satırlar durum filtrelerinde durur | Detector-side hysteresis (core değişikliği — kapsam dışı), hiç dokunmama |

## 3. Sayfa Yapısı (yukarıdan aşağıya, tek scroll)

1. **Başlık:** `st.title("Mast Filo İzleme")` + `st.caption` alt başlık.
2. **KPI satırı:** `st.columns(4)` + `st.metric`: *Cihaz sayısı · Açık uyarı · Kritik uyarı ·
   Son tespit (göreli zaman)*. Delta okları YOK (kıyas baseline'ı gerektirir — YAGNI).
3. **Filo sağlık kartları:** `st.columns(N)` + `st.container(border=True)`: cihaz adı + sağlık
   rozeti (🟢 OK / 🟡 UYARI / 🔴 KRİTİK) + anlık state + 6 sensörün son değeri kompakt, birimli
   (açık uyarıyla ilişkili sensör vurgulu) + açık uyarı sayısı + en kritik kural adı (en yüksek severity'li,
   eşitlikte en güncel açık uyarının `rule_name`'i). **Salt-görüntü** (drill-down yok; cihaz
   seçimi sidebar'da kalır).
4. **Uyarı akışı:** severity-stilli tablo (pandas `Styler` satır renkleri + severity emoji +
   göreli zaman kolonu). **Varsayılan görünüm "Cihaz özeti"** = cihaz başına en son açık uyarı
   tek satır (flicker yumuşatma) — mevcut filtre selectbox'ına ilk seçenek (index=0) olarak
   eklenir; diğer durum filtreleri (Açık/Tümü/active/acknowledged/resolved) ham satırları
   göstermeye devam eder (dürüstlük).
5. **Uyarı yönetimi:** mevcut selectbox + ack/resolve butonları AYNEN — `main()` içinde,
   fragment DIŞINDA (Faz 7 S1 deseni korunur).
6. **Cihaz detay grafikleri:** sidebar cihaz + zaman penceresi seçimi (mevcut), 2 kolonda
   6 Altair grafiği + anomali overlay (§ 5).

**Fragment yapısı korunur:** üst blok (KPI + kartlar + uyarı akışı) 5s fragment; grafikler 2s
fragment; yönetim kontrolleri fragment dışı. Streamlit 1.36 → `st.experimental_fragment`.

## 4. Tema

`.streamlit/config.toml` (YENİ, commit'li — gitignore'a girmez):

```toml
[theme]
base = "light"
primaryColor = "#1d4ed8"          # lacivert vurgu
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f8fafc"
textColor = "#1e293b"
font = "sans serif"
```

Custom CSS hack YOK. `demo_up.sh` ve manuel `streamlit run` repo kökünden çalıştığı için config
otomatik devreye girer. Severity paleti (kartlar/tablo/grafik bantları tutarlı): critical kırmızı
(`#b91c1c` metin / `#fef2f2` zemin), warning amber (`#a16207` / `#fefce8`), OK yeşil
(`#15803d` / `#f0fdf4`).

## 5. Grafikler + Anomali Overlay

**Builder (saf, `src/dashboard/charts.py`):**
`build_sensor_chart(frame, alerts, sensor, unit) -> alt.LayerChart` — streamlit import etmez.

Katmanlar (alttan üste):
1. **Anomali bandı** — `mark_rect`: `x=window_start → x2=window_end`, severity rengi,
   opacity ~0.15, `clip=True`; x-domain telemetri frame'inden sabitlenir (bant domain'i esnetmesin).
2. **Başlangıç çizgisi** — `mark_rule` kesikli dikey, severity rengi.
3. **Kural etiketi** — `mark_text`: bandın başında üstte `⚠ {rule_name} ({score})`.
4. **Telemetri çizgisi** — `mark_line` lacivert; tooltip: `timestamp, value, state`.

Eksen/etkileşim: y-başlığı `{sensor} ({unit})` (birim DB'den, § 6), `.interactive()` zoom/pan,
`st.altair_chart(theme="streamlit", use_container_width=True)`.

**Boş overlay:** pencerede uyarı yoksa yalnız çizgi katmanı (boş-frame doğru-şema deseni).

**Performans koruması (hard limit):** Altair `max_rows=5000` aşımında **MaxRowsError fırlatır**;
"Tümü" penceresi 1 Hz veride bunu aşar. Çözüm: saf `downsample_frame(frame, max_points=1000)`
(eşit aralıklı seyreltme) her grafik öncesi uygulanır — hem hata önlenir hem 2s yenileme hafif kalır.

**Kabul edilen kozmetik sınır:** aynı pencerede çok uyarıda etiketler üst üste binebilir
(demo'da cihaz başına az epizot; tooltip her zaman çalışır).

## 6. Veri Erişimi

**Yeni repository read metodu (TEK ekleme, read-only — gözlem modu korunur):**

- `fetch_latest_readings() -> list[IngestedReading]` — her `(device_id, sensor)` çifti için en
  güncel okuma, tek SQL (`ROW_NUMBER() OVER (PARTITION BY device_id, sensor ORDER BY timestamp
  DESC)`, SQLAlchemy Core). Kartların state + son değer + `unit` kaynağı (`telemetry.unit`
  kolonu mevcut, sabit birim haritası GEREKMEZ).

**Mevcut read API yeniden kullanılır:**
- Üst blok (5s fragment) sorgu bütçesi: `list_devices()` + `fetch_alerts(None, limit=200)` +
  `fetch_latest_readings()` = **3 sorgu**. KPI sayımları, kart uyarı bilgisi ve uyarı akışı
  görünümleri bu TEK `fetch_alerts` sonucundan client-side türetilir (açık = status ∈
  {active, acknowledged}). Dürüstlük notu: durum filtreleri son-200 uyarı üzerinde client-side
  uygulanır (SQL-filtreli limit-50 yerine) — demo ölçeğinde eşdeğer, semantik fark kabul edildi.
- Grafik overlay: grafik fragment'i (2s, üst bloktan bağımsız) kendi `fetch_alerts(None,
  limit=200)` çağrısını yapar; seçili cihaz client-side filtrelenir (cihaz eşleşmesi + uyarı
  penceresi ∩ grafik zaman penceresi). Yeni repository metodu gerekmez.

## 7. Türetim Kuralları (saf fonksiyonlar)

| Türetim | Kural | Modül |
|---|---|---|
| Sağlık rozeti | Açık uyarılarda `critical` varsa KRİTİK; herhangi açık uyarı varsa UYARI; yoksa OK | `fleet.py` |
| Anlık state | Cihazın en güncel okumasının `state`'i | `fleet.py` |
| Kart değerleri | Son okuma + `unit`; `Alert.sensor` eşleşen sensör vurgulu | `fleet.py` |
| KPI sayımları | Tek `fetch_alerts(None, limit=200)` sonucundan client-side: açık = status ∈ {active, acknowledged}; kritik = açık ∧ severity=critical | `fleet.py` |
| KPI son tespit | Tüm uyarılar arasında (durum fark etmez) en güncel `created_at` → göreli zaman; hiç uyarı yoksa "—" | `fleet.py` + `transform.py` |
| Cihaz özeti | `latest_alert_per_device(alerts)`: cihaz başına en son açık uyarı | `transform.py` |
| Göreli zaman | `relative_time(now, ts)`; `now` enjekte, tz-naive → ValueError (`window_to_since` deseni) | `transform.py` |
| Downsample | `downsample_frame(frame, max_points)` eşit aralıklı seyreltme | `transform.py` |

**Bilinen sınır:** `fused(N)` uyarısının bandı yalnız temsilci `Alert.sensor` grafiğine çizilir;
katkıda bulunan kurallar tooltip'teki açıklamada okunur (açıklama metninden kural→sensör parse
etmek kırılgan — YAPILMAZ).

## 8. Mimari ve Dosya Düzeni

| Dosya | Durum | Sorumluluk |
|---|---|---|
| `.streamlit/config.toml` | YENİ | Tema (§ 4) |
| `src/dashboard/transform.py` | genişler | Saf frame/zaman helper'ları (göreli zaman, cihaz özeti, downsample, stilli uyarı frame'i) |
| `src/dashboard/fleet.py` | YENİ, saf | KPI + kart verisi türetimi; `DeviceHealth` dataclass |
| `src/dashboard/charts.py` | YENİ, saf | Altair chart builder'ları (§ 5) |
| `src/dashboard/app.py` | rework | İnce Streamlit wiring; fragment yapısı § 3 |
| `src/storage/repository.py` | +1 metot | `fetch_latest_readings()` (§ 6) |
| `requirements.txt` | +1 satır | `altair==5.5.0` (venv'deki mevcut sürüm, doğrulandı 2026-06-03; artık doğrudan import — dürüst bağımlılık beyanı, yeni kurulum yok) |

Saf modüller (`transform.py`, `fleet.py`, `charts.py`) streamlit import ETMEZ → birim test edilir;
`app.py` ince kalır. `src/dashboard/app.py` sys.path bootstrap'i korunur.

## 9. Hata Yönetimi / Bilinen Sınırlar

- Boot guard'ları aynen: config/DB yok → `st.error`; `telemetry` tablosu/cihaz yok → `st.info` +
  erken dönüş (fragment'lere ulaşılmaz — AppTest gotcha'sı korunur).
- **Üst blok degrade:** `anomalies` tablosu yoksa (`fetch_alerts` → `OperationalError`)
  KPI/kartlar ÇÖKMEZ: uyarılar boş sayılır, kartlar telemetriden state/değer gösterir +
  "detector henüz çalışmadı" caption'ı. `fetch_latest_readings` hatası → mevcut read-error
  deseni (`st.error` + log).
- Uyarı yönetimi geçişleri: mevcut `_apply_transition` aynen.
- Bilinen sınırlar: fused bandı temsilci sensörde (§ 7); etiket üst üste binmesi (§ 5);
  flicker'ın kök çözümü (detector hysteresis) kapsam dışı — yalnız görsel yumuşatma.

## 10. Test Stratejisi

| Katman | Test |
|---|---|
| `transform.py` | `relative_time` (sn/dk/saat + tz-naive ValueError), `downsample_frame` (≤max_points, sıra korunur, küçük frame değişmez), `latest_alert_per_device`, stilli frame kolonları |
| `fleet.py` | Rozet türetimi (critical>warning>OK), kart verisi (vurgu eşleşmesi, unit passthrough), KPI sayımları |
| `charts.py` | `chart.to_dict()` üstünden katman sayısı/encoding (uyarılı 4 katman; uyarısız yalnız çizgi) |
| repository | `fetch_latest_readings`: çoklu cihaz×sensör'de en güncel kazanır, boş DB → boş liste |
| Boot smoke | AppTest boş-DB (mevcut desen) — config.toml ile çökme yok |

Her task sonunda tam suite + mypy + ruff (`.venv/bin/python -m pytest/mypy`, ruff=homebrew).
Altair 5.5.0 `py.typed` taşıyor (doğrulandı 2026-06-03) → mypy override BEKLENMEZ; ilk mypy
koşusunda aksi görülürse pandas-tarzı dar override (yalnız altair).

**Closure: canlı demo smoke ŞART** (Faz 4.2/5.2/8.1 dersi): `./scripts/demo_up.sh` →
(1) tema yüklü, (2) KPI doğru sayıyor, (3) 4 kart senaryoları yansıtıyor (device_001 🟢 /
device_002 🔴 / device_003-004 🟡), (4) dev_002 `motor_current` grafiğinde overlay bandı +
etiket, (5) cihaz-özeti akışı flicker'sız, (6) temiz cihaz 0 FP, (7) temiz teardown.

## 11. Kabul Kriterleri

1. Açılışta "ilk bakış" cevabı: KPI satırı + renk-kodlu filo kartları (hangi cihaz, neden).
2. Uyarı akışı severity-stilli + göreli zaman + cihaz-özeti varsayılan görünümü (churn görünmez,
   ham satırlar filtrelerle erişilir).
3. 6 sensör grafiği Altair: birim, hover tooltip, zoom; anomali bandı + kural etiketi seçili
   cihazın uyarılarını pencere içinde gösterir.
4. Tema aktif — "default Streamlit" görünümü yok.
5. Canlı demo smoke (§ 10) 7 maddesi geçer; mevcut 313 test + yeniler yeşil, mypy + ruff temiz.
6. Gözlem modu korunur: tek yazma yolu mevcut uyarı durumu geçişleri.

## 12. Kapsam Dışı

React/özel frontend (CLAUDE.md mutlak) · detector-side hysteresis · spark kartları (C varyantı —
sonradan yükseltme yolu) · eşik referans çizgileri (state-koşullu eşiklerde yanıltıcı) · skor
standardizasyonu/önceliklendirme (Faz 7'den ertelenmiş) · kart drill-down (Layout C) · yeni
tablo/migration · KPI delta okları.

## 13. Spec'e Karşı Disiplin

Uygulama bu spec'ten saparsa önce spec güncellenir (tek hakem). Eşik/stil değerleri (renk kodları,
max_points=1000, limit=200) implementasyonda ölçümle ince ayar görebilir; mimari kararlar (§ 2)
kullanıcı onayı olmadan değişmez.

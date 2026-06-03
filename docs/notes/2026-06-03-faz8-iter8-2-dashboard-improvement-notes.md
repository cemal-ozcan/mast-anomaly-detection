# Faz 8 Iter 8.2 — Dashboard İyileştirme Ön-Notları

> **Bu bir spec DEĞİL** — Iter 8.2 brainstorming'ine girdi olacak ön-keşif notları (2026-06-03,
> Iter 8.1 kapanışında controller tarafından çıkarıldı). Brainstorming → spec → plan akışı bunu
> başlangıç malzemesi olarak kullanır; kararlar orada netleşir. Kısıt: **Streamlit-native, React/özel
> frontend YOK** (CLAUDE.md).

## Mevcut durum (src/dashboard/app.py + transform.py, Faz 3'ten beri ~değişmemiş)
Tek sayfa, `st.set_page_config(layout="wide")` + `st.title`. Bileşenler:
- **Uyarılar:** düz `st.dataframe(alerts_to_frame(...))` — ham tablo, severity renk/ikon YOK.
- **Uyarı yönetimi:** `selectbox` + 2 buton (Gör/Çöz) — fonksiyonel, sade.
- **Grafikler:** sidebar'dan TEK cihaz seçilir → 6 sensör `st.line_chart` (2 kolon). Birim YOK, hover
  YOK, eşik çizgisi YOK, **anomali overlay YOK**, zoom YOK. `st.subheader(sensor) + st.line_chart`.
- Sidebar: cihaz selectbox + zaman-aralığı selectbox.
- Tema YOK (default beyaz Streamlit). KPI/özet YOK. Filo genel-bakış YOK (aynı anda tek cihaz).

**Özet:** çalışıyor ama "default Streamlit prototip" görünümü — yöneticiye sunum için etkileyici değil.

## Görsel zayıf noktalar (sunum gözüyle)
1. **"İlk bakışta" özet yok** — açılışta ham tablo + 6 küçük grafik; headline rakam yok (filo sağlığı,
   kaç aktif uyarı, kaç cihaz, en kritik durum).
2. **Uyarı tablosu ham** — critical/high/warning görsel olarak aynı; öncelik/renk/ikon, göreli zaman yok.
3. **Grafikler temel** — birim yok, hover yok, **anomali overlay yok** (asıl etkileyici özellik: sensör
   trace'i üstünde anomalinin ne zaman/nerede tetiklendiğini işaretlemek), eşik referans çizgisi yok.
4. **Filo genel-bakış yok** — bir yönetici "hangi cihaz arızalı?" diye tüm filoyu bir arada görmek ister;
   şu an tek cihaz.
5. **Cihaz durum/sağlık göstergesi yok** — anlık state (idle/raising/holding/lowering), son değerler,
   sağlık (OK/uyarı/kritik) rozeti yok.
6. **Tema/marka yok** — default Streamlit; `.streamlit/config.toml` tema + başlık stili "ürün" hissi verir.
7. **Kozmetik flicker (Iter 8.1)** — uyarı listesi ramp sırasında churn eder; cihaz başına "en son durum"
   gösterimi / gruplama bunu yumuşatabilir.

## Aday iyileştirmeler (hepsi Streamlit-native, mevcut veriyle uygulanabilir)
- **KPI başlık satırı** (`st.metric`): # aktif uyarı, # cihaz, # kritik/yüksek, son tespit zamanı (delta okları).
- **Filo sağlık genel-bakışı**: cihaz başına kart/kolon → device_id + anlık state rozeti + son sensör
  snapshot + sağlık durumu (açık uyarılardan türetilir), renk-kodlu (yeşil OK / sarı uyarı / kırmızı kritik).
  Seçince cihaz detayına in.
- **Severity-stilli uyarı akışı**: ham dataframe yerine `st.column_config` / pandas `Styler` (1.36 destekli)
  ile severity renk + emoji + göreli zaman + durum rozeti.
- **Plotly grafikler + anomali overlay** (en etkileyici): `st.line_chart` → `st.plotly_chart`; eksen birimi +
  hover tooltip + eşik referans çizgisi + **anomali pencerelerini trace üstünde işaretle** (seçili cihazın
  anomalilerini `fetch_recent_anomalies`/`fetch_alerts`'ten al → window_start/window_end → plotly vrect/vline).
  NOT: plotly bir bağımlılık kararı (requirements'te var mı kontrol et); alternatif `st.altair_chart`
  (altair Streamlit ile gelir, ek bağımlılık yok). Brainstorming karar verir.
- **Tema**: `.streamlit/config.toml` (dark/branded primaryColor + font).
- **Layout/sekme**: `st.tabs(["Filo Genel Bakış","Cihaz Detay","Uyarılar"])` ile hiyerarşi.

## Mevcut veri/erişim (yeterli mi?)
Repository read API: `list_devices()`, `fetch_window(device, sensor, since)` (IngestedReading: timestamp/
state/value), `fetch_recent_anomalies(limit)`, `fetch_alerts(statuses, limit)` (Alert: severity/status/
window_start/window_end/rule_name/...). **Anlık state + son değer** için son okuma yeterli (fetch_window'un
son satırı). "Cihaz başına en son okuma/sağlık" için yeni bir read-only repository metodu gerekebilir
(latest-per-device) — bu `src/` ekleme olur (gözlem modu korunur), brainstorming değerlendirir.

## Skill notu
`frontend-design` / `vibe-design-fixer` skill'leri "anti-slop" tasarım ilkeleri için fikir verebilir AMA
React/özel frontend üretir — Streamlit-native kısıtı içinde yalnız PRENSİP/ilham için kullan, çıktısını
doğrudan uygulama. Asıl iş Streamlit + (altair/plotly) + st.metric/st.tabs/.streamlit teması.

## Önerilen kapsam kararı (brainstorming'de doğrula)
Tek iterasyon büyük olabilir; olası 2 alt-parça: (8.2a) KPI + filo sağlık genel-bakışı + tema + severity-stilli
uyarılar (layout/hiyerarşi), (8.2b) plotly/altair zengin grafikler + anomali overlay. Ya da hepsi tek iterasyon
— brainstorming north-star'a göre karar verir.

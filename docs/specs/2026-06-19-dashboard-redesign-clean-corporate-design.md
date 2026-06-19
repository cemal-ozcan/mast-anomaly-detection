# Dashboard Yeniden Tasarım — "Clean Corporate" (Sunum/Demo Cilası) Tasarım Dokümanı

> **Tek hakem:** Bu doküman dashboard görsel yeniden-tasarımının kararlarını bağlar. Brainstorming 2026-06-19.
> **Bağlam:** Faz 8 kapandı (POC işlevsel tam). Bu, **sunum-hazırlık cilası**: mevcut Streamlit dashboard
> işlevsel ama görsel olarak amatör → firma yönetim kurulu başkanı + IT team lead'e sunulabilir profesyonel
> bir "komuta merkezi"ne dönüştürülür. **Veri/tespit/mantık katmanı DEĞİŞMEZ** — tamamen sunum.
> **Kısıt (CLAUDE.md):** Streamlit-native kal — React/özel frontend YOK. Sektör-nötr (gerçek firma adı yok).

## 1. Amaç ve Kapsam

**Sorun (iki canlı ekran görüntüsüyle teşhis edildi):**
1. **Filo kartları okunamaz metin yığını** — 6 sensör düz metin, kelimeler ortadan bölünüyor; debug-log hissi.
2. **KPI'lar cansız** — düz sayı, renk yok, "Son tespit —" boşken bozuk görünüyor.
3. **Grafikler amatör** — 1 Hz salınım yoğun "mavi blob", varsayılan renk, minik eksen, devasa dikey yer.
4. **Hiyerarşi yok** — "şu an ne kötü?" baskın değil; Streamlit chrome (Deploy/menü) görünüyor.
5. **Tema uygulanmıyor** — `.streamlit/config.toml` açık tema tanımlı ama tarayıcı tema-seçici eziyor → koyu görünüyor.

**Çözüm:** "Clean Corporate" yön (açık/kurumsal, beyaz + lacivert) — **enjekte CSS ile deterministik** kurulan
profesyonel komuta merkezi. Kapsam: tema/chrome + KPI bandı + filo kartları + iki-eksen uyarılar + grafikler + akış.

**Kapsam içi:** sunum/görsel katman (`app.py` + `charts.py` + yeni saf `styles.py`; gerekirse `transform.py` formatlama).
**Kapsam dışı:** veri/tespit/reconciliation/`fleet.py` türetim mantığı (değişmez); React/özel frontend; yeni ağır bağımlılık; gerçek firma markası.

## 2. Temel Kararlar (brainstorming, 2026-06-19)

| Karar | Seçim | Gerekçe |
|---|---|---|
| Birincil izleyici | **Yönetim kurulu başkanı + IT team lead (sunum)** | Hem "wow" (başkan) hem teknik güven (IT lead) |
| Estetik yön | **Clean Corporate (açık, beyaz + lacivert #1d4ed8)** | Boardroom-dostu, profesyonel rapor hissi |
| Tema kurulumu | **Enjekte CSS (`st.markdown unsafe_allow_html`)** + config.toml taban | Tarayıcı tema-seçici config'i eziyor → CSS deterministik + tam kontrol (kart/tipografi/spacing) |
| Streamlit chrome | **Gizle** (Deploy + #MainMenu + footer + header) | Temiz demo yüzeyi |
| Filo kartları | **Metin yığını → severity-şeritli kompakt kart + hizalı 2-kolon metrik ızgarası** | En büyük okunabilirlik düzeltmesi |
| Grafikler | **2×3 küçük-çoklu ızgara, arızalı sensör vurgulu** | Bir bakışta tüm cihaz; demo dengeli |
| Ürün adı | **"MastGuard"** (sektör-nötr, değiştirilebilir) + basit metin-logo | Gerçek ürün hissi; gerçek firma değil |
| Veri/mantık | **DEĞİŞMEZ** | Faz 8 sağlam; yalnız sunum |

## 3. Mimari — Sunum Katmanı Yapısı

**Yeni saf modül `src/dashboard/styles.py`** (streamlit/DB import etmez — `transform.py`/`fleet.py` gibi saf, unit-testli):
- `APP_CSS: str` — tüm kurumsal CSS (tema renkleri, tipografi, spacing, kart stilleri, chrome-gizleme).
- Saf HTML-builder fonksiyonları (string döner → unit-testlenebilir; app.py `st.markdown(..., unsafe_allow_html=True)` ile basar):
  - `kpi_card_html(label: str, value: str, tone: str) -> str` (tone: neutral/warning/critical → renk).
  - `device_card_html(health: DeviceHealth) -> str` — severity-şerit + badge + state + 2-kolon metrik ızgarası + en kritik kural.
  - `severity_pill_html(severity: str) -> str` — renkli pill.
  - `status_dot(badge: str) -> str` — ●/▲/■ + renk.
- **Güvenlik:** serbest-metin alanları (uyarı `açıklama`, sensör adları) HTML'e gömülürken `html.escape()` ile kaçışlanır (injection önleme; veriler iç/sentetik ama disiplin). Sayısal değerler format'lanır.

**`app.py`** (ince wiring): `set_page_config` + `st.markdown(APP_CSS)` (chrome gizleme dahil) bir kez; özel başlık şeridi (MastGuard + ● canlı + saat); KPI bandı (4 `kpi_card_html`); filo ızgarası (`device_card_html` × cihaz, `st.columns`); iki-eksen uyarı bölümleri (mevcut `split_alerts_by_axis` + temiz tablo/kart); 2×3 grafik ızgarası. Fragment yapısı (5s üst / 2s grafik) korunur. Gözlem modu korunur (salt-okuma + yalnız ack yazımı).

**`charts.py`** (`build_sensor_chart` iyileştirme): lacivert ince çizgi, açık grid, daha büyük/okunur eksen etiketleri, eşit yükseklik, agresif downsample (1 Hz blob → okunur trend), anomali overlay netleştir (bant + işaret + etiket), arızalı sensör başlığı/çerçevesi vurgulu. Mevcut `alerts_to_overlay_frame`/`downsample_frame` yeniden kullanılır/ayarlanır.

**`fleet.py` / `transform.py`:** türetim mantığı DEĞİŞMEZ; yalnız gerekirse küçük formatlama helper'ı (`relative_time`/empty-state zaten var). `DeviceHealth`/`compute_kpis` aynen kullanılır.

## 4. Bileşen Tasarımı

**Başlık şeridi:** sol "🛡 MastGuard · Teleskopik Mast İzleme", sağ "● canlı · {saat}". İnce, kurumsal, lacivert vurgu.

**KPI bandı (4 kart):** Cihaz / Açık Uyarı / Kritik / Son Tespit. Büyük rakam + küçük etiket; tone renk: Kritik>0 kırmızı, Açık Uyarı>0 amber, diğer nötr-lacivert. "Son Tespit" boş → "Henüz yok".

**Filo ızgarası:** cihaz başına kart — üstte severity renk-şeridi + `● device_001` + badge (OK/UYARI/KRİTİK) + `state`; altında **2-kolon hizalı metrik ızgarası** (sensör → değer+birim, kelime bölünmesi YOK); arıza varsa en-kritik kural pill'i + "⚠ N açık". Renk: ok=yeşil, uyarı=amber, kritik=kırmızı şerit/badge. Highlighted sensör değeri renkli.

**Aktif uyarılar (iki eksen):** "🚨 Arıza Uyarıları" + "🔌 Veri Kalitesi". Her satır: göreli zaman ("1 dk önce") + cihaz + renkli severity pill + sensör + kural + skor + okunur açıklama (kesilmez). Kritik üstte. Boş → dostça mesaj. (Tablo yerine temiz satır-kartları veya stillenmiş tablo — implementasyonda okunurluğa göre.)

**Grafikler (2×3):** motor_current, motor_voltage, hydraulic_pressure, motor_temperature, mast_position, vibration. Downsample'lı temiz lacivert çizgi, açık grid, okunur eksen; anomali bandı/işareti net; arızalı sensör kartı vurgulu (renkli başlık/çerçeve). Seçili cihaz sidebar'dan.

**Sidebar:** cihaz + zaman aralığı seçici — sadeleşmiş, kurumsal.

## 5. Test Stratejisi

- **Saf birim (`styles.py`):** her HTML-builder fonksiyonu — doğru tone/renk/sınıf üretimi, `html.escape` ile kaçış (örn. açıklamada `<` kaçışlanır), boş/None girdi. `APP_CSS` non-empty + chrome-gizleme selektörleri içerir.
- **Mevcut testler yeşil kalır:** `transform.py`/`fleet.py`/`charts.py` saf testleri (logic değişmez); `app.py` ince (unit yok, boot smoke + canlı).
- **app.py:** headless boot smoke (boş-DB graceful) korunur.
- **Canlı doğrulama (closure):** `demo_up.sh` → kullanıcı ekran görüntüsü → iterasyon. Hedef: açık kurumsal tema render oluyor (koyu değil), chrome gizli, kartlar okunur (metin-yığını yok), KPI renk-kodlu, grafikler okunur, iki-eksen uyarı temiz. Başkan+IT-lead sunumuna uygun.

## 6. Değişmeyen Kontratlar

`Anomaly`/`fuse_anomalies`/`Detector`/`_detect_once`/repository/`fleet.py` türetimi/`transform.split_alerts_by_axis`/gözlem modu/veri katmanı DEĞİŞMEZ. Dashboard yalnız okur + uyarı durumu (ack) yazar. Streamlit-native (yeni ağır bağımlılık yok; altair mevcut). Sektör-nötr.

## 7. Yürütme Notu

Bu ortamda subagent'lar Bash/Write izinsiz → controller-inline + salt-okunur reviewer hibridi. Her task TDD (saf
styles helper'ları) + tam suite + mypy + ruff + CI. **Görsel doğrulama kullanıcı ekran görüntüleriyle iteratif**
(canlı `demo_up.sh`). Bağımsız plan-review + final review.

## 8. Açık Uçlar / Riskler

- **Streamlit CSS kırılganlığı:** Streamlit DOM sınıfları sürümle değişebilir; chrome-gizleme + tema CSS'i `1.36.0`'a göre yazılır, sürüm sabit (requirements pin). Risk düşük (sürüm pinli).
- **`unsafe_allow_html` güvenliği:** yalnız iç/sentetik veri + `html.escape` ile sınırlı → injection riski yok.
- **Ürün adı "MastGuard"** placeholder; kullanıcı spec review'da değiştirebilir.

# Dashboard — Açılış Sayfası "Operasyon Merkezi" Tasarım Dokümanı

> **Tek hakem:** Açılış (Filo Genel Bakış) sayfasının yeniden tasarımı. Brainstorming 2026-06-20 (web araştırması: NOC/condition-monitoring en-iyi-pratikleri + görsel companion mockup onaylandı).
> **Bağlam:** İki-sayfa gezinme + radar grafikler + enstrüman-sınıfı görünüm (IBM Plex/grafit/hairline) `dashboard-redesign-clean-corporate` dalında uygulandı. Mevcut açılış hep-yeşilken bilgisiz/boş kalıyor; sistemin *sürekli izlediğini* ve *yakaladığını* anlatmıyor. Hedef: yönetim kurulu başkanı + IT lead'e "kontrol odası" hissi veren, hak ettiği açılış.
> **Kısıt (CLAUDE.md):** Streamlit-native (React YOK). Veri/tespit/gözlem-modu DEĞİŞMEZ. Sayı/eşik config/DB'den (uydurma yok). Sektör-nötr. Yeni ağır bağımlılık yok.

## 1. Amaç ve Kapsam

**Sorun:** Açılış sayfası (a) hep-yeşilken 6 aynı kart + boş bölümler = düşük bilgi; (b) zaman/trend yok (sistemin izlediği/yakaladığı görünmüyor); (c) KPI'lar düz sayaç (sağlık skoru/kapsam/tazelik yok); (d) kartlar tıklanmıyor.

**Çözüm — "Operasyon Merkezi" açılışı (web-araştırma temelli: glanceability + management-by-exception + health-score + süreklilik kanıtı):**
1. **Sağlık hero'su** — sağlık halkası (N/M sağlıklı) + büyük durum metni + kapsam/tazelik subline + izleme süresi.
2. **Kapsam/ölçek şeridi** — mono enstrüman istatistik + **info (i) tooltip'leri**.
3. **Sinyal-öncelikli filo ızgarası** — problemli cihazlar üstte; kartlar **tıklanır (drill-down)**; her kartta **mini sparkline**.
4. **Son 24 saat olay akışı (timeline)** — tespit/çözüm/ack geçmişi (sistemin yakaladığının kanıtı).
5. **Radar zone belirginleştirme** (Cihaz Detayı) — mevcut yeşil/sarı/kırmızı bölgeleri beyaz-zeminde net görünür kıl + canlı doğrula.

**Kapsam içi:** `app.py` (açılış render), yeni saf `overview.py` (hero/stats/timeline saf builder'ları — veya `styles.py`'ye eklenir), `fleet.py` (sıralama + sparkline veri türetimi saf), `charts.py` (sparkline + zone opaklık), `repository.py` (2 yeni okuma metodu), `styles.py` (CSS + tooltip + hero/stat/timeline/sparkline). **Kapsam dışı:** tespit/füzyon/reconciliation; gerçek "uptime" servis-izleme (izleme süresi = veri span'i); yeni bağımlılık.

## 2. Temel Kararlar

| Karar | Seçim | Gerekçe |
|---|---|---|
| Açılış yönü | **Operasyon Merkezi** (hero + kapsam + sinyal-ızgara + timeline) | Görsel companion'da onaylandı; hem başkan hem IT lead |
| Sağlık göstergesi | **Sağlık halkası (N/M sağlıklı donut)** | Web: health-score üst-KPI; tek bakışta "filo iyi mi" |
| Drill-down | **Tıklanır kart → `?dev=` query param → o cihaz sayfası** | Streamlit-native gerçek tıklama (st.query_params); sidebar fallback korunur |
| Sparkline | **Cihaz başına temsilci sensörün son ~60s'i** (problemli→top_rule sensörü, değilse motor_current) | Boş "Sorun yok" yerine gerçek trend; query bütçesi küçük (yerel SQLite) |
| Tooltip | **Saf HTML/CSS "i" + hover** (data-tip) | Streamlit-native, ucuz, JS yok |
| İzleme süresi | **now − en eski telemetri ts** (veri span'i) | Gerçek "uptime" servis-izleme kapsam dışı; demo için dürüst yaklaşım (etiket "izleme süresi") |
| Zone (radar) | **Mevcut band katmanları korunur, opaklık 0.10→0.16 + beyaz zemin** | Zaten kodlu; siyah-zeminde görünmüyordu → beyazda belirgin; tek-yönlü eşik (config) |

## 3. Mimari — Modüller

**Yeni saf modül `src/dashboard/overview.py`** (streamlit/DB import etmez; `alerts.models.Alert`/`fleet.DeviceHealth`/`labels`/`transform.relative_time` + stdlib; unit-testli):
- `FleetSummary` (frozen): `total:int`, `ok:int`, `warning:int`, `critical:int`, `worst:str` ("ok|warning|critical").
- `summarize_fleet(fleet: list[DeviceHealth]) -> FleetSummary`.
- `health_ring_svg(summary: FleetSummary) -> str` — donut SVG (yeşil yay = ok/total; merkez "N/M" + "SAĞLIKLI"); saf string.
- `hero_html(summary, device_count, sensor_count, freshness_str, span_str) -> str` — hero kartı (halka + büyük durum metni + subline + sağ izleme süresi). Durum metni: hepsi ok → "TÜM FİLO SAĞLIKLI"; değilse "{crit} kritik · {warn} dikkat · {ok} sağlıklı" (renkli).
- `CoverageStat` (frozen): `value:str`, `label:str`, `tip:str`.
- `coverage_stats(...) -> list[CoverageStat]` + `coverage_html(stats) -> str` — her stat'ta info tooltip.
- `timeline_events(alerts: list[Alert], now, limit=8) -> list[TimelineEvent]` + `timeline_html(events, now) -> str` — son-24s olaylar; her olay: zaman + durum noktası + "{cihaz} · {kural-düz-türkçe} {durum}" (durum: sürüyor/çözüldü/teknisyen onayı; resolved_at varsa çözüldü). `TimelineEvent` frozen.
- `info_badge_html(tip: str) -> str` — `<span class="mg-info" data-tip="...">i</span>` (html.escape).
- **Güvenlik:** tüm serbest metin html.escape.

**`src/dashboard/fleet.py`** (MODIFY): saf eklemeler — `sort_fleet_by_severity(fleet) -> list[DeviceHealth]` (critical>warning>ok, eşitlikte device_id) + `representative_sensor(health) -> str` (top_rule'dan sensör çıkar; yoksa "motor_current"). Türetim çekirdeği DEĞİŞMEZ.

**`src/dashboard/charts.py`** (MODIFY): `build_sparkline(frame) -> alt.Chart` — minik (yükseklik ~34) eksensiz/gridsiz grafit çizgi (kart sparkline'ı; saf). `ZONE_OPACITY` 0.10→0.16 (zone belirginlik).

**`src/dashboard/styles.py`** (MODIFY): CSS — `.mg-hero*`, `.mg-stats`/`.mg-stat`, `.mg-info` (tooltip `:hover::after`), `.mg-fleet` kart sparkline/tıklama/`.mg-go`, `.mg-tl`/`.mg-ev` (timeline). Mevcut tokenlar (IBM Plex/grafit/hairline/buz-mavisi hover) yeniden kullanılır.

**`src/storage/repository.py`** (MODIFY, read-only — gözlem modu korunur): 
- `earliest_telemetry_timestamp() -> str | None` (`SELECT MIN(timestamp) FROM telemetry`).
- `count_anomalies_since(since: str) -> int` (`SELECT COUNT(*) FROM anomalies WHERE created_at >= :since`).

**`src/dashboard/app.py`** (MODIFY): `_render_overview` yeniden yazılır (eski KPI+summary+fleet+2-eksen-uyarı → hero + kapsam + sinyal-ızgara + timeline + açık-uyarı yalnız varsa). Drill-down: main()'de `dev = st.query_params.get("dev")` → geçerliyse `st.session_state["nav"] = device_label(dev)` + `st.query_params.clear()` (selectbox'tan önce; widget-state idiyomu). Sparkline'lar için cihaz başına `fetch_window(repr_sensor, since=60s)`. Açık uyarı yönetimi (ack) DEĞİŞMEZ. Fragment yapısı (5s) korunur.

## 4. Bileşen Tasarımı (detay)

**Hero:** grid [halka | metin | izleme-süresi]. Halka = inline SVG donut (`stroke-dasharray` = `ok/total*100 100`). Hepsi ok → tam yeşil + "TÜM FİLO SAĞLIKLI"; kritik varsa sol-şerit kırmızı. Subline mono vurgulu: "**6** mast · **36** sensör kesintisiz izleniyor · son veri **2 sn** önce".

**Kapsam şeridi (5 stat + info):** İzlenen Mast (i: "Sisteme bağlı, sürekli izlenen mast sayısı"), Aktif Sensör (i: "Her mastta 6 sensör — toplam izlenen kanal"), Ölçüm Hızı (i: "Saniyede işlenen telemetri ölçümü, ~mast×6"), Veri Tazeliği (i: "En son telemetrinin üstünden geçen süre"), Son 24s Tespit (i: "Son 24 saatte üretilen anomali uyarısı sayısı").

**Sinyal-öncelikli ızgara:** `sort_fleet_by_severity` ile problemliler üstte; her kart `<a href="?dev={device_id}" target="_self">` (tıklanır), hover buz-mavisi, alt satırda sparkline + (problemse) son değer / (sağlıklıysa) "incele →". Ham sensör yığını yok.

**Timeline:** son 24 saat, en yeni üstte, ≤8 olay; satır = mono zaman + durum noktası (kırmızı/amber/yeşil/gri-ack) + düz-Türkçe metin. Olay yoksa "Son 24 saatte olay yok — izleme sürüyor." Kaynak: `fetch_alerts(None, 200)` → 24s filtre.

**Açık uyarılar:** yalnız açık uyarı varsa "Arıza Uyarıları" / "Veri Kalitesi" panelleri gösterilir (mevcut `split_alerts_by_axis` + `alerts_section_html`); yoksa gösterilmez (boş dev bölüm yok — timeline zaten "sürüyor"u anlatır).

## 5. Veri Akışı (Açılış, 5s fragment)

```
fetch_alerts(None,200) → alerts
fetch_latest_readings() → latest (cihazlar + son değer + state + veri tazeliği)
earliest_telemetry_timestamp() → span (izleme süresi)
count_anomalies_since(now-24h) → son-24s tespit
derive_fleet(devices, latest, alerts) → fleet → summarize_fleet → hero
sort_fleet_by_severity(fleet); her cihaz: fetch_window(repr_sensor, now-60s) → sparkline frame
timeline_events(alerts, now) → timeline
açık uyarı varsa split_alerts_by_axis → paneller
```

## 6. Test Stratejisi

- **`overview.py` (saf birim):** `summarize_fleet` (sayımlar+worst); `health_ring_svg` (dasharray = ok/total; merkez metni); `hero_html` (hepsi-ok → "TÜM FİLO SAĞLIKLI"; karışık → renkli sayımlar; escape); `coverage_stats`/`coverage_html` (info tooltip data-tip var); `timeline_events` (24s filtre, sıralama, resolved→"çözüldü", ack→"teknisyen onayı", boş→[]); `info_badge_html` (escape).
- **`fleet.py`:** `sort_fleet_by_severity` (crit>warn>ok, tie device_id); `representative_sensor` (top_rule→sensör; yoksa default).
- **`charts.py`:** `build_sparkline` (eksen yok, yükseklik küçük); mevcut band testleri yeşil (opaklık değişimi yapı kırmaz).
- **`repository.py`:** `earliest_telemetry_timestamp` (boş DB→None; veri varsa min); `count_anomalies_since` (since filtresi) — `migrated_engine`/in-memory fixture'la.
- **Mevcut testler yeşil kalır;** `app.py` ince → boot smoke (boş-DB graceful) korunur.
- **Canlı doğrulama (closure):** `demo_up.sh` → kullanıcı görseli → hero/halka, kapsam+tooltip, sinyal-sıralı tıklanır kartlar+sparkline, timeline; **Cihaz Detayı'nda zone'lar (yeşil/sarı/kırmızı) beyaz-zeminde net görünüyor**; karışık + hep-yeşil durum.

## 7. Değişmeyen Kontratlar

`Anomaly`/`fuse_anomalies`/`Detector`/`_detect_once`/füzyon/migration şeması/gözlem modu/ACK yaşam döngüsü DEĞİŞMEZ. Dashboard yalnız okur + ack yazar. `build_sensor_chart` band imzası (geriye-uyumlu) korunur. Yeni repository metodları salt-okuma. Streamlit-native. Sektör-nötr.

## 8. Açık Uçlar / Riskler

- **Tıklanır kart (query param):** `st.query_params` + `target="_self"` anchor → rerun → nav set. Risk: param↔selectbox senkron döngüsü → param okununca hemen `clear()` + session_state set (selectbox'tan önce). Canlı smoke'ta doğrulanır; sidebar selectbox garantili fallback.
- **Sparkline query bütçesi:** cihaz başına 1 küçük `fetch_window` (6 sorgu/5s). Yerel SQLite'ta önemsiz; çok cihazda gözden geçirilir.
- **İzleme süresi semantiği:** veri span'i (servis-uptime değil) → etiket "izleme süresi"/"kesintisiz izleme" dürüst tutulur.
- **Zone görünürlüğü:** asıl kanıt canlı (Cihaz Detayı, beyaz zemin). Birim test yapıyı doğrular, render'ı değil.
- **Webfont:** IBM Plex CDN; offline → system-ui fallback (mevcut karar).

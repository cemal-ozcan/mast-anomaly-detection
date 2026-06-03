# Faz 7 — Alert Manager (Uyarı Yaşam Döngüsü) Tasarım Dokümanı

> Bu doküman Faz 7'nin **tek hakemidir**. Spec ile çelişen kod kabul edilmez. Spec değişikliği önce bu dosyada yapılır, sonra kod izler. Bu spec brainstorming oturumunda (2026-06-03) kararlaştırıldı; **plan + uygulama** writing-plans → subagent-driven ile yapılacak (Faz 4/5 deseni).

---

## 1. Amaç ve Kapsam

Faz 4 (kural) ve Faz 5 (istatistik) dedektörleri ham anomalileri `anomalies` tablosuna yazıyor ve dashboard onları read-only listeliyor. Faz 7, bu ham anomalileri **yönetilebilir uyarılara** dönüştürür: her uyarının bir **durumu** (yaşam döngüsü) olur ve teknisyen dashboard'dan bunları **yönetir** (gör/kapat).

**Kuzey Yıldızı:** Çalışan, açıklanabilir, küçük. Mevcut `anomalies` tablosu + füzyon + debounce yeniden kullanılır; minimal kolon + ince `src/alerts/` modülü eklenir. Ayrı süreç / MQTT / yeni tablo YOK.

**Kapsam içi (Faz 7 — bu iterasyon):**
- Uyarı yaşam döngüsü: `active → acknowledged → resolved` (ARCHITECTURE § 5 "yaşam döngüsü: yeni, görüldü, kapalı").
- **Auto-resolve:** detector arıza temizlenince (debounce re-arm) cihazın açık uyarılarını otomatik `resolved` işaretler.
- **Manuel yönetim:** teknisyen dashboard'dan uyarıyı `acknowledged` (gör) veya `resolved` (manuel kapat) yapar.
- Dashboard: durum kolonu + duruma göre filtre + ack/resolve yönetim kontrolü.

**Kapsam dışı (ertelendi):**
- Açık **önceliklendirme** katmanı (severity→priority sınıflandırma), **skor normalizasyon standardizasyonu** (Faz 5 ThreeSigma-fence vs IQR-IQR asimetrisi), **suppression / akıllı pencere** kuralları — Faz 7'nin olası 2. iterasyonu veya Faz 6/7 fusion çalışması. *(Füzyon + epizot debounce zaten Faz 4.3/5.1'de yapıldı, değişmez.)*
- Ayrı `python -m alerts` süreci / MQTT-tabanlı alert servisi — değerlendirildi, kuzey yıldızı lehine ELENDİ (brainstorming, 2026-06-03). Detector zaten DB'ye yazıyor; write-side yaşam döngüsü yeterli.
- Bildirim (e-posta/SMS/webhook), auth/kullanıcı kimliği — prototip kapsam dışı.

---

## 2. Temel Kararlar (brainstorming çıktısı, 2026-06-03)

1. **Veri modeli: `anomalies` tablosunu genişlet.** Epizot debounce (Faz 4.3) zaten epizot başına ~1 satır ürettiği için bu satırlar zaten "uyarı"dır. Yeni `alerts` tablosu veya ayrı süreç gereksiz (YAGNI). Migration 003 ile `status`/`acknowledged_at`/`resolved_at` eklenir.
2. **Resolve modeli: otomatik + manuel.** Detector arıza temizlenince auto-resolve (sorumluluk: "arıza sürüyor mu" detector'ın bilgisi); teknisyen ayrıca manuel ack/resolve (sorumluluk: "gördüm / yanlış alarm"). Temiz sorumluluk bölümü.
3. **Eskalasyon davranışı DEĞİŞMEZ.** Faz 4.3'te kural-seti değişince yeni satır yazılır; bu korunur (yeni satır = yeni `active` uyarı). Eski uyarı eskalasyonda `resolved` İŞARETLENMEZ — eskalasyon arızanın kötüleşmesidir, çözülmesi değil; `resolved` demek semantik yalan olur. **Sonuç (kabul edilen, dürüst davranış):** eskalasyon sırasında bir cihazda kısa süre >1 açık uyarı görülebilir; hepsi arıza temizlenince auto-resolve olur.
4. **Gözlem modu korunur.** Dashboard'ın **uyarı durumu** (ack/resolve) yazması "gözlem modu" güvenlik kuralını (CLAUDE.md: cihaza/masta komut gönderme yasağı) İHLAL ETMEZ — bu dahili kayıt yönetimidir, cihaz kontrolü değil. Dashboard yine telemetri yazmaz, hiçbir mast/cihaza komut göndermez.

---

## 3. İterasyon Planı

**Iter 7.1 — Uyarı yaşam döngüsü + dashboard yönetimi (tek iterasyon):**
- Migration 003: `anomalies`'e `status`/`acknowledged_at`/`resolved_at` + `idx_anomalies_status`.
- `src/alerts/` paketi: `lifecycle.py` (saf durum-geçiş kuralları) + `models.py` (`Alert` okuma/yönetim modeli).
- `storage/repository.py`: `acknowledge_alert` / `resolve_alert` / `resolve_open_alerts` / `fetch_alerts` (+ `_row_to_alert`).
- `detectors/service.py` `_detect_once`: re-arm dalında auto-resolve.
- Dashboard: `alerts_to_frame` durum kolonu + filtre + yönetim kontrolü.
- Birim/integration testler + canlı smoke.

*(Faz 7 tek iterasyonda kapanır; önceliklendirme istenirse ayrı bir iterasyon olarak değerlendirilir.)*

---

## 4. Mimari ve Dosya Düzeni

```
src/alerts/                    # YENİ paket (ARCHITECTURE § 5)
├── __init__.py
├── lifecycle.py               # SAF: AlertStatus sabitleri + can_transition + ALLOWED_TRANSITIONS
└── models.py                  # Alert frozen dataclass (okuma/yönetim görünümü)

src/storage/
├── migrations/003_alert_lifecycle.sql   # YENİ: ALTER TABLE + index (version-gated)
├── schema.py                  # MODIFY: anomalies Table'a 3 kolon (DDL ÇALIŞTIRMAZ)
└── repository.py              # MODIFY: 4 alert metodu + _row_to_alert

src/detectors/service.py       # MODIFY: _detect_once re-arm dalı → resolve_open_alerts

src/dashboard/
├── transform.py               # MODIFY: alerts_to_frame status kolonu (Anomaly→Alert)
└── app.py                     # MODIFY: _render_alerts filtre + yönetim kontrolü (fetch_alerts)
```

**Bağımlılık yönü (döngü yok):** `alerts/` saf (dış bağımlılık yok). `storage.repository` → `alerts.models` (`Alert`) + `alerts.lifecycle` (geçiş sabitleri) [storage zaten `detectors.base.Anomaly`'ye bağlı]. `detectors.service` → `storage.repository` (mevcut). `dashboard` → `storage.repository` + `alerts.lifecycle` (buton görünürlüğü). `alerts` hiçbir şeye bağlı değil → döngü yok.

**`Detector` ABC, `Anomaly`, `fuse_anomalies` DEĞİŞMEZ** (Faz 4/5 girdi kontratı). `insert_anomaly` DEĞİŞMEZ — yeni `status` kolonu DB `DEFAULT 'active'` ile dolar (yazma kodu `status` set etmez).

---

## 5. Veri Modeli

**Migration 003 (`003_alert_lifecycle.sql`, version-gated → bir kez çalışır):**
```sql
ALTER TABLE anomalies ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE anomalies ADD COLUMN acknowledged_at TEXT;
ALTER TABLE anomalies ADD COLUMN resolved_at TEXT;
CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies (status, created_at);
```
- `status`: `active` | `acknowledged` | `resolved`. Yeni anomali default `active` (DB default; mevcut `insert_anomaly` değişmez).
- `acknowledged_at` / `resolved_at`: ISO 8601 ms Z, geçiş anında yazılır (nullable).
- `schema.py` `anomalies` Table tanımına 3 kolon eklenir (DDL ÇALIŞTIRMAZ — yalnız expression builder; migrasyon SQL tek kaynak).

**`Alert` modeli (`alerts/models.py`, frozen dataclass — okuma/yönetim görünümü):**
`Anomaly`'nin 9 alanı + `id: int`, `status: str`, `acknowledged_at: str | None`, `resolved_at: str | None`, `created_at: str`. Düz (flat) dataclass — DataFrame transform ve dashboard tüketimi için sade. `Anomaly` (detector yazma kontratı) değişmez; `Alert` ayrı bir okuma modeli (kimlik + durum içerir).

---

## 6. Yaşam Döngüsü

**Durumlar ve geçişler (`alerts/lifecycle.py`, SAF):**
```
active ──(teknisyen: gör)──> acknowledged ──(teknisyen/detector: kapat)──> resolved
   └──────────────(teknisyen/detector: kapat)──────────────────────────────> resolved
```
- `ALLOWED_TRANSITIONS = {active: {acknowledged, resolved}, acknowledged: {resolved}, resolved: set()}`.
- `can_transition(current, target) -> bool`. Dashboard hangi butonu göstereceğine bununla karar verir; repository SQL WHERE ile atomik zorlar.

**Geçiş tetikleyicileri:**
| Olay | Kim | Sonuç |
|---|---|---|
| Yeni arıza epizodu | detector (mevcut) | `active` satır yazılır (`insert_anomaly`, status DEFAULT) |
| Eskalasyon (kural-seti değişir) | detector (mevcut) | yeni `active` satır (eski satır AYNEN kalır, § 2.3) |
| Arıza temizlenir (re-arm) | detector | cihazın TÜM açık (`!= resolved`) uyarıları → `resolved` (auto) |
| Teknisyen "gör" | dashboard | `active → acknowledged` |
| Teknisyen "kapat" | dashboard | `active|acknowledged → resolved` |

**Detector auto-resolve entegrasyonu (`_detect_once`):** mevcut re-arm dalı `if not rule_set: active.pop(device_id, None)`. Yeni: yalnız cihaz `active` dict'te VARKEN (yani izlenen bir arıza gerçekten temizlendiğinde) `repository.resolve_open_alerts(device_id, created_at)` çağrılır, sonra pop. Her poll'da temiz cihaz için boşa UPDATE yapılmaz.

---

## 7. Repository API (yeni metotlar)

- `acknowledge_alert(alert_id: int, acknowledged_at: str) -> bool` — `UPDATE ... SET status='acknowledged', acknowledged_at=? WHERE id=? AND status='active'`. Dönüş: etkilenen satır > 0 (geçiş geçerli miydi).
- `resolve_alert(alert_id: int, resolved_at: str) -> bool` — `UPDATE ... SET status='resolved', resolved_at=? WHERE id=? AND status IN ('active','acknowledged')`.
- `resolve_open_alerts(device_id: str, resolved_at: str) -> int` — `UPDATE ... SET status='resolved', resolved_at=? WHERE device_id=? AND status != 'resolved'`. Dönüş: kapatılan sayı (detector auto-resolve).
- `fetch_alerts(statuses: tuple[str, ...] | None, limit: int) -> list[Alert]` — `statuses` verilirse `status IN (...)` filtreler, None → tümü; `created_at DESC`; `_row_to_alert` ile `Alert` döndürür (id + status dahil). "Açık" görünüm = `("active", "acknowledged")`, tek durum = `("active",)`, tümü = `None`.

Geçiş kuralları SQL WHERE ile **atomik** zorlanır (oku-sonra-yaz yarışı yok). `lifecycle.can_transition` saf doğrulama + dashboard buton görünürlüğü içindir.

---

## 8. Dashboard (Streamlit-native, gözlem modu)

`_render_alerts` fragment'i (`@st.experimental_fragment(run_every="5s")`, Streamlit 1.36):
- **Veri:** `fetch_alerts(statuses, limit)` → `alerts_to_frame` (mevcut kolonlar + `durum` kolonu + `id`).
- **Varsayılan görünüm:** açık uyarılar = `("active", "acknowledged")`; durum filtresi `selectbox` (Açık [default] / Tümü / active / acknowledged / resolved → ilgili `statuses` tuple'ına çevrilir).
- **Yönetim kontrolü:** açık uyarı seç (`selectbox`, alert `id` + kısa etiket) + **Gör (ack)** / **Çöz (resolve)** butonları. Buton görünürlüğü `lifecycle.can_transition(seçili.status, hedef)` ile. Tıklama → `repository.acknowledge_alert`/`resolve_alert` → rerun → tablo tazelenir.
- **Yazma:** dashboard'ın `TelemetryRepository`'si (zaten yazabilir) yalnız uyarı durumu yazar; WAL altında detector ile eşzamanlı (seyrek buton tıklamaları → kabul edilebilir kilit teması).

`alerts_to_frame(alerts: list[Alert]) -> pd.DataFrame`: mevcut `anomalies_to_frame` kolonları (zaman/cihaz/severity/sensör/kural/skor/açıklama) + `durum`. (Mevcut `anomalies_to_frame` + `fetch_recent_anomalies` korunabilir veya `alerts_to_frame`/`fetch_alerts` ile değiştirilir — plan netleştirir; ölü kod bırakılmaz.)

---

## 9. Hata Yönetimi / Bilinen Sınırlar

CLAUDE.md disiplini (spesifik exception, `except Exception` yasak, loguru).
| Durum | Davranış |
|---|---|
| Geçersiz geçiş (ör. resolved'ı ack'leme) | SQL WHERE 0 satır günceller → metot `False` → dashboard "uyarı durumu değişmiş olabilir, yenileyin" info (sessiz no-op, çökme yok) |
| Dashboard yazımında `OperationalError` (DB kilidi vb.) | loguru ERROR + `st.error`; çökme yok |
| `anomalies` tablosu yok (detector hiç çalışmadı) | mevcut davranış (st.info) |

**Bilinen sınırlar (belgelenir — prototip kabul):**
1. **Manuel resolve sırasında süregelen arıza:** teknisyen *aktif* bir arızayı manuel `resolved` ederse, detector'ın in-memory `active` dict'i (ayrı süreç) bunu bilmez → kural-seti değişene veya arıza temizlenene kadar yeni uyarı açılmaz. Auto-resolve yaygın durumu kapsar; manuel resolve yanlış-alarm kapatmak içindir.
2. **Detector restart orphan'ı:** detector yeniden başlarsa `active` dict boşalır; o an açık olan uyarılar, o cihaz tekrar arıza verip temizlenene kadar auto-resolve edilmeyebilir → teknisyen manuel kapatır.
3. **Eskalasyonda >1 açık uyarı:** § 2.3 (kabul edilen dürüst davranış).

---

## 10. Test Stratejisi

Faz 4/5 deseni:
- **Birim (saf):** `alerts/lifecycle.py` geçiş matrisi (`can_transition` tüm durum çiftleri); `dashboard.transform.alerts_to_frame` (durum kolonu, boş liste şeması).
- **Integration (repository):** `acknowledge_alert`/`resolve_alert`/`resolve_open_alerts`/`fetch_alerts` — geçiş guard'ları (active→ack OK, resolved→ack 0 satır), status filtresi, auto-resolve çoklu açık satır.
- **Detector (`_detect_once`):** re-arm'da auto-resolve (açık uyarı `resolved` olur, `resolved_at` yazılır); cihaz `active` değilken boşa UPDATE yapılmaz; eskalasyonda eski satır AYNEN kalır (resolve edilmez).
- **Dashboard `app.py`:** ince presentation (manuel + headless boot smoke).
- **Coverage:** `alerts` paketi ≥%85; storage/dashboard değişen kısımlar test edilir. Her task sonunda tam suite + mypy (`src/alerts` dahil) + ruff (homebrew `ruff`).
- **Canlı smoke:** gerçek `detectors.service.run()` arıza→temizlenme döngüsünde auto-resolve; dashboard'da ack/resolve butonları durum değiştirir; gözlem modu korunur.

---

## 11. Kabul Kriterleri (ROADMAP § Faz 7)

1. **Bir arıza birden fazla dedektör tetiklediğinde tek uyarı.** ✅ ZATEN VAR (Faz 4.3 `fuse_anomalies` → `fused(N)`); değişmez. Faz 7 testleri bunu regresyon olarak doğrular.
2. **Dashboard'da uyarı durumu yönetilebiliyor.** ← Bu iterasyonun ana teslimi: yaşam döngüsü + ack/resolve + filtre.
3. **Yanlış pozitif oranı önceki fazlara göre düşüyor.** Dürüst çerçeve: ham FP'yi Faz 4 epizot debounce zaten düşürdü; Faz 7 yaşam döngüsü (auto-resolve + resolved'ı varsayılan görünümden çıkarma) **aktif uyarı gürültüsünü** azaltır. Açık önceliklendirme/suppression ile ek FP düşüşü ertelendi (§ 1 kapsam dışı).

**Genel:** ≥1 yaşam döngüsü dedektörü çalışır; tüm önceki testler yeşil + yeni testler; mypy strict + ruff temiz; canlı smoke.

---

## 12. Spec'e Karşı Disiplin

- Bu spec Faz 7 boyunca tek hakemdir.
- Faz 4 (kural, fusion, debounce, `anomalies` tablosu) + Faz 5 (istatistik) + Faz 2/3 (storage, dashboard) bu fazın **girdi kontratıdır**; Faz 7 bunları okur + genişletir (status kolonları, alerts paketi, dashboard yönetimi), bozmaz. `Detector` ABC, `Anomaly`, `fuse_anomalies`, `insert_anomaly` DEĞİŞMEZ.
- Gözlem modu: dashboard yalnız uyarı **durumu** yazar (telemetri değil, cihaz komutu değil); detector yalnız telemetry okur + anomalies yazar (status dahil).

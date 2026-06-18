# Faz 8 Iter 8.5 — Uyarı Yaşam Döngüsü Reconciliation Tasarım Dokümanı

> **Tek hakem:** Bu doküman Iter 8.5'in tasarım kararlarını bağlar. Brainstorming 2026-06-18.
> **Bağlam:** POC sağlamlaştırma çalışmasının 3. iterasyonu (1=8.3 arıza kapsamı, 2=8.4 skor
> standardizasyonu; sıradaki 8.6 = ertelenen D/E + eskalasyon update-in-place). Amaç teknik
> sağlamlık (yaşam döngüsü kenar durumları), GÖRSEL değil.
> **Domain temeli:** Karar, üç bağımsız kaynağın (Claude web-araştırması + 2 harici AI brief)
> örtüştüğü olgun alerting pratiğine dayanır (Prometheus Alertmanager, PagerDuty, Nagios/Zabbix).
> Kaynaklar § 12.

## 1. Amaç ve Kapsam

Faz 7 (Alert Manager) üç **bilinen sınır** bıraktı (spec § 9): (1) teknisyen *aktif* bir arızayı
manuel `resolved` ederse detector'ın in-memory durumu bunu bilmez → gerçek arıza sessiz kalır;
(2) detector restart'ta `active` dict boşalır → açık uyarılar orphan kalır; (3) eskalasyonda cihaz
başına >1 açık uyarı (kabul edilen dürüst davranış).

Bu sınırların **kök nedeni:** detector yaşam döngüsü durumunu **in-memory `active: dict[device→
frozenset[rule]]`** ile tutuyor; DB ise uyarı statüsünün (active/acknowledged/resolved) hakikat
kaynağı. **İki yazıcı vardır** (detector + operatör); in-memory durum, başka bir tarafın
değiştirebildiği bir değerin özel cache'idir → detector kendi yapmadığı bir değişikliği gözlemleyemez.
Bu, dikkatli in-memory defter tutmayla çözülemez; **paylaşılan tek hakikat kaynağı zorunludur.**

Bu iterasyon mimariyi **DB-tek-hakikat + per-poll idempotent reconciliation** (level-triggered)
modeline taşır ve **manuel resolve'u kaldırır** (P2 — § 2). **Limit 1 ve 2 inşaat gereği çözülür;
limit 3 (eskalasyon) bilinçli korunur** (Iter 8.6'da update-in-place ele alınır).

## 2. Temel Kararlar (brainstorming + üçgenleme, 2026-06-18)

| Karar | Seçim | Gerekçe / reddedilen |
|---|---|---|
| Durum modeli | **DB tek hakikat + per-poll reconciliation** (level-triggered) | İki yazıcı → in-memory cache divergence'ın kökü. Kubernetes-controller / Prometheus deseni. Reddedilen: in-memory + dikkatli reconcile (hibrit) — divergence'ı yok etmez |
| In-memory `active` dict | **KALDIRILIR** | Durum her poll DB'den re-derive edilir; restart = normal yol |
| Fingerprint (uyarı kimliği) | **`device_id + rule_set`** (sıralı kümeden kanonik) | Prometheus/PagerDuty dedup-key deseni; timestamp/sayaç YOK |
| Manuel RESOLVE | **KALDIRILIR** (P2) | Gözlem-modu: teknisyen makineyi bu araçtan tamir edemez → "düzeldi" detector'ın bilgisi. ACK zaten "görünümden düşür"ü karşılar. Alertmanager da insanın firing alert'i resolve etmesine izin vermez (yalnız silence). Reddedilen P1 (resolve kalsın, yeniden-açılabilir): "resolve geri sekti" UX karmaşası + gereksiz |
| ACK | **KALIR** | Teknisyenin tek anlamlı fiili: "gördüm, ilgileniyorum" → active→acknowledged (açık kalır, muted) |
| Çözüm granülerliği | **Cihaz-seviyesi** (cihaz tamamen temiz → tüm açık uyarılar resolve) | Eskalasyon (limit 3) davranışını korur |
| Açma granülerliği | **Fingerprint-seviyesi** (bu rule_set'le açık uyarı yoksa → yeni) | İlk tespit + eskalasyon + (yeniden-açma) tek diff'le |
| Eskalasyon (limit 3) | **AYNEN korunur** | Faz 7 § 2.3 kabul; update-in-place → Iter 8.6 |

## 3. Mimari Değişiklik — In-Memory'den Reconciliation'a

**Çıkan:** `_detect_once`'tan **`active: dict[str, frozenset[str]]` parametresi düşer** (imza değişir);
`run()` (service.py ~188) `active = {}` kurulumunu + poll döngüsünde (~207) `active` geçirmeyi BIRAKIR.
**Giren:** her poll başında DB'den açık-uyarı fingerprint'lerini okuma + level-triggered diff. Detector durum
tutmaz → restart, normal poll yolundan kendiliğinden uzlaşır (limit 2 inşaat gereği).

**Tek hakikat kaynağı = `anomalies` tablosu.** Reconciliation idempotenttir (aynı poll iki kez koşsa
sonuç aynı): retry/overlap güvenli.

## 4. Veri Modeli — Migration 004

`anomalies` tablosuna **`rule_set TEXT`** kolonu (nullable; eski satırlar NULL).
- **İçerik:** uyarının fingerprint'i — katkıda bulunan kural adlarının **sıralı, virgülle birleştirilmiş**
  hali (örn. `"motor_current_high,vibration_elevated"`). Kanonik (sıralı) → küme eşitliği deterministik.
- **Yazım:** `insert_anomaly`'ye `rule_set: str` parametresi eklenir. `_detect_once` fingerprint'i zaten
  hesaplıyor (`frozenset(a.rule_name for a in device_anomalies)`) → `",".join(sorted(rule_set))` olarak geçer.
  **`Anomaly` write-kontratı DEĞİŞMEZ** (fused dataclass `rule_name="fused(N)"` taşımaya devam eder;
  rule_set ayrı kolon, repository parametresi).
- **Okuma:** parse `frozenset(s.split(",")) if s else frozenset()` — **NULL/boş güvenli** (legacy satır → boş
  frozenset; eşleşmez → en kötü bir kerelik 1 fazla uyarı, demo DB arşivlendiğinden pratikte yok).
- **İKİ-KAYNAK (kritik, migration 003 deseni):** `anomalies` tablosu hem SQL migration'da hem
  `src/storage/schema.py`'deki Core `Table` nesnesinde tanımlı. `rule_set` **HER İKİSİNE** eklenir:
  migration 004 `ALTER TABLE anomalies ADD COLUMN rule_set TEXT` + `schema.py` `anomalies` Table'a
  `Column("rule_set", Text)`. Aksi halde repository'nin Core sorguları (`insert_anomaly` yazımı /
  `fetch_open_fingerprints` okuması) `anomalies.c.rule_set` bulamaz → kırılır. (003 `status`/`acknowledged_at`/
  `resolved_at`'i ikisine birden eklemişti — aynı disiplin.)
- İndeks: yeni indeks GEREKMEZ (`idx_anomalies_status` `(status, created_at)` reconciliation `WHERE status IN
  (...)` filtresini kullanır — covering değil ama POC'ta birkaç açık uyarı için yeterli).

## 5. Reconciliation (per-poll, per-cihaz)

Poll başında **tek sorgu:** `fetch_open_fingerprints() -> dict[str, set[frozenset[str]]]`
(cihaz → açık [active|acknowledged] uyarıların rule_set'leri). Sonra her cihaz için (`list_devices()`
append-only telemetry'den DISTINCT okur → cihaz asla düşmez):

```
current = frozenset(firing rule adları)        # bu poll'da tetikleyen kümeler
open_fps = open_fingerprints.get(device, set())

if not current:                                # cihaz temiz
    if open_fps:                               # açık uyarısı varsa
        resolve_open_alerts(device, now)       # auto-resolve (hepsi: active+acknowledged)
    # açık yoksa → no-op
elif current in open_fps:                      # bu fingerprint zaten açık (ack dahil)
    pass                                       # DEBOUNCE — yeniden açma yok
else:                                          # firing ama bu fingerprint açık değil
    insert_anomaly(fuse(...), now, rule_set=",".join(sorted(current)))   # YENİ uyarı
```

**KORUNAN İSKELE (kritik — yukarıdaki pseudocode yalnız DEĞİŞEN iç dalı gösterir):** `current` kümesini
ÜRETEN mevcut makine **aynen korunur** — `detector_groups` çok-grup döngüsü (kural 120s + istatistik 3600s),
per-cihaz `window_cache` (service.py ~101-108), per-dedektör `try/except (KeyError, ValueError)` yutma
(~112-116), `fuse_anomalies`, ve `insert_anomaly`/`resolve_open_alerts` etrafındaki `OperationalError`
yakalama (~128-129/139-140). Yani `_detect_once`'ın `rule_set` hesabına (service.py ~118) kadar olan kısmı
korunur; YALNIZ `if not rule_set / debounce / yeni-satır` karar bloğu (in-memory `active`) yukarıdaki
DB-fingerprint diff'iyle değiştirilir.

**Davranış sonuçları:**
- **Debounce** = aynı fingerprint açık (active **veya** acknowledged) → no-op. Ack'lenmiş uyarı yeniden açılmaz.
- **Eskalasyon** = `current` farklı (yeni/farklı küme) → yeni satır; eski açık uyarılar **resolve EDİLMEZ**
  (cihaz tamamen temiz değil) → cihaz başına >1 açık uyarı (**limit 3 korunur**).
- **Auto-resolve** = cihaz tamamen temizlenince tüm açık uyarılar (active+acknowledged) resolve.
- **Restart** = ilk poll bu diff'i koşar; geçmiş açık uyarılar DB'den okunur → orphan yok, duplikat yok.
- **(Yeniden-açma)** = mimaride doğru (resolved "açık" sayılmaz → eşleşmez → yeni); P2'de manuel resolve
  olmadığından bu yol yalnız detector'ın kendi auto-resolve'undan sonra tekrar arıza için işler.

## 6. Repository API

**Yeni:**
- `insert_anomaly(anomaly, created_at, rule_set: str)` — `rule_set` parametresi eklenir (zorunlu; çağrı
  yerleri güncellenir — § 8 regresyon).
- `fetch_open_fingerprints() -> dict[str, set[frozenset[str]]]` — **Core `select` ile** (raw SQL değil,
  proje deseni): `select(anomalies.c.device_id, anomalies.c.rule_set).where(anomalies.c.status.in_(("active",
  "acknowledged")))`; her satırın `rule_set`'i parse edilip (`frozenset(s.split(",")) if s else frozenset()`)
  cihaz başına kümelenir.

**Korunan:** `acknowledge_alert` (active→acknowledged), `resolve_open_alerts(device, at)` (detector
auto-resolve; `status != 'resolved'` → active+acknowledged kapatır), `fetch_alerts(statuses, limit)`.

**Kaldırılan:** `resolve_alert(id, at)` (manuel tekil resolve — P2'de kullanılmıyor) + testi. NOT:
lifecycle geçiş matrisi (`can_transition`, ACKNOWLEDGED→RESOLVED dahil) DEĞİŞMEZ — geçiş artık yalnız
detector `resolve_open_alerts` üzerinden tetiklenir.

## 7. Dashboard (Streamlit-native, gözlem-modu)

- **Manuel resolve butonu KALDIRILIR** (`_render_alert_management`'tan resolve dalı + çağrısı).
- **ACK butonu KALIR.** Anlatı: *"teknisyen ack'ler; sistem arıza sensörlerce temizlenince auto-resolve
  eder — bir insan canlı gerçek arızayı sessizce kapatamaz."*
- Durum filtresi (Açık/Tümü/...) + `alerts_to_frame` + fragment yapısı **DEĞİŞMEZ** (resolved uyarılar
  yine "Tümü"de görünür). Gözlem modu korunur: dashboard yalnız `status` (ack) yazar.

## 8. Mevcut Davranışla Uyum (Regresyon Kapsamı)

- **Eskalasyon (limit 3) korunur** (§ 5): mevcut "küme değişince yeni satır, eski açık kalır" davranışı.
- **`insert_anomaly`'ye zorunlu `rule_set` + `_detect_once`'tan `active` düşmesi TÜM çağrı yerlerini kırar**
  (Iter 8.4 `trip_*` dersi). **Atomik iniş seti:** migration 004 SQL + **`schema.py` Table `Column`** (C1) +
  `insert_anomaly` imza + `fetch_open_fingerprints` + `_detect_once` yeniden yazımı + `run()` (active kaldır) +
  dashboard resolve butonu + `resolve_alert` silme + AŞAĞIDAKİ test çağrı yerleri.
- **Kırılan mevcut test çağrı yerleri (~20+, plan bütçelemeli):**
  - `_detect_once(..., active, ...)` (active pozisyonel arg): `tests/unit/detectors/test_service_detect_once.py`
    (~11 çağrı), `tests/integration/test_statistical_detector.py` (2), `tests/integration/test_detector_config_driven.py` (1).
  - `insert_anomaly(anomaly, created_at)` (rule_set'siz): `test_service_detect_once.py` helper, `tests/integration/
    test_detector_persistence.py` (2), `tests/unit/test_storage_anomaly_repository.py` (2), `tests/unit/
    test_storage_alert_repository.py` (~7).
  - `resolve_alert` kaldırma: `tests/unit/test_storage_alert_repository.py` (~3 çağrı, ör. `test_acknowledge_then_resolve_alert`).
- **Auto-resolve davranışı korunur** (cihaz temiz → açık uyarılar resolve); yalnız tetikleyici in-memory
  `active` yerine DB fingerprint okuması.
- **`Detector` ABC + `Anomaly` + `fuse_anomalies` DEĞİŞMEZ.** Gözlem modu korunur (detector kendi çıktı
  tablosu `anomalies`'i okur + yazar; telemetri yazmaz, cihaz kontrol etmez).
- **Skor [0,1], dedektör kuralları (Iter 8.4) DEĞİŞMEZ.**

## 9. Kapsam Dışı / Ertelenen

- **Eskalasyon update-in-place** (severity'yi mutable + tek satır güncelle): Iter 8.6 (limit 3'ü çözer).
- **Debounce eşleşmesinde value/score güncelleme** (8.4'teki "skor ilk-tespite donuyor" sınırı): Iter 8.6
  (update-in-place ile birlikte tutarlı).
- **Hysteresis/deadband + flap-detection** (kural transient-stop → resolve/re-open flapping; MEVCUT
  davranış, 8.5 kötüleştirmez): paging katmanımız yok; gerekirse sonra. 120s pencere pratikte maskeliyor.
- **Notification-state ayrımı / repeat_interval:** paging/bildirim katmanı yok (dashboard salt-görüntü) → N/A.
- **Unique partial index** (`(device_id, rule_set) WHERE open`): tek-yazıcı detector → reconciliation zaten
  duplikat üretmez; yapısal güvence YAGNI (çok-replica fazında değerlendirilir).
- **Time-bounded silence:** ACK yeterli; ayrı snooze özelliği YAGNI.

## 10. Test Stratejisi

| Katman | Test |
|---|---|
| Reconciliation (saf/birim) | diff dalları: clean+açık→resolve; clean+açık-yok→no-op; firing+eşleşen-fingerprint→debounce; firing+eşleşen-yok→yeni; eskalasyon→2 açık (eski resolve edilmez); ack'li fingerprint firing→debounce (yeniden açma yok) |
| Restart senaryosu | "soğuk" detector (in-memory durum yok) + DB'de açık uyarılar → ilk poll: süregelen arıza debounce, temizlenen auto-resolve (orphan yok, duplikat yok) |
| Repository (integration) | `fetch_open_fingerprints` (active+acknowledged döner, resolved dönmez, rule_set parse; NULL→boş); `insert_anomaly` rule_set yazımı; `resolve_open_alerts` korunur |
| Dashboard | ack butonu var; **resolve butonu YOK** (+ `resolve_alert` kaldırıldı, çağrı yok) |
| Kapanış | **tam suite + mypy strict + ruff + canlı demo smoke** |

**Canlı demo smoke kabul:** arıza→uyarı `active`; dashboard ack→`acknowledged` (açık kalır); arıza
temizlenince auto-resolve (active+acknowledged→resolved); **detector ortada restart edilince orphan yok**
(süregelen arıza debounce, temizlenen resolve); resolve butonu yok; gözlem modu korunur.

## 11. Kabul Kriterleri

1. In-memory `active` dict kaldırıldı; `_detect_once` DB-tek-hakikat reconciliation ile çalışır.
2. Detector restart'ta orphan uyarı kalmaz (limit 2 çözüldü); restart testi + canlı smoke kanıtlar.
3. Manuel resolve kaldırıldı (P2); dashboard'da yalnız ACK; `resolve_alert` repository'den silindi.
   Manuel-resolve divergence'ı (limit 1) inşaat gereği yok (insan firing arızayı resolve edemez).
4. Eskalasyon davranışı (limit 3) korunur (küme değişince yeni satır, eski açık kalır).
5. `rule_set` fingerprint kolonu (migration 004) yazılır + reconciliation'da okunur; NULL güvenli.
6. Tüm testler yeşil + mypy strict + ruff + canlı demo smoke (§ 10).
7. `Detector` ABC + `Anomaly` + `fuse_anomalies` + Iter 8.4 skorları + gözlem modu DEĞİŞMEDİ.

## 12. Spec'e Karşı Disiplin

Uygulama bu spec'ten saparsa önce spec güncellenir. Mimari kararlar (§ 2 — DB-tek-hakikat, P2 manuel-resolve
kaldırma, fingerprint=device+rule_set) kullanıcı onayı olmadan değişmez.

## 13. Kaynaklar (domain temeli — üç bağımsız kaynak örtüşmesi)

- **Prometheus Alertmanager** — level-triggered evaluation, fingerprint dedup, sürekli firing-set re-assert,
  `resolve_timeout` (kaynağın durmasıyla auto-expire); insan firing alert'i resolve edemez (yalnız silence).
- **PagerDuty / Nagios** — ACK (eskalasyon/bildirim durdur, koşul aktif) vs RESOLVE (terminal); resolved
  occurrence tekrarlarsa yeni occurrence açılır; Nagios recovery'de ack'i temizler.
- **Kubernetes controller reconcile** — level-triggered, idempotent, ground-truth'tan re-derive.
- **Centreon/Nagios flap detection + ISA-18.2 deadband** — hysteresis/dwell (kapsam dışı, Iter 8.6+).
- 2 harici AI brief (kullanıcı, 2026-06-18) — "iki yazıcı → DB tek hakikat zorunlu" + unique-partial-index +
  fingerprint kuralları (deterministik, sıralı, timestamp'siz) + escalation update-in-place (Iter 8.6).

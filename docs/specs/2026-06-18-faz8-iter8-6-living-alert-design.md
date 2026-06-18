# Faz 8 Iter 8.6 — "Yaşayan Uyarı" (In-Place Yaşam Döngüsü + Severity Banttan) Tasarım Dokümanı

> **Tek hakem:** Bu doküman Iter 8.6'nın tasarım kararlarını bağlar. Brainstorming 2026-06-18.
> **Bağlam:** POC sağlamlaştırma çalışmasının 4. iterasyonu (1=8.3 arıza kapsamı, 2=8.4 skor
> standardizasyonu, 3=8.5 reconciliation + P2; bu=8.6 eskalasyon update-in-place + skor refresh +
> severity-banttan). Amaç POC inandırıcılığı + operasyonel dürüstlük; ham görsel iş değil ama demo'da
> doğrudan görünür ("yaşayan uyarı").
> **Domain temeli:** Karar olgun alarm-yönetimi pratiğiyle örtüşür (Prometheus Alertmanager dedup +
> inhibition, PagerDuty dedup_key incident-update, ISO 20816 zone eşikleri, ISA-18.2 önceliklendirme).
> Kaynaklar § 13. Kullanıcı ayrıca harici AI üçgenlemesi yapacak (8.4/8.5 deseni).

## 1. Amaç ve Kapsam

Iter 8.4 ve 8.5 iki **ertelenen sınır** bıraktı:
- **8.4 (skor donması):** Bir cihazın açık uyarısı sürerken `_detect_once` debounce dalı **no-op**'tur →
  uyarının `score`/`value`'su **ilk tespit anına donar** (örn. cihaz 005 sıcaklığı tırmanmaya devam
  etse de skor 0.03'te kalır). Severity de config'ten statik (skordan bağımsız).
- **8.5 (eskalasyon = ayrı satır):** Kural-seti değişince (eskalasyon) **yeni satır** açılır, eski açık
  kalır → bir cihazda birden çok açık uyarı (Faz 7 "limit 3", dürüst ama gürültülü).

Bu iterasyon her ikisini **tek mekanizmayla** çözer: **cihaz-seviyesi tek "olay" (incident) kimliği +
in-place UPDATE**. Buna **severity'nin band-pozisyon skorundan türetilmesi** (8.4'ten ertelenen D
parçası) eklenir; böylece uyarı, arıza kötüleştikçe **hem skoru hem severity'si** yükselen, düzelince
resolve olan tek bir "yaşayan" satır olur.

**Kapsama giren (8.6):**
1. **Eskalasyon update-in-place** — cihaz başına >1 açık uyarı sorununu bitirir (kimlik cihaz seviyesi).
2. **Debounce'ta skor/değer/severity refresh** — 8.4 donma sınırını bitirir.
3. **Severity'yi banttan türetme** — global iki eşik (config-driven, ISO zone-aligned); füzyon sıralaması
   buna göre çalışır.
4. **Acknowledge sonrası re-activate** — severity bir üst banda geçince uyarı yeniden "active".

**Kapsam DIŞI (Iter 8.7'ye ertelendi):**
- **(3) Hysteresis / deadband** — transient-stop flapping (kural-seviyesi, ayrı mekanizma).
- **(5) Sensör-sağlığını ayrı veri-kalitesi/validity ekseni** — gating + dashboard (mimari, en büyük parça).

Gerekçe (kullanıcı + Kuzey Yıldızı): (1)+(2)+(4) tek mekanizma etrafında sıkı-bağlı ve demo-görünür;
(3)/(5) bağımsız ve daha geniş → ayrı iterasyon, kontrollü kalır.

## 2. Temel Kararlar (brainstorming, 2026-06-18)

| Karar | Seçim | Gerekçe / reddedilen |
|---|---|---|
| Uyarı kimliği | **Cihaz-seviyesi tek incident** (cihaz başına ≤1 açık uyarı) | (1)+(2) tek "in-place UPDATE" mekanizmasında birleşir; "limit 3" yapısal biter. Alertmanager/PagerDuty dedup-key deseniyle uyumlu. Reddedilen: fingerprint-kimliği (8.5) — eskalasyonda ayrı satır → gürültü |
| Firing + açık uyarı var | **O satırı UPDATE et** (score/value/severity/rule_set/window_end/description) | Hem skor refresh (2) hem eskalasyon in-place (1). created_at = olay başlangıcı SABİT |
| Firing + açık uyarı yok | **Yeni aç** (ilk tespit) | Değişmedi |
| Cihaz temiz | **resolve_open_alerts** (cihaz seviyesi) | 8.5'ten değişmedi |
| Severity | **Band skorundan türet** (global high/critical eşiği) | Skor zaten [0,1] ISO-zone normalize (8.4). Statik config severity → band-pozisyona uyumsuzdu. Reddedilen: severity'yi her dedektörde ayrı config'te bırakmak |
| Sensör-sağlığı severity | **Banttan türetilmez; config severity korunur** | `sensor_out_of_range`/`sensor_frozen` skoru 1.0 ikili validity bayrağı, band konumu DEĞİL → türetme anlamsız. Ayrı veri-kalitesi ekseni zaten 8.7 |
| ACK + eskalasyon | **Severity bir üst banda geçince re-activate** (acknowledged_at=NULL); aynı band içi skor artışı sessiz | Sistemin vaadi "patlamadan yakala" — ack'lenmiş uyarı sessizce kritikleşmemeli. Rank karşılaştırması küçük + kesin (gürültü yok). Reddedilen: tamamen sessiz (operasyonel güvenlik açığı) |
| Migration | **YOK** | Mevcut kolonlar UPDATE edilir; yeni alan gerekmez (8.4 gibi migrationsız) |
| `Anomaly` / `fuse_anomalies` / `Detector` ABC / gözlem modu | **DEĞİŞMEZ** | Girdi kontratı korunur (8.4/8.5 deseni) |

## 3. Model — Cihaz-Seviyesi "Olay" (Incident) Kimliği

8.5'te kimlik = `device_id + rule_set` (fingerprint); 8.6'da kimlik = **`device_id`**. Bir cihazın
**açık (active|acknowledged) en fazla TEK** uyarısı olur. Bu uyarı arıza süresince *yaşar*:

- `created_at` = olayın **ilk tespit** anı (sabit, audit).
- `window_end`, `value`, `score`, `severity`, `rule_set`, `description` = **en güncel** poll'a göre güncellenir.
- Arıza bitince (cihaz temiz) → `resolved`.

**Önemli kayıp/kazanç analizi:** Cihaz-seviyesi kimlik, *aynı anda iki bağımsız arızayı ayrı uyarı olarak*
göstermez (ikisi tek satırda füzyonlanır). Bu, mevcut `fuse_anomalies` davranışıyla zaten tutarlı (poll
başına cihaz başına tek fused satır) → 8.6 yeni bir kayıp getirmez, sadece eskalasyonu da aynı satıra
toplar. Çok-arıza ayrıştırma POC kapsamı dışı (gerçek-donanım / Faz 9+).

## 4. Reconciliation Algoritması (`_detect_once` reworku)

Mevcut üç dal → güncellenmiş üç dal (kimlik cihaz seviyesi):

```
open_alerts = repository.fetch_open_alerts()   # dict[device_id, list[Alert]]  (active|acknowledged)
for device_id in repository.list_devices():
    device_anomalies = <kural + istatistik grupları, mevcut window_cache yolu>
    device_anomalies = [apply_band_severity(a, cutoffs) for a in device_anomalies]   # § 6
    rule_set = frozenset(a.rule_name for a in device_anomalies)
    open_list = open_alerts.get(device_id, [])

    if not rule_set:                                  # (A) cihaz temiz
        if open_list:
            resolve_open_alerts(device_id, created_at)
        continue

    fused = fuse_anomalies(device_anomalies)          # severity'ler türetilmiş hâlde gelir
    if not open_list:                                 # (B) firing + açık yok → ilk tespit
        insert_anomaly(fused, created_at, ",".join(sorted(rule_set)))
        continue

    # (C) firing + açık var → in-place UPDATE (skor refresh + eskalasyon birleşik)
    primary = max(open_list, key=lambda a: a.created_at)        # en yeni = birincil
    # legacy çoklu-açık (8.5 öncesi satırlar): fazlalıkları kapat → kendi-kendine yakınsama
    for extra in open_list:
        if extra.id != primary.id:
            resolve_alert_by_id(extra.id, created_at)
    # re-activate kararı (§ 7)
    new_status, new_ack_at = _reconcile_status(primary, fused.severity)
    update_alert(
        primary.id,
        severity=fused.severity, score=fused.score, value=fused.value,
        window_end=fused.window_end, rule_set=",".join(sorted(rule_set)),
        description=fused.description, status=new_status, acknowledged_at=new_ack_at,
    )
```

- **Idempotent / level-triggered korunur** (8.5): durum her poll DB'den okunur, in-memory yok. Restart =
  normal yol. Aynı poll iki kez koşsa sonuç aynı (UPDATE deterministik).
- **`fetch_open_fingerprints` → `fetch_open_alerts`** ile değiştirilir (id+status+severity+created_at
  taşımalı; karar artık fingerprint eşitliğine değil "açık uyarı var mı"ya dayanır). 8.5'in fingerprint
  okuma yolu kalkar.
- **`window_cache` / grup yapısı / error-swallow / `OperationalError` swallow / pragma iskelesi KORUNUR.**

## 5. (2) Skor / Değer Refresh

Dal (C) her poll'da `update_alert` çağırır → `score`/`value`/`window_end`/`description` daima güncel.
8.4 "skor ilk tespitte donuyor" sınırı biter. UPDATE hacmi: firing-cihaz başına poll başına 1 UPDATE
(5s) → ihmal edilebilir. **Log gürültüsü:** yalnız (i) ilk tespit, (ii) severity değişimi, (iii) rule_set
değişimi loglanır; sade skor tırmanışı log üretmez (INFO sel önleme).

## 6. (4) Severity Band'dan Türetme

**Yeni saf fonksiyon** `src/detectors/scoring.py` (band_position_score'un yanı):

```python
def severity_from_band(score: float, high_cutoff: float, critical_cutoff: float) -> str:
    """Band skorunu (0..1) severity'ye eşler. 0 = alarm bölgesine yeni girdi (en az warning),
    1 = kritik (trip). Eşikler ISO 20816 zone mantığı + sim kalibrasyonu."""
    if not (0.0 < high_cutoff < critical_cutoff < 1.0):
        raise ValueError(...)
    if score >= critical_cutoff:
        return "critical"
    if score >= high_cutoff:
        return "high"
    return "warning"
```

**Eşikler config-driven** (hand-picked sabit YASAK — proje kuralı). `detectors.yaml`'a **global** blok:

```yaml
severity_bands:
  high_cutoff: 0.40      # başlangıç; canlı smoke ile kalibre
  critical_cutoff: 0.75
```

- `DetectorConfig`'e `severity_bands: SeverityBands` (default'lu → geriye-uyumlu; example/demo YAML
  güncellenir). `load_detector_config` parse eder.
- **Uygulama yeri:** `_detect_once` içinde, fusion'dan ÖNCE, band-skorlu anomalilere `apply_band_severity`
  ile severity (yeniden) atanır. `Anomaly` frozen → `dataclasses.replace(a, severity=...)` ile **yeni**
  nesne döner (mutasyon yok). Sensör-sağlığı kuralları (`sensor_out_of_range`, `sensor_frozen`) bu setten
  **muaf** (kendi config severity'lerini korur). Muafiyet `VALIDITY_RULES: frozenset` üyeliğiyle belirlenir
  (rule_name bazlı; string-eşleşme tek yerde, dokümante).

  > **Tasarım notu (düşük-risk yol):** Severity'yi `_detect_once`'ta merkezî atamak, eşikleri tek yerden
  > dağıtır ve **7 dedektörün `__init__`'ini, generic `build_detectors(severity=..., **params)` çağrısını
  > ve tüm config YAML'larının yapısını kırmaktan kaçınır** (8.4 "zorunlu param tüm çağrı yerlerini kırar"
  > dersinin maliyetini sınırlar — kullanıcının açıkça seçtiği düşük-risk tercih). Band-rule config'lerindeki
  > `severity` alanı **bırakılır ama provisional**'dır: dedektör onu Anomaly'e koyar, `apply_band_severity`
  > band'dan türetilenle **override eder**. Config severity yalnız sensör-sağlığı kuralları için
  > **otoritatif**tir (muaf). Bu kasıtlı asimetri kod yorumunda + bu spec'te dokümante edilir (ölü-config
  > kokusu değil, bilinçli karar). YAML'lardan severity silinmez → atomik kırılma yüzeyi minimum.

- **Füzyon etkileşimi:** `fuse_anomalies` değişmez — severity'ler ona türetilmiş gelir, `_rank`
  (severity, score) doğru çalışır, temsilci (`top`) doğru seçilir. Tek-anomali yolu da türetilmiş
  severity taşır (atama fusion'dan önce).
- **İstatistik dedektörler:** band skoru büyük sapmada 1.0'a satüre olur (8.4) → çoğu zaman critical'e
  türer (dürüst).

## 7. Acknowledge Sonrası Re-activate

`_reconcile_status(primary: Alert, new_severity: str) -> tuple[str, str | None]` (saf helper, test edilir):

```
rank = {"critical":3,"high":2,"warning":1,"info":0}   # fusion._SEVERITY_RANK ile aynı (tek kaynak)
if primary.status == ACKNOWLEDGED and rank[new_severity] > rank[primary.severity]:
    return (ACTIVE, None)        # band-yukarı geçiş → yeniden dikkat çek, ack temizle
return (primary.status, primary.acknowledged_at)   # değişmez (active kalır / ack korunur)
```

- Yalnız **band-yukarı geçiş** (rank artışı) re-activate eder; aynı band içi skor artışı sessiz → gürültü yok.
- `active` bir uyarı zaten `active` kalır. `acknowledged` + aynı/düşük severity → `acknowledged` kalır.
- `_SEVERITY_RANK` tek kaynak: `fusion.py`'den import (duplikasyon yok).

## 8. Repository Değişiklikleri

| Metot | Durum | İmza / davranış |
|---|---|---|
| `fetch_open_fingerprints` | **KALDIRILIR** | Yerine fetch_open_alerts; 8.5 testleri atomik güncellenir |
| `fetch_open_alerts` | **YENİ** | `() -> dict[str, list[Alert]]`; `status IN (active,acknowledged)`, device_id'ye grupla, `_row_to_alert` DRY |
| `update_alert` | **YENİ** | `(alert_id, *, severity, score, value, window_end, rule_set, description, status, acknowledged_at) -> bool`; `anomalies.update().where(id==alert_id)`; rowcount>0 |
| `resolve_alert_by_id` | **YENİ** | `(alert_id, resolved_at) -> bool`; legacy çoklu-açık yakınsaması için tek satır resolve (`WHERE id AND status!=resolved`) |
| `insert_anomaly` | DEĞİŞMEZ | (rule_set parametresi 8.5'te eklendi) |
| `resolve_open_alerts` / `acknowledge_alert` | DEĞİŞMEZ | Cihaz temiz auto-resolve + ack |

**Migration YOK** — tüm UPDATE'ler mevcut kolonlara. `Alert` modeli DEĞİŞMEZ (rule_set okumaya gerek yok;
karar device-level). `created_at` UPDATE'lerde **dokunulmaz** (olay başlangıcı).

## 9. Dashboard Etkisi

Yapısal değişiklik **yok**. "Yaşayan uyarı" kendiliğinden daha iyi görünür:
- Cihaz başına tek açık satır → uyarı listesi daha temiz (eskalasyon yığını yok).
- Skor/severity her poll güncellendiği için tablo + grafik overlay zaten canlı yansıtır (5s/2s fragment).
- Severity emoji/satır-stili (8.2 `alerts_to_frame`) artık banttan türetilmiş gerçek severity'yi gösterir.

Yeni panel/kolon eklenmez (sensör-sağlığı ayrı eksen 8.7). Gözlem modu korunur.

## 10. Test Stratejisi (TDD; her task tam suite + mypy + ruff)

**Saf birim:**
- `severity_from_band`: sınır değerleri (0→warning, high_cutoff→high, critical_cutoff→critical, 1→critical),
  geçersiz eşik → ValueError.
- `_reconcile_status`: ack+rank-artışı→(active,None); ack+aynı/düşük→değişmez; active→değişmez.
- `apply_band_severity`: band-rule severity türetilir; validity-rule muaf (config severity korunur).

**Reconciliation (`_detect_once`, clock DI):**
- (B) ilk tespit → 1 insert.
- (C) skor refresh: aynı arıza sürerken skor artışı → UPDATE (yeni skor/value), satır sayısı SABİT (donma yok).
- (C) eskalasyon in-place: rule_set genişler → **yeni satır YOK**, aynı satır güncellenir (severity yükselir).
- (A) auto-resolve korunur (8.5 regresyon).
- legacy çoklu-açık → fazlalıklar resolve, biri güncellenir (yakınsama).
- ack→critical re-activate; ack→aynı band sessiz.

**Repository:** `fetch_open_alerts` (gruplandırma, sıralama), `update_alert` (rowcount), `resolve_alert_by_id`.

**İmza/regresyon:** `fuse_anomalies` değişmez (mevcut testler yeşil); 8.5'in `fetch_open_fingerprints`
testleri `fetch_open_alerts`'e dönüştürülür (atomik).

**Canlı 6-cihaz demo smoke (closure şartı — proje dersi):**
- 001 temiz → 0 FP.
- 005 (sıcaklık aşımı) → skor zamanla **tırmanır** (donma yok), severity warning→high→critical geçişi gözlenir.
- 002 (mekanik aşınma, eskalasyon) → **tek satır**, rule_set genişledikçe in-place büyür (yığın yok).
- Bir uyarı ack'lenip arıza kritikleşince → **re-activate** gözlenir.
- Arıza bitince → resolve. Detector restart → orphan/duplikat yok (8.5 korunur).
- Severity eşikleri (high/critical_cutoff) **gerçek sim çıktısıyla ölçülerek** kalibre edilir (8.4 dersi).

## 11. Değişmeyen Kontratlar

`Anomaly` (write), `fuse_anomalies`, `Detector` ABC, `band_position_score`, gözlem modu (yalnız telemetry
oku / anomalies yaz), skor [0,1] aralığı, migration şeması. ACK yaşam döngüsü (`can_transition`,
`acknowledge_alert`, `resolve_open_alerts`) korunur.

## 12. Yürütme Notu (ortam gerçeği)

Bu ortamda subagent'lar Bash/Write izinsiz (yalnız Read) → **controller inline implement + salt-okunur
reviewer subagent kalite kapısı** (8.4/8.5 hibrit deseni). Her task: TDD → tam suite
(`.venv/bin/python -m pytest`) + `mypy` + `ruff` (homebrew PATH) → reviewer. Closure'da canlı smoke.

## 13. Kaynaklar

- Prometheus Alertmanager — dedup (label fingerprint), inhibition (critical alt-severity'yi bastırır),
  repeat_interval (süregelen yeniden bildirim): https://prometheus.io/docs/alerting/latest/alertmanager/
- ISO 20816-3 — alarm=B/C zone sınırı, trip=C/D sınırı (band warn→trip eşlemesinin temeli):
  https://vibromera.eu/glossary/iso-20816-3/
- ISA-18.2 — alarm önceliklendirme / sınıflandırma: https://www.isa.org/products/ansi-isa-18-2-2016-management-of-alarm-systems-for
- PagerDuty dedup_key — mevcut incident'ı güncelleme (yeni açmama) konvansiyonu (genel pratik).
- Harici AI üçgenlemesi: kullanıcı § 1 promptuyla bağımsız doğrulama yapacak (8.4/8.5 deseni).

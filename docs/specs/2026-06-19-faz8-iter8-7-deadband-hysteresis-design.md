# Faz 8 Iter 8.7 — Deadband Hysteresis Tasarım Dokümanı

> **Tek hakem:** Bu doküman Iter 8.7'nin tasarım kararlarını bağlar. Brainstorming 2026-06-19.
> **Bağlam:** POC sağlamlaştırmanın 5. iterasyonu. Iter 8.6'dan ertelenen iki parçadan **(3) hysteresis**
> alındı; **(5) sensör-sağlığı ayrı veri-kalitesi ekseni → Iter 8.8'e** bırakıldı (mimari, daha büyük).
> **Domain temeli:** Deadband/hysteresis olgun alarm-yönetimi pratiğidir (ISA-18.2 "alarm chattering"
> önleme, Prometheus `for:` / Alertmanager `group_interval`/`repeat_interval` flapping bastırma).

## 1. Amaç ve Kapsam

**Sorun (flapping):** `_detect_once` cihaz "firing değil" olunca açık uyarıyı **hemen** resolve eder
(`resolve_open_alerts`). Değer tespit eşiği civarında salınırsa: poll N firing→açık, poll N+1 değil→resolve,
poll N+2 firing→yeni satır … = resolve↔reopen churn (8.1'de gözlenen "kozmetik flicker"). 8.6 kural-seti
dalgalanmasını (in-place update) yumuşattı ama **resolve↔reopen sınırı** hâlâ flap edebilir.

**Çözüm:** **Deadband** — cihaz firing değilse bile, arıza **N ardışık temiz poll** boyunca yok olmadan
uyarıyı resolve etme. Arada tek poll firing olursa sayaç sıfırlanır → salınan arıza **tek açık uyarı**
olarak kalır. Gerçek düzelmede ~N-poll (varsayılan 3 × 5s = 15s) küçük, kabul edilebilir gecikme.

**Kapsama giren:** Deadband hysteresis (resolve tarafı), config-driven N, DB-backed sayaç.
**Kapsam DIŞI (Iter 8.8):** (5) sensör-sağlığı ayrı veri-kalitesi/validity ekseni (gating + dashboard).
Ek küçük cleanup: `dashboard/fleet.py` dup `_SEVERITY_RANK` → `fusion.SEVERITY_RANK` (8.8'e).

> **Dürüst not (YAGNI, brainstorming self-review):** Kurallar 120s pencere + min_samples üzerinden
> çalıştığı için pencereleme flapping'i büyük ölçüde halihazırda yumuşatıyor; 8.6 in-place update de
> kural-seti churn'ünü topladı (8.6 canlı smoke'ta flapping gözlenmedi). Deadband, gözle görülür bir
> sorunu değil **sınırda yavaş-geçiş** kenar durumunu kapatan ucuz bir sigortadır → düşük risk, düşük
> marjinal fayda, sağlamlık katkısı. Bilinçli kabul.

## 2. Temel Kararlar (brainstorming, 2026-06-19)

| Karar | Seçim | Gerekçe / reddedilen |
|---|---|---|
| Mekanizma | **Deadband (N-ardışık-temiz-poll)** | Tek global knob; kural başına yeniden kalibrasyon YOK. Reddedilen: çift-eşik Schmitt trigger (per-rule clear eşiği → 5 kural × sim kalibrasyonu + state-bağımlı değerlendirme, daha invaziv) |
| Sayaç depolama | **DB-backed (`anomalies.clean_streak`, migration 005)** | 8.5/8.6 "DB tek hakikat + stateless detector + level-triggered" korunur; restart-safe. Reddedilen: in-memory dict (tek-yazıcı/benign ama _detect_once'a mutable-state param geri ekler → temiz mimariyi erozyona uğratır); zaman-tabanlı window_end-proxy (veri-saati ile firing-saatini karıştırır, test kırılgan) |
| Sayaç sıfırlama | **Firing poll'da `clean_streak=0`** (update_alert içinde) | Salınan arıza her firing'de sıfırlanır → tek açık uyarı (anti-flap) |
| Resolve granülerliği | **Cihaz-seviyesi** (8.6'dan, `resolve_open_alerts`) | N'e ulaşınca cihazın tüm açık uyarıları kapanır |
| N (deadband) | **Config-driven `deadband_clean_polls: int = 3`** | Hand-picked sabit yok; canlı smoke ile kalibre |
| Açma tarafı deadband | **YOK** | Flapping kaynağı resolve↔reopen; deadband resolve'u tuttuğu için reopen oluşmaz → açma tarafı gereksiz (YAGNI) |
| `Anomaly`/`fuse_anomalies`/severity-banttan (8.6)/gözlem modu/ACK | **DEĞİŞMEZ** | Girdi kontratı korunur |

## 3. Veri Modeli — Migration 005

`anomalies` tablosuna **`clean_streak INTEGER NOT NULL DEFAULT 0`** kolonu.
- **İçerik:** açık bir uyarının ardışık "temiz" (firing-olmayan) poll sayısı. Firing → 0; clean → +1.
- **schema.py** Core Table'a + **`migrations/005_clean_streak.sql`**'e İKİSİNE (003/004 deseni; tek-statement).
- `insert_anomaly` DEĞİŞMEZ — DB DEFAULT 0 uygular (status deseninin aynısı, Faz 7).
- **`Alert` modeli + `_row_to_alert`:** `+clean_streak: int` (reconciliation sayacı okumalı). `Alert` okuma
  modeli; alan eklemek güvenli (Anomaly write-kontratı ayrı, değişmez).
- schema_version testleri `[1,2,3,4,5]` / count 5 olur (002 dersi: migration ekleyince güncelle).

## 4. Reconciliation Değişikliği (`_detect_once` clean+open dalı)

8.6 dört-kadran reconciliation'ı korunur; yalnız **clean+open** dalı deadband kazanır:

```
# (A) cihaz temiz (rule_set boş)
if not rule_set:
    if open_list:
        primary = max(open_list, key=lambda a: (a.created_at, a.id))
        new_streak = primary.clean_streak + 1
        if new_streak >= deadband_clean_polls:
            resolve_open_alerts(device_id, created_at)        # yeterince sakin → kapat
        else:
            repository.set_clean_streak(primary.id, new_streak)  # açık tut, sayacı artır
    continue
```

- **(B) firing + açık yok → insert** (clean_streak DB default 0). DEĞİŞMEZ.
- **(C) firing + açık var → update_alert** — `clean_streak=0` sıfırlanır (firing). Diğer alanlar 8.6'daki gibi.
- **Idempotent/level-triggered korunur:** sayaç DB'de; aynı poll iki kez koşsa streak fazladan artmaz mı?
  Artar (her çağrı +1) — ama poll'lar gerçekte serileştirilir (tek detector süreci, `shutdown.wait`); test
  `_detect_once`'ı kasıtlı N kez çağırır. Bu kabul: deadband "yaklaşık N poll" semantiğidir, kesin sayı değil.
- `_detect_once(repository, detector_groups, now, severity_bands=..., deadband_clean_polls=3)` — yeni param
  (severity_bands gibi default'lu). `run()` `detector_config.deadband_clean_polls` geçirir.

## 5. Repository Değişiklikleri

| Metot | Durum | İmza / davranış |
|---|---|---|
| `update_alert` | **GENİŞLER** | `.values(...)`'a `clean_streak=0` eklenir (firing → reset). İmza DEĞİŞMEZ (param eklenmez; her firing reset). |
| `set_clean_streak` | **YENİ** | `(alert_id: int, streak: int) -> bool`; `anomalies.update().where(id==alert_id).values(clean_streak=streak)`; rowcount>0 |
| `fetch_open_alerts` | DEĞİŞMEZ imza | `_row_to_alert` artık `clean_streak` taşır (Alert alanı) |
| `resolve_open_alerts` / `reactivate_alert` / `resolve_alert_by_id` / `insert_anomaly` | DEĞİŞMEZ | — |

## 6. Config

`DetectorConfig.deadband_clean_polls: int = 3` (default'lu → geriye-uyumlu). `load_detector_config`
top-level `deadband_clean_polls` okur (yoksa 3). `config/detectors.yaml.example` + `.demo.yaml`'a eklenir:

```yaml
# Deadband hysteresis (Faz 8 Iter 8.7): arıza N ardışık temiz poll yoksa resolve (anti-flap).
deadband_clean_polls: 3
```

## 7. Dashboard Etkisi

Yapısal değişiklik **yok**. Deadband süresince uyarı "açık" görünür (son firing değerleriyle), N-poll sonra
kaybolur → kullanıcıya daha kararlı liste (yanıp sönme yok). `clean_streak` dashboard'da gösterilmez (iç sayaç).

## 8. Test Stratejisi (TDD; her task tam suite + mypy + ruff)

**Repository:**
- `set_clean_streak` (rowcount), `fetch_open_alerts` clean_streak taşır, `update_alert` clean_streak'i 0'a çeker.
- Migration 005: schema_version `[1,2,3,4,5]`; mevcut satırlar clean_streak=0 (DEFAULT).

**Reconciliation (`_detect_once`, clock DI, deterministik):**
- **Deadband holds:** firing → açık; clean poll #1, #2 (N=3) → hâlâ açık (`set_clean_streak` 1,2); clean poll #3 → resolve.
- **Anti-flap reset:** firing → clean → firing → clean → clean → clean: ortadaki firing sayacı sıfırlar → toplam 3 değil, son firing'den sonra 3 temiz gerekir; tek satır kalır (yeni satır/yeni incident YOK).
- **Mevcut `test_auto_resolves_on_clear` uyarlanır:** `deadband_clean_polls=1` ile çağrılır → tek temiz poll resolve (eski davranış; deadband=1 = anlık).
- Restart mid-streak: clean_streak DB'den okunur → kaldığı yerden devam (deterministik unit).
- 8.6 regresyon: re-activate / in-place update / severity-banttan / legacy-convergence testleri yeşil kalır
  (deadband yalnız clean+open dalını etkiler).

**Canlı 6-cihaz demo smoke (closure şartı):**
- Eşik civarı salınan bir arıza kurup (veya gerçek ramp sonu) **resolve↔reopen flapping olmadığını** doğrula.
- Gerçek düzelmede uyarının ~N-poll sonra (donma değil) resolve olduğunu gözle.
- 8.6 davranışları korunur (skor/severity refresh, re-activate, restart orphan-yok). N'i smoke'la kalibre et.

## 9. Değişmeyen Kontratlar

`Anomaly` (write), `fuse_anomalies`, `Detector` ABC, `band_position_score`, `severity_from_band` /
`apply_band_severity` (8.6), füzyon, gözlem modu (yalnız telemetry oku / anomalies yaz), skor [0,1],
ACK yaşam döngüsü (`can_transition`, `acknowledge_alert`, `resolve_open_alerts`, `reactivate_alert`).
8.6 cihaz-seviyesi in-place reconciliation iskeleti (dört kadran) korunur — yalnız clean+open dalı genişler.

## 10. Yürütme Notu

Bu ortamda subagent'lar Bash/Write izinsiz → **controller-inline implement + salt-okunur reviewer** hibridi
(8.4/8.5/8.6 deseni). Her task TDD → tam suite (`.venv/bin/python -m pytest`) + mypy + ruff (homebrew PATH).
Closure'da canlı smoke. Bağımsız plan-review + final whole-branch review.

## 11. Kaynaklar

- ISA-18.2 — alarm chattering / deadband ile bastırma: https://www.isa.org/products/ansi-isa-18-2-2016-management-of-alarm-systems-for
- Prometheus alerting `for:` (pending → firing gecikmesi) + Alertmanager `group_interval`/`repeat_interval`
  (flapping/gürültü bastırma deseni): https://prometheus.io/docs/alerting/latest/alertmanager/

# Faz 8 Iter 8.8 — Veri-Kalitesi Ekseni (Sensör-Sağlığı Sunum Ayrımı) Tasarım Dokümanı

> **Tek hakem:** Bu doküman Iter 8.8'in tasarım kararlarını bağlar. Brainstorming 2026-06-19.
> **Bağlam:** POC sağlamlaştırmanın SON iterasyonu (8.3 arıza kapsamı → 8.4 skor std → 8.5 reconciliation
> → 8.6 yaşayan uyarı → 8.7 deadband → **8.8 veri-kalitesi ekseni**). Bu bittiğinde POC sağlamlaştırma
> planı tamamlanır ve Faz 8 kapanabilir.
> **Domain temeli:** Gerçek durum-izleme sistemleri (ISO 13374) "veri kalitesi / sinyal geçerliliği"ni
> kestirimci arıza şiddetinden AYRI bir katman olarak ele alır — "makine arızalı" ile "sensöre güvenilmez"
> farklı kararlar gerektirir.

## 1. Amaç ve Kapsam

Sistem iki kavramsal olarak farklı şeyi tek "🚨 Uyarılar" akışında karıştırıyor:
- **Kestirimci arızalar** ("makine bozuluyor"): motor_temperature_high, motor_current_high, vibration_elevated,
  hydraulic_pressure_decline, motor_voltage_erratic + istatistiksel (three_sigma/iqr).
- **Sensör bütünlüğü** ("ölçüm aletine güvenilmez"): `sensor_out_of_range` (fiziksel-imkânsız değer),
  `sensor_frozen` (donuk sensör). Bunlar zaten `VALIDITY_RULES` olarak ayrık (skor 1.0 ikili validity,
  band'dan muaf, Iter 8.4/8.6) ama dashboard'da aynı tabloda kestirimci arızalarla karışık görünüyor.

**Çözüm:** Veri-kalitesini **ayrı bir eksen** olarak SUNUMDA ayır — dashboard'da iki ayrı panel
("Arıza Uyarıları" + "Veri Kalitesi / Sensör Sağlığı"). Teknisyen "makineyi mi tamir edeyim, sensörü mü
değiştireyim?" sorusunu net ayırır → POC olgunluk sinyali.

**Kapsama giren (8.8):**
1. Dashboard'da kestirimci vs veri-kalitesi iki ayrı panel.
2. Saf, test edilebilir sınıflandırma (`split_alerts_by_axis`).
3. `Alert.rule_set` okuma alanı (fused satırları doğru sınıflandırmak için).
4. `VALIDITY_RULES` tek-kaynak (saf leaf'e taşıma → detector + dashboard paylaşır).
5. Küçük cleanup: `dashboard/fleet.py` dup `_SEVERITY_RANK` → `fusion.SEVERITY_RANK`.

**Kapsam DIŞI (gerçek-donanım fazı):**
- **Gating** (sensör geçersizken o sensöre bağlı kestirimci dedektörleri askıya alma). Sentetik veride
  gözle görülür etkisi ~sıfır (`mast_position` hiçbir kestirimci kuralca okunmuyor; `sensor_frozen`
  simülatörde üretilmiyor → görünür kılmak yeni "donmuş sensör" senaryosu gerektirir). Geçersiz sensörün
  kestirimci okumayı gerçekten bozduğu gerçek-donanım fazına ait.
- **Reconciliation'ı iki eksene bölme** (cihaz başına ayrı kestirimci + veri-kalitesi incident'ı). Gereksiz
  mimari karmaşa; çakışma demoda yok (validity ve kestirimci arızalar ayrı cihazlarda).

## 2. Temel Kararlar (brainstorming, 2026-06-19)

| Karar | Seçim | Gerekçe / reddedilen |
|---|---|---|
| Ayrım katmanı | **Sunum tarafı (dashboard + saf transform)** | Tespit/reconciliation/füzyon/migration DEĞİŞMEZ → düşük risk. Reddedilen: reconciliation'ı iki eksene bölme (mimari, demoda gereksiz) |
| Gating | **ERTELE (gerçek-donanım)** | Sentetik veride görünmez + simülatör senaryosu gerektirir (YAGNI) |
| Sınıflandırma anahtarı | **`rule_set`'teki TÜM kurallar validity mi?** | Tek-kural satırı (sensor_out_of_range) net; fused satırı (çakışma) bileşimine göre. Reddedilen: yalnız `rule_name` (fused multi-validity'yi yanlış sınıflar) |
| Çakışan fault+bad-sensor (aynı cihaz) | **Kestirimci panele düşer (kabul, demoda yok)** | Füzyon tek satıra indiriyor; tam ayrım gating ile gerçek-donanımda. Dürüst sınır, dokümante |
| `VALIDITY_RULES` konumu | **Saf leaf'e taşı (`detectors/base.py`)** | Hem `service` hem dashboard `transform` (saf, streamlit/DB'siz) importlayabilsin; `transform`'a heavy `service` import etmeden. Tek kaynak |
| `Anomaly`/`fuse_anomalies`/`Detector` ABC/`_detect_once`/gözlem modu | **DEĞİŞMEZ** | Girdi kontratı korunur |

## 3. `VALIDITY_RULES` Tek-Kaynak Taşıma

Şu an `src/detectors/service.py`'de `VALIDITY_RULES: frozenset[str] = frozenset({"sensor_out_of_range",
"sensor_frozen"})`. **`src/detectors/base.py`'ye taşınır** (saf leaf — yalnız stdlib/abc/dataclasses/pandas;
`Anomaly`/`Detector` zaten orada). `service.py` `from detectors.base import VALIDITY_RULES` ile importlar
(davranış değişmez). Dashboard `transform.py` de buradan importlar (saflık korunur — base.py heavy değil).

## 4. `Alert.rule_set` Okuma Alanı

`Alert` (alerts/models.py) frozen dataclass'a **`rule_set: str | None = None`** (default'lu → mevcut
`Alert(...)` constructor'ları kırılmaz, `clean_streak` deseni). `_row_to_alert` → `rule_set=row.rule_set`
(kolon 8.5 migration 004'ten beri var). Migration YOK. `anomalies` tablosu/şema değişmez.

## 5. Saf Sınıflandırma (`transform.py`)

```python
def is_data_quality_alert(alert: Alert) -> bool:
    """Uyarı veri-kalitesi ekseninde mi (yalnız validity kurallarından mı oluşuyor)?

    rule_set'teki TÜM kurallar VALIDITY_RULES'taysa True (sensör bütünlüğü);
    en az bir kestirimci kural varsa False (arıza ekseni). rule_set boş/None → False (kestirimci varsay).
    """
    if not alert.rule_set:
        return False
    rules = {r for r in alert.rule_set.split(",") if r}
    return bool(rules) and rules <= VALIDITY_RULES


def split_alerts_by_axis(alerts: list[Alert]) -> tuple[list[Alert], list[Alert]]:
    """Uyarıları (kestirimci_arızalar, veri_kalitesi) olarak ikiye böler (sıra korunur)."""
    faults = [a for a in alerts if not is_data_quality_alert(a)]
    data_quality = [a for a in alerts if is_data_quality_alert(a)]
    return faults, data_quality
```

`alerts_to_frame` / `severity_row_style` / `latest_alert_per_device` DEĞİŞMEZ (iki panel de yeniden kullanır).

## 6. Dashboard İki Panel (`app.py` `_render_overview`)

Mevcut tek "🚨 Uyarılar" `st.dataframe` → `split_alerts_by_axis` ile ikiye:
- **"🚨 Arıza Uyarıları"** (faults) — mevcut görünüm (severity-stilli, göreli zaman).
- **"🔌 Veri Kalitesi / Sensör Sağlığı"** (data_quality) — aynı `alerts_to_frame` formatı, ayrı başlık.
- Her panel kendi boş-durumunu gösterir ("Açık arıza uyarısı yok" / "Tüm sensörler sağlıklı").
- Mevcut durum-filtresi (Açık/Tümü) + `latest_alert_per_device` özetleme + 5s fragment yapısı KORUNUR
  (split filtreleme/özetlemeden SONRA uygulanır). Sorgu bütçesi değişmez (tek `fetch_alerts`).
- Gözlem modu korunur (salt-görüntü).

## 7. Cleanup — `fleet.py` Severity Rank Tek-Kaynak

`src/dashboard/fleet.py` kendi `_SEVERITY_RANK = {"warning":1,"high":2,"critical":3}` kopyasını taşıyor
(8.6 spec §7 tek-kaynak intent'i, 8.6/8.7'de kapsam dışıydı). `from detectors.fusion import SEVERITY_RANK`
ile değiştirilir. NOT: `fusion.SEVERITY_RANK` `{"critical":3,"high":2,"warning":1,"info":0}` — fleet
kullanımı `.get(severity, 0)` olduğu için davranış aynı (info=0 ek anahtar zararsız). fleet testleri yeşil kalmalı.

## 8. Test Stratejisi (TDD; her task tam suite + mypy + ruff)

**Saf birim (`transform.py`):**
- `is_data_quality_alert`: sensor_out_of_range/sensor_frozen tek-kural → True; motor_current_high → False;
  fused "motor_current_high,sensor_out_of_range" (çakışma) → False; fused "sensor_frozen,sensor_out_of_range"
  → True; rule_set None/"" → False.
- `split_alerts_by_axis`: karışık liste → doğru iki bölüm, sıra korunur.

**Repository/model:** `Alert.rule_set` `_row_to_alert` ile dolar (fetch_alerts/fetch_open_alerts satırlarında).

**Cleanup:** `fleet.py` mevcut testleri (`test_dashboard_fleet.py`) `SEVERITY_RANK` importu sonrası yeşil kalır.

**Dashboard app.py:** ince presentation (unit YOK) — headless boot smoke + canlı smoke.

**Canlı 6-cihaz demo smoke (closure şartı):**
- device_006 (`sensor_out_of_range`, mast_position) → **"Veri Kalitesi" panelinde**.
- Kestirimci cihazlar (002/003/004/005) → **"Arıza Uyarıları" panelinde**.
- device_001 temiz → her iki panel de boş-durum.
- 8.6/8.7 korunur (yaşayan uyarı + deadband). Boş-DB/eksik-config graceful (çökme yok).

## 9. Değişmeyen Kontratlar

`Anomaly` (write), `fuse_anomalies`, `Detector` ABC, `_detect_once` reconciliation + deadband (8.7),
severity-banttan + re-activate + in-place (8.6), `band_position_score`, gözlem modu, skor [0,1], ACK yaşam
döngüsü, migration şeması (YENİ migration YOK). `VALIDITY_RULES` içeriği değişmez (yalnız konum taşınır).

## 10. Yürütme Notu

Bu ortamda subagent'lar Bash/Write izinsiz → **controller-inline implement + salt-okunur reviewer** hibridi
(8.4-8.7 deseni). Her task TDD → tam suite + mypy + ruff (homebrew PATH). Closure'da canlı smoke + bağımsız
plan-review + final whole-branch review.

## 11. Kaynaklar

- ISO 13374 — durum-izleme veri işleme katmanları (veri edinme → manipülasyon → durum tespiti); sinyal
  geçerliliği/veri kalitesi ayrı ele alınır.
- Mevcut kod: `VALIDITY_RULES` (service.py, Iter 8.6), `sensor_out_of_range`/`sensor_frozen` (Iter 8.3),
  `anomalies.rule_set` (migration 004, Iter 8.5).

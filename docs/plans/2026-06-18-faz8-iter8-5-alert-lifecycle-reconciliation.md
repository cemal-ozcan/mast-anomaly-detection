# Faz 8 Iter 8.5 — Uyarı Yaşam Döngüsü Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detector'ın uyarı yaşam döngüsü durumunu in-memory `active` dict'ten **DB-tek-hakikat + per-poll idempotent reconciliation**'a taşı; manuel resolve'u kaldır (P2, gözlem-modu); `rule_set` fingerprint kolonu ekle.

**Architecture:** `anomalies` tablosuna `rule_set TEXT` (fingerprint) kolonu (migration 004 + schema.py Core Table). `_detect_once` her poll DB'den açık-uyarı fingerprint'lerini okuyup level-triggered uzlaşır (cihaz-temiz→resolve-all; fingerprint-eşleşir→debounce; eşleşmez→yeni-aç). In-memory `active` kalkar → restart orphan inşaat gereği biter. Dashboard'dan manuel resolve butonu + `resolve_alert` repository metodu silinir; ACK kalır.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 Core, SQLite, pytest, mypy strict, ruff. Detector servisi (`src/detectors/`), storage (`src/storage/`), dashboard (`src/dashboard/`).

## Global Constraints

- **Spec (tek hakem):** `docs/specs/2026-06-18-faz8-iter8-5-alert-lifecycle-reconciliation-design.md`. Sapma → önce spec.
- **Mimari kararlar (spec § 2, değişmez):** DB-tek-hakikat + reconciliation; fingerprint=`device+rule_set` (sıralı virgül-bağlı, timestamp YOK); P2 = manuel resolve kaldırılır (ACK kalır); çözüm cihaz-seviyesi, açma fingerprint-seviyesi (eskalasyon/limit 3 korunur).
- **Tip ipuçları zorunlu** (mypy strict). **Docstring zorunlu** (Google stili, Türkçe). **Spesifik exception** (`except Exception` yasak); `OperationalError` yakalanır, loguru.
- **İKİ-KAYNAK (migration 003 deseni):** `anomalies` hem SQL migration'da hem `schema.py` Core `Table`'da → `rule_set` İKİSİNE eklenir.
- **Gözlem modu korunur:** detector yalnız telemetry okur + anomalies okur/yazar (telemetri yazmaz, cihaz kontrol etmez); dashboard yalnız `status` (ack) yazar.
- **TDD:** önce başarısız test, sonra minimal kod. **Sık commit.**
- **Test/lint disiplini (her task sonunda):** `.venv/bin/python -m pytest -q` + `.venv/bin/python -m mypy src/detectors src/storage src/dashboard src/alerts tests/unit tests/integration tests/scenarios` + `ruff check src tests` (ruff = homebrew PATH).
- **Python:** her zaman `.venv/bin/python`.
- **ATOMİK İNİŞ:** `rule_set` zorunlu param + `_detect_once` imza değişimi tüm çağrı yerlerini kırar → ilgili task kural+config+test'i birlikte indirir (yoksa suite kırık kalır).

---

## File Structure

| Dosya | Durum | Sorumluluk |
|---|---|---|
| `src/storage/migrations/004_alert_fingerprint.sql` | YENİ | `rule_set TEXT` kolonu |
| `src/storage/schema.py` | +Column | `anomalies` Table'a `rule_set` |
| `src/storage/repository.py` | edit | `insert_anomaly(+rule_set)`, `_anomaly_to_dict(+rule_set)`, YENİ `fetch_open_fingerprints`, `resolve_alert` SİL |
| `src/detectors/service.py` | rework | `_detect_once` DB-reconciliation (active kalkar), `run()` active kaldır |
| `src/dashboard/app.py` | edit | resolve butonu sil (ack kalır) |
| `tests/...` | güncelle | migrator version, insert_anomaly çağrıları, _detect_once çağrıları, resolve_alert testi sil, YENİ reconciliation/restart/fingerprint testleri |
| `docs/DEMO.md` | güncelle | P2 (ack-only) + reconciliation notu |

---

## Task 1: Migration 004 + schema.py Column

**Files:**
- Create: `src/storage/migrations/004_alert_fingerprint.sql`
- Modify: `src/storage/schema.py` (anomalies Table)
- Test: `tests/unit/test_storage_migrator.py`

**Interfaces:**
- Produces: `anomalies` tablosunda nullable `rule_set TEXT` kolonu (SQL + Core Table); migrator version 4.

- [ ] **Step 1: Migrator version testini güncelle (kırmızı yapacak)**

`tests/unit/test_storage_migrator.py` içinde:
```python
    assert versions == [1, 2, 3]
```
→
```python
    assert versions == [1, 2, 3, 4]
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_migrator.py -q`
Expected: FAIL — `assert [1, 2, 3] == [1, 2, 3, 4]` (004 henüz yok)

- [ ] **Step 3: Migration 004 dosyasını oluştur**

`src/storage/migrations/004_alert_fingerprint.sql`:
```sql
-- Iter 8.5 reconciliation: rule_set = uyarının fingerprint'i (sıralı, virgülle birleştirilmiş
-- kural adları). DB-tek-hakikat reconciliation'da açık-uyarı kimliği. Nullable (legacy satır NULL).
ALTER TABLE anomalies ADD COLUMN rule_set TEXT;
```

- [ ] **Step 4: schema.py Core Table'a kolonu ekle**

`src/storage/schema.py` `anomalies` Table'ında, `resolved_at` satırından SONRA:
```python
    Column("resolved_at", Text),  # nullable
    Column("rule_set", Text),  # nullable — fingerprint (Iter 8.5)
)
```

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_migrator.py -q`
Expected: PASS (versions [1,2,3,4])
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (1 skipped) — kolon nullable, mevcut kod kullanmıyor → kırılma yok
Run: `.venv/bin/python -m mypy src/storage && ruff check src/storage tests/unit/test_storage_migrator.py`

- [ ] **Step 6: Commit**

```bash
git add src/storage/migrations/004_alert_fingerprint.sql src/storage/schema.py tests/unit/test_storage_migrator.py
git commit -m "feat(storage): migration 004 anomalies.rule_set fingerprint kolonu (Faz 8 Iter 8.5)"
```

---

## Task 2: `insert_anomaly` rule_set parametresi + tüm çağrı yerleri

**Files:**
- Modify: `src/storage/repository.py` (`insert_anomaly`, `_anomaly_to_dict`)
- Modify: `src/detectors/service.py` (`_detect_once` insert çağrısı — yalnız bu satır; tam rework Task 4)
- Test: `tests/unit/test_storage_anomaly_repository.py`, `tests/unit/test_storage_alert_repository.py`, `tests/integration/test_detector_persistence.py`

**Interfaces:**
- Consumes: schema `rule_set` kolonu (Task 1).
- Produces: `insert_anomaly(anomaly: Anomaly, created_at: str, rule_set: str) -> None` — `rule_set` `anomalies.rule_set` kolonuna yazılır.

- [ ] **Step 1: Başarısız test ekle (rule_set yazıldığını doğrula)**

`tests/unit/test_storage_anomaly_repository.py` içine yeni test:
```python
def test_insert_anomaly_persists_rule_set(migrated_engine: Engine) -> None:
    """insert_anomaly rule_set fingerprint'i yazar (Iter 8.5)."""
    from sqlalchemy import text

    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anomaly(), "2026-05-30T00:00:00.000Z", "motor_current_high,vibration_elevated")
    with migrated_engine.connect() as conn:
        rs = conn.execute(text("SELECT rule_set FROM anomalies")).scalar_one()
    assert rs == "motor_current_high,vibration_elevated"
```
(NOT: `_anomaly(*, device_id=, rule_name=, ...)` bu dosyadaki mevcut keyword-only Anomaly helper'ı; `text` zaten import'lu.)

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_anomaly_repository.py::test_insert_anomaly_persists_rule_set -q`
Expected: FAIL — `insert_anomaly() missing 1 required positional argument: 'rule_set'`

- [ ] **Step 3: `insert_anomaly` + `_anomaly_to_dict`'i güncelle**

`src/storage/repository.py`:
```python
    def insert_anomaly(self, anomaly: Anomaly, created_at: str, rule_set: str) -> None:
```
docstring'e `rule_set` satırı ekle (`rule_set: uyarının fingerprint'i — sıralı virgül-bağlı kural adları (Iter 8.5)`); gövde:
```python
        with self._engine.begin() as conn:
            conn.execute(
                anomalies.insert().values(**self._anomaly_to_dict(anomaly, created_at, rule_set))
            )
```
`_anomaly_to_dict` imzası + dönüş:
```python
    def _anomaly_to_dict(anomaly: Anomaly, created_at: str, rule_set: str) -> dict[str, object]:
        """Anomaly + created_at + rule_set'i anomalies kolon dict'ine çevirir."""
        return {
            "device_id": anomaly.device_id,
            "rule_name": anomaly.rule_name,
            "sensor": anomaly.sensor,
            "severity": anomaly.severity,
            "score": anomaly.score,
            "window_start": anomaly.window_start,
            "window_end": anomaly.window_end,
            "value": anomaly.value,
            "description": anomaly.description,
            "created_at": created_at,
            "rule_set": rule_set,
        }
```

- [ ] **Step 4: Production çağrı yerini güncelle (service.py — yalnız bu satır)**

`src/detectors/service.py` `_detect_once` içindeki:
```python
            repository.insert_anomaly(fused, created_at)
```
→
```python
            repository.insert_anomaly(fused, created_at, ",".join(sorted(rule_set)))
```
(NOT: `rule_set` bu noktada zaten hesaplı; tam rework Task 4.)

- [ ] **Step 5: Tüm test çağrı yerlerini güncelle**

Her `insert_anomaly(<anomaly>, <created_at>)` çağrısına 3. arg ekle = o anomalinin `rule_name`'i (tek-kural test anomalisi için fingerprint = rule_name yeterli):
- `tests/unit/test_storage_anomaly_repository.py`: `_anomaly()` çağrıları → `repo.insert_anomaly(_anomaly(), _CREATED, "motor_temperature_high")` (varsayılan rule_name).
- `tests/unit/test_storage_alert_repository.py`: `_anom(...)` çağrıları → 3. arg o anomalinin rule'u (ör. `repo.insert_anomaly(_anom(rule="motor_current_high"), _CREATED, "motor_current_high")`).
- `tests/integration/test_detector_persistence.py:42,66`: **keyword `created_at=` formu** → `repo.insert_anomaly(anomalies[0], created_at="2026-05-30T00:00:03.000Z", rule_set=anomalies[0].rule_name)` (ve :66 benzeri `rule_set=anomaly.rule_name`).

Kalan kırıkları bul: `grep -rn "insert_anomaly(" tests src` → 2-arg kalan var mı (rule_set'siz) doğrula.

- [ ] **Step 6: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (1 skipped)
Run: `.venv/bin/python -m mypy src/storage src/detectors tests/unit tests/integration && ruff check src tests`

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(storage): insert_anomaly rule_set fingerprint yazar + tüm çağrı yerleri (Faz 8 Iter 8.5)"
```

---

## Task 3: `fetch_open_fingerprints` repository metodu

**Files:**
- Modify: `src/storage/repository.py`
- Test: `tests/unit/test_storage_alert_repository.py`

**Interfaces:**
- Consumes: `rule_set` kolonu (Task 1), ACTIVE/ACKNOWLEDGED sabitleri (`alerts.lifecycle`, repository'de zaten import).
- Produces: `fetch_open_fingerprints() -> dict[str, set[frozenset[str]]]` — cihaz → açık (active|acknowledged) uyarıların rule_set frozenset'leri; resolved DÖNMEZ; NULL rule_set → boş frozenset.

- [ ] **Step 1: Başarısız test ekle**

`tests/unit/test_storage_alert_repository.py` içine:
```python
def test_fetch_open_fingerprints_groups_by_device(migrated_engine: Engine) -> None:
    """active+acknowledged uyarıların rule_set'leri cihaz başına kümelenir; resolved hariç (Iter 8.5)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(device="d1", rule="motor_current_high"), "2026-05-30T00:00:00.000Z", "motor_current_high")
    repo.insert_anomaly(_anom(device="d1", rule="fused(2)"), "2026-05-30T00:00:01.000Z", "motor_current_high,vibration_elevated")
    repo.insert_anomaly(_anom(device="d2", rule="iqr:motor_current"), "2026-05-30T00:00:02.000Z", "iqr:motor_current")
    # d2'nin uyarısını resolve et → fingerprints'te görünmemeli
    repo.resolve_open_alerts("d2", "2026-05-30T00:01:00.000Z")

    fps = repo.fetch_open_fingerprints()

    assert fps["d1"] == {frozenset({"motor_current_high"}), frozenset({"motor_current_high", "vibration_elevated"})}
    assert "d2" not in fps
```
(NOT: `_anom(device=, rule=)` bu dosyadaki mevcut helper'dır — Anomaly döndürür, `device_id`/`rule_name` ayarlar.)

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_alert_repository.py::test_fetch_open_fingerprints_groups_by_device -q`
Expected: FAIL — `AttributeError: 'TelemetryRepository' object has no attribute 'fetch_open_fingerprints'`

- [ ] **Step 3: Metodu ekle**

`src/storage/repository.py`'ye (diğer alert metotlarının yanına):
```python
    def fetch_open_fingerprints(self) -> dict[str, set[frozenset[str]]]:
        """Açık (active|acknowledged) uyarıların rule_set fingerprint'lerini cihaz başına döndürür.

        Reconciliation kaynağı (Iter 8.5): detector her poll bunu okuyup level-triggered uzlaşır.
        NULL rule_set (legacy satır) → boş frozenset.

        Returns:
            device_id → o cihazın açık uyarılarının rule_set frozenset'leri kümesi.
        """
        result: dict[str, set[frozenset[str]]] = {}
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(anomalies.c.device_id, anomalies.c.rule_set).where(
                    anomalies.c.status.in_((ACTIVE, ACKNOWLEDGED))
                )
            )
            for device_id, rule_set_str in rows:
                fingerprint = frozenset(rule_set_str.split(",")) if rule_set_str else frozenset()
                result.setdefault(str(device_id), set()).add(fingerprint)
        return result
```
(NOT: `ACTIVE`/`ACKNOWLEDGED` ve `select`/`anomalies` repository'de zaten import'lu — doğrula.)

- [ ] **Step 4: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_alert_repository.py -q`
Expected: PASS
Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src/storage tests/unit && ruff check src/storage tests`

- [ ] **Step 5: Commit**

```bash
git add src/storage/repository.py tests/unit/test_storage_alert_repository.py
git commit -m "feat(storage): fetch_open_fingerprints (reconciliation kaynağı, Faz 8 Iter 8.5)"
```

---

## Task 4: `_detect_once` DB-reconciliation reworku + `run()`

**Files:**
- Modify: `src/detectors/service.py` (`_detect_once`, `run()`)
- Test: `tests/unit/detectors/test_service_detect_once.py` (mevcut çağrılar + yeni reconciliation/restart testleri), `tests/integration/test_statistical_detector.py`, `tests/integration/test_detector_config_driven.py`

**Interfaces:**
- Consumes: `repository.fetch_open_fingerprints()` (Task 3), `repository.resolve_open_alerts`, `insert_anomaly(+rule_set)` (Task 2).
- Produces: `_detect_once(repository, detector_groups, now)` — **`active` parametresi YOK**; durum DB'den okunur.

- [ ] **Step 1: Mevcut testleri yeni imzaya taşı + yeni testler ekle**

`tests/unit/detectors/test_service_detect_once.py`:
- Tüm `_detect_once(repo, groups, active, _NOW)` çağrılarından `active` argümanını çıkar → `_detect_once(repo, groups, _NOW)`.
- Tüm `active: dict[str, frozenset[str]] = {}` satırlarını sil.
- `active` dict'ine assert eden satırlar varsa (örn. `assert active == {...}`) → DB-tabanlı assert'e çevir: süregelen arıza için `repo.fetch_open_fingerprints()` veya `repo.fetch_recent_anomalies(...)` ile doğrula. (Mevcut debounce/auto-resolve testleri zaten DB durumuna assert ediyor → çoğu yalnız `active` arg silinerek geçer; çünkü reconciliation durumu DB'de yaşıyor.)

Yeni testler ekle:
```python
def test_reconcile_debounce_same_fingerprint(migrated_engine: Engine) -> None:
    """Aynı fingerprint açıkken ikinci poll yeni satır YAZMAZ (DB-reconciliation debounce)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    groups = [([MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)], _BIG_WINDOW_S)]
    _detect_once(repo, groups, _NOW)
    _detect_once(repo, groups, _NOW)  # ikinci poll — fingerprint açık → debounce
    assert len(repo.fetch_recent_anomalies(limit=10)) == 1


def test_reconcile_restart_no_orphan_no_duplicate(migrated_engine: Engine) -> None:
    """'Soğuk' detector (in-memory durum yok): süregelen arıza debounce, temizlenen auto-resolve."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    groups = [([MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)], _BIG_WINDOW_S)]
    _detect_once(repo, groups, _NOW)  # 1. süreç: uyarı açıldı
    assert repo.fetch_open_fingerprints() == {"device_001": {frozenset({"motor_temperature_high"})}}
    # "restart" = aynı DB ile yeni _detect_once çağrısı (in-memory durum taşınmaz)
    _detect_once(repo, groups, _NOW)  # arıza sürüyor → debounce, duplikat yok
    assert len(repo.fetch_recent_anomalies(limit=10)) == 1


def test_reconcile_clean_device_auto_resolves(migrated_engine: Engine) -> None:
    """Cihaz temizlenince açık uyarılar auto-resolve (rule_set boş + açık fingerprint var)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    groups = [([MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)], _BIG_WINDOW_S)]
    _detect_once(repo, groups, _NOW)            # uyarı açık
    # temiz okuma ekle, eskiyi pencere dışına itecek kadar ileri NOW (veya düşük değer)
    repo.insert(_reading("motor_temperature", "2026-05-30T01:00:00.000Z", 20.0))
    from datetime import timedelta
    _detect_once(repo, groups, _NOW + timedelta(hours=1, seconds=1))  # rule_set boş → auto-resolve
    assert repo.fetch_open_fingerprints() == {}
```
(NOT: `RESOLVED` importu mevcut kodda nereden geliyorsa oradan; temiz-okuma testinde pencere/NOW ayarını mevcut `_BIG_WINDOW_S` yerine gerçekçi window_s ile kur ki eski yüksek değer pencereden düşsün — gerekirse window_s=3600 + uygun NOW.)

`tests/integration/test_statistical_detector.py` ve `test_detector_config_driven.py`: `_detect_once(...)` çağrılarından `active` argümanını + `active = {}` satırlarını çıkar.

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -q`
Expected: FAIL — `_detect_once() takes ... positional arguments but ... were given` / yeni testler `active` yok hatası (kod hâlâ eski imza)

- [ ] **Step 3: `_detect_once`'ı reworkle**

`src/detectors/service.py` `_detect_once`'ı tümüyle değiştir (gruplar/pencere/error iskelesi KORUNUR; yalnız `active` kalkar + karar bloğu DB-fingerprint olur):
```python
def _detect_once(
    repository: TelemetryRepository,
    detector_groups: list[tuple[list[Detector], int]],
    now: datetime,
) -> None:
    """Tek poll: her cihaz × her dedektör-grubu → fusion → DB-tek-hakikat reconciliation (Iter 8.5).

    In-memory durum YOK: açık-uyarı fingerprint'leri her poll DB'den okunur (`fetch_open_fingerprints`).
    Diff (level-triggered): cihaz temiz + açık uyarı var → auto-resolve; firing + fingerprint açık (ack
    dahil) → debounce; firing + fingerprint açık değil → yeni uyarı. Restart = bu yolun ilk koşumu (orphan yok).
    """
    created_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    open_fingerprints = repository.fetch_open_fingerprints()

    for device_id in repository.list_devices():
        device_anomalies: list[Anomaly] = []
        window_cache: dict[int, pd.DataFrame] = {}
        for detectors, window_s in detector_groups:
            window = window_cache.get(window_s)
            if window is None:
                window = build_window(
                    repository, device_id, SENSORS, _since_cutoff(now, window_s)
                )
                window_cache[window_s] = window
            if window.empty:  # pragma: no cover - list_devices yalnız telemetri'si olan cihazları döndürür
                continue
            for detector in detectors:
                try:
                    device_anomalies.extend(detector.detect(window))
                except (KeyError, ValueError) as e:
                    logger.error("Dedektör '{}' hata verdi, atlandı: {}", detector.name, e)
                    continue

        rule_set = frozenset(a.rule_name for a in device_anomalies)
        open_fps = open_fingerprints.get(device_id, set())

        if not rule_set:  # cihaz temiz
            if open_fps:  # açık uyarısı varsa auto-resolve (limit 2: restart'ta da DB'den okunur)
                try:
                    closed = repository.resolve_open_alerts(device_id, created_at)
                    if closed:
                        logger.info("Auto-resolve: device={} kapatılan uyarı={}", device_id, closed)
                except OperationalError as e:
                    logger.error("Auto-resolve yazılamadı (atlandı): {}", e)
            continue

        if rule_set in open_fps:  # aynı fingerprint açık (active veya acknowledged) → debounce
            continue

        # firing ama bu fingerprint açık değil → yeni uyarı (ilk tespit / eskalasyon)
        fused = fuse_anomalies(device_anomalies)
        if fused is None:  # pragma: no cover - rule_set boş değilse fused None olamaz
            continue
        try:
            repository.insert_anomaly(fused, created_at, ",".join(sorted(rule_set)))
        except OperationalError as e:
            logger.error("Anomali yazılamadı (atlandı): {}", e)
            continue
        logger.info(
            "Alert: device={} rules={} value={:.2f} sev={}",
            fused.device_id,
            sorted(rule_set),
            fused.value,
            fused.severity,
        )
```

- [ ] **Step 4: `run()`'ı güncelle (active kaldır)**

`src/detectors/service.py` `run()` içinde:
- `active: dict[str, frozenset[str]] = {}` satırını SİL.
- Poll çağrısını `_detect_once(repository, detector_groups, datetime.now(UTC))` yap (`active` argümanı kalkar).

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -q`
Expected: PASS (mevcut + 3 yeni reconciliation testi)
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (1 skipped)
Run: `.venv/bin/python -m mypy src/detectors tests/unit tests/integration tests/scenarios && ruff check src tests`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(detectors): _detect_once DB-tek-hakikat reconciliation (in-memory active kalktı, restart orphan biter, Faz 8 Iter 8.5)"
```

---

## Task 5: Manuel resolve'u kaldır (P2) — dashboard + repository

**Files:**
- Modify: `src/dashboard/app.py` (`_render_alert_management`)
- Modify: `src/storage/repository.py` (`resolve_alert` SİL)
- Test: `tests/unit/test_storage_alert_repository.py` (resolve_alert testlerini sil/uyarlat)

**Interfaces:**
- Produces: dashboard'da yalnız ACK butonu; `resolve_alert` repository metodu artık yok (`resolve_open_alerts` korunur — detector auto-resolve).

- [ ] **Step 1: Dashboard resolve butonunu kaldır**

`src/dashboard/app.py` `_render_alert_management` içinde şu iki satırı SİL:
```python
    if can_transition(selected.status, RESOLVED) and cols[1].button("Çöz (resolve)", key="resolve_btn"):
        _apply_transition(repository.resolve_alert, selected.id)
```
ve `cols = st.columns(2)` → `cols = st.columns(1)` (tek buton). Docstring'i güncelle: "Açık bir uyarıyı **ACK** eden yönetim kontrolü (P2: manuel resolve yok — çözümü detector sahiplenir, Iter 8.5)." `RESOLVED` importu başka yerde kullanılmıyorsa kaldır (mypy/ruff unused yakalar → doğrula).

- [ ] **Step 2: `resolve_alert` testlerini güncelle (kırmızı yapacak)**

`tests/unit/test_storage_alert_repository.py`:
- **SİL** `test_acknowledge_then_resolve_alert` (resolve_alert'i test eder) + `test_acknowledge_resolved_alert_is_noop` (resolve_alert noop'unu test eder).
- **UYARLAT** `test_fetch_alerts_status_filter_and_all` (resolve_alert'i yalnız *setup* için kullanıyor): `repo.resolve_alert(repo.fetch_alerts(("active",), limit=10)[-1].id, "...")` satırını `repo.resolve_open_alerts(<o uyarının device_id'si>, "...")` ile değiştir (aynı sonucu üretir — bir uyarı resolved olur). Filtre assert'leri korunur.
- `test_resolve_open_alerts_closes_all_non_resolved_for_device` + ack testleri **KALIR** (resolve_open_alerts/ack korunuyor).

- [ ] **Step 3: Başarısız olduğunu doğrula (resolve_alert hâlâ kodda)**

Run: `ruff check src/storage src/dashboard`
Expected: resolve_alert silinmeden önce — bu adım aslında "resolve_alert'i sil" için; testler silindiğinden suite zaten resolve_alert'siz. Aşağıda kaldır.

- [ ] **Step 4: `resolve_alert` metodunu repository'den sil**

`src/storage/repository.py`'den `def resolve_alert(...)` metodunu tümüyle SİL.

- [ ] **Step 5: Test + tam suite + lint**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (1 skipped) — resolve_alert çağrısı kalmadı
Run: `.venv/bin/python -m mypy src/storage src/dashboard tests/unit && ruff check src tests`
Expected: temiz (unused import yok)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(dashboard): P2 — manuel resolve kaldırıldı (ack kalır, çözümü detector sahiplenir) + resolve_alert silindi (Faz 8 Iter 8.5)"
```

---

## Task 6: Kapanış — DEMO.md + canlı smoke (CONTROLLER)

> Controller (sen) yürütür: doküman + manuel canlı smoke (restart dahil) + closure.

- [ ] **Step 1: `docs/DEMO.md` güncelle**

"Bilinen Sınırlar" + uyarı yönetimi bölümlerini güncelle: manuel resolve artık YOK (P2); teknisyen **ack**'ler, sistem arıza sensörlerce temizlenince **auto-resolve** eder; detector restart'ta orphan uyarı kalmaz (DB-reconciliation). Faz 7 § 9 limit 1+2'nin çözüldüğünü, limit 3'ün (eskalasyon) korunduğunu not et.

- [ ] **Step 2: Tam suite + mypy + ruff (son)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (1 skipped)
Run: `.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/dashboard src/alerts tests/unit tests/integration tests/scenarios`
Run: `ruff check src tests`
Expected: temiz

- [ ] **Step 3: Canlı demo smoke (6 cihaz + restart)**

Run: `./scripts/demo_up.sh`; ~3-4 dk bekle.
Doğrula: `sqlite3 data/telemetry.db "SELECT device_id, rule_name, status, rule_set FROM anomalies ORDER BY created_at DESC LIMIT 20;"` — arızalar `active`; `rule_set` doluyor.
**Restart testi:** detector sürecini öldür + yeniden başlat (`logs/demo`'dan pid; `kill` sonra `PYTHONPATH=src .venv/bin/python -m detectors &`), birkaç poll bekle → **duplikat uyarı yok, süregelen arızalar debounce, orphan yok** doğrula.
**Ack testi:** dashboard'da (http://localhost:8501) bir uyarıyı ack'le → `acknowledged`; **resolve butonu YOK** doğrula; arıza temizlenince auto-resolve.
Run: `./scripts/demo_down.sh` (temiz teardown).

- [ ] **Step 4: Closure commit (CLAUDE.md + ROADMAP + memory)**

CLAUDE.md "Mevcut Faz" + Iter 8.5 closure bloğu + ROADMAP Iter 8.5 DONE + memory `project_active_phase.md` (Iter 8.5 ✅, sıradaki 8.6). Canlı smoke sonucu.
```bash
git add -A
git commit -m "docs(faz8): Iter 8.5 closure — reconciliation + P2 DONE + canlı smoke (restart orphan yok)"
```

---

## Self-Review

**1. Spec coverage:**
- §3 in-memory active kaldır → Task 4. ✓
- §4 migration 004 + schema.py Column (C1) → Task 1. ✓
- §5 reconciliation diff (clean→resolve / fingerprint→debounce / else→open; iskele korunur) → Task 4 Step 3. ✓
- §6 insert_anomaly+rule_set → Task 2; fetch_open_fingerprints → Task 3; resolve_alert sil → Task 5; resolve_open_alerts/ack korunur. ✓
- §7 dashboard resolve butonu sil, ack kalır → Task 5. ✓
- §8 atomik iniş + ~20 test çağrı yeri → Task 2 (insert_anomaly sites) + Task 4 (_detect_once sites) + Task 5 (resolve_alert sites). ✓
- §10 test stratejisi (reconciliation/restart/fetch_open_fingerprints/dashboard) → Task 3/4/5 testleri + Task 6 canlı smoke. ✓
- §11 kabul kriterleri → tüm tasklar + Task 6 closure. ✓

**2. Placeholder taraması:** Kod blokları gerçek; test helper isimleri (`_make_anomaly`/`_alert_anomaly`) mevcut dosya kalıbına bağlandı (yoksa inline kullanım not edildi); migration/schema/diff kodu tam. ✓

**3. Tip tutarlılığı:** `insert_anomaly(anomaly, created_at, rule_set: str)` (Task 2) ↔ `_detect_once` çağrısı `",".join(sorted(rule_set))` (Task 2/4) ↔ `fetch_open_fingerprints() -> dict[str, set[frozenset[str]]]` (Task 3) ↔ `_detect_once(repository, detector_groups, now)` (Task 4) — imzalar tutarlı. `rule_set in open_fps` (frozenset ∈ set[frozenset]) tip-doğru. ✓

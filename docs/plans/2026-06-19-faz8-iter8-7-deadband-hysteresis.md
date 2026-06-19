# Faz 8 Iter 8.7 — Deadband Hysteresis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Açık bir uyarıyı, arıza "firing değil" olur olmaz değil, **N ardışık temiz poll** sonra resolve ederek resolve↔reopen flapping'ini bastırmak (deadband hysteresis).

**Architecture:** `_detect_once` clean+open dalı genişler: hemen `resolve_open_alerts` yerine açık uyarının DB-backed `clean_streak` sayacını artırır; sayaç `deadband_clean_polls`'a ulaşınca resolve eder. Firing poll'u sayacı 0'a sıfırlar (`update_alert`) → salınan arıza tek açık uyarı kalır. Sayaç DB'de (migration 005) → 8.5/8.6 "DB tek hakikat + stateless detector + level-triggered" korunur, restart-safe.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 Core, pytest, mypy (strict), ruff, loguru.

## Global Constraints

- **Spec (tek hakem):** `docs/specs/2026-06-19-faz8-iter8-7-deadband-hysteresis-design.md`.
- **Mekanizma:** deadband (N-ardışık-temiz-poll); çift-eşik/Schmitt YOK (kural kalibrasyonu gerekmez).
- **Sayaç DB-backed:** `anomalies.clean_streak INTEGER NOT NULL DEFAULT 0` (migration 005). In-memory state YOK.
- **Config-driven:** `deadband_clean_polls: int = 3` (default'lu → geriye-uyumlu; hand-picked sabit yok).
- **Değişmez kontratlar:** `Anomaly` (write), `fuse_anomalies`, `Detector` ABC, `band_position_score`, `severity_from_band`/`apply_band_severity` (8.6), gözlem modu (yalnız telemetry oku / anomalies yaz), skor [0,1], ACK yaşam döngüsü (`can_transition`, `acknowledge_alert`, `resolve_open_alerts`, `reactivate_alert`). 8.6 cihaz-seviyesi dört-kadran reconciliation iskeleti korunur; yalnız clean+open dalı genişler.
- **Tip ipuçları zorunlu** (mypy strict), **docstring zorunlu** (Google stili), `loguru` (print yok).
- **Test komutu:** `.venv/bin/python -m pytest <path> -q -p no:cacheprovider --no-cov`. Tam suite: `.venv/bin/python -m pytest`. Lint: `.venv/bin/python -m mypy src/detectors src/storage tests/unit tests/integration tests/scenarios` + `ruff check ...` (**ruff = homebrew PATH**).
- **Yürütme ortamı:** subagent'lar Bash/Write izinsiz → controller-inline implement + salt-okunur reviewer (8.4/8.5/8.6 hibrit).

---

## Dosya Haritası

| Dosya | Sorumluluk | Değişim |
|---|---|---|
| `src/storage/migrations/005_clean_streak.sql` | clean_streak kolonu DDL | YENİ |
| `src/storage/schema.py` | Core Table kolon referansı | +`clean_streak` Column |
| `src/alerts/models.py` | Alert okuma modeli | +`clean_streak: int = 0` (default'lu) |
| `src/storage/repository.py` | sayaç oku/yaz | `_row_to_alert`+clean_streak; `update_alert` reset 0; +`set_clean_streak` |
| `src/detectors/config.py` | deadband config | +`DetectorConfig.deadband_clean_polls` + loader |
| `config/detectors.yaml.example`, `config/detectors.demo.yaml` | deadband knob | +`deadband_clean_polls: 3` |
| `src/detectors/service.py` | reconciliation | `_detect_once` clean+open deadband + `run()` wire |
| tests | TDD | migrator/schema_version + repo + config + detect_once |

---

### Task 1: Migration 005 + schema kolonu + migrator testleri

**Files:**
- Create: `src/storage/migrations/005_clean_streak.sql`
- Modify: `src/storage/schema.py:51` (rule_set Column'undan sonra)
- Test: `tests/unit/test_storage_migrator.py:24,49`

**Interfaces:**
- Produces: `anomalies.clean_streak` kolonu (Integer, NOT NULL, DEFAULT 0); migration version 5.

- [ ] **Step 1: Update migrator tests (failing)**

`tests/unit/test_storage_migrator.py` satır 24: `assert versions == [1, 2, 3, 4]` → `assert versions == [1, 2, 3, 4, 5]`
satır 49: `assert count == 4` → `assert count == 5`

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_migrator.py -q -p no:cacheprovider --no-cov`
Expected: FAIL (`versions == [1,2,3,4]`, beklenen 5).

- [ ] **Step 3: Create migration + schema column**

`src/storage/migrations/005_clean_streak.sql`:
```sql
-- Iter 8.7 deadband hysteresis: clean_streak = açık uyarının ardışık "temiz" (firing-olmayan) poll
-- sayısı. firing → 0; clean → +1; deadband_clean_polls'a ulaşınca resolve (anti-flap). NOT NULL DEFAULT 0.
ALTER TABLE anomalies ADD COLUMN clean_streak INTEGER NOT NULL DEFAULT 0;
```

`src/storage/schema.py` — `Column("rule_set", Text), ...` satırından SONRA (anomalies Table içinde, kapanış `)` öncesi):
```python
    Column("clean_streak", Integer, nullable=False),  # Iter 8.7 deadband sayacı (DB DEFAULT 0, migration 005)
```
(`Integer` zaten import'lu — satır 10.)

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_migrator.py tests/unit/test_storage_schema.py -q -p no:cacheprovider --no-cov`
Expected: PASS (migrator version/count 5; schema testi index-only, etkilenmez).

- [ ] **Step 5: Commit**

```bash
git add src/storage/migrations/005_clean_streak.sql src/storage/schema.py tests/unit/test_storage_migrator.py
git commit -m "feat(storage): migration 005 anomalies.clean_streak kolonu (Faz 8 Iter 8.7 deadband)"
```

---

### Task 2: Alert.clean_streak + repository (`_row_to_alert`, `update_alert` reset, `set_clean_streak`)

**Files:**
- Modify: `src/alerts/models.py` (Alert dataclass)
- Modify: `src/storage/repository.py` (`_row_to_alert`, `update_alert`, +`set_clean_streak`)
- Test: `tests/unit/test_storage_alert_repository.py`

**Interfaces:**
- Consumes: `anomalies.clean_streak` (Task 1).
- Produces:
  - `Alert.clean_streak: int = 0` (frozen dataclass alanı, default'lu → mevcut Alert(...) constructor'ları kırılmaz).
  - `set_clean_streak(alert_id: int, streak: int) -> bool` — `anomalies.update().where(id==alert_id).values(clean_streak=streak)`; rowcount>0.
  - `update_alert` artık `.values(...)`'a `clean_streak=0` ekler (firing → reset). İmza DEĞİŞMEZ.
  - `_row_to_alert` → `clean_streak=row.clean_streak`.

- [ ] **Step 1: Write failing tests** (append to `tests/unit/test_storage_alert_repository.py`)

```python
def test_set_clean_streak(migrated_engine: Engine) -> None:
    """set_clean_streak sayacı yazar; fetch_open_alerts onu taşır."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id
    assert repo.set_clean_streak(alert_id, 2) is True
    assert repo.fetch_open_alerts()["device_001"][0].clean_streak == 2


def test_insert_anomaly_defaults_clean_streak_zero(migrated_engine: Engine) -> None:
    """insert_anomaly clean_streak set etmez → DB DEFAULT 0."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    assert repo.fetch_open_alerts()["device_001"][0].clean_streak == 0


def test_update_alert_resets_clean_streak(migrated_engine: Engine) -> None:
    """update_alert (firing refresh) clean_streak'i 0'a çeker."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id
    repo.set_clean_streak(alert_id, 2)
    repo.update_alert(alert_id, rule_name="motor_current_high", sensor="motor_current",
                      severity="critical", score=0.9, value=12.5, window_end="w",
                      rule_set="motor_current_high", description="d")
    assert repo.fetch_open_alerts()["device_001"][0].clean_streak == 0
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_alert_repository.py -q -p no:cacheprovider --no-cov`
Expected: FAIL (`Alert` has no `clean_streak` / `set_clean_streak` yok).

- [ ] **Step 3a: Add Alert field** (`src/alerts/models.py`, `resolved_at` alanından SONRA, dataclass sonu)

```python
    resolved_at: str | None
    clean_streak: int = 0  # Iter 8.7 deadband sayacı (default'lu → mevcut constructor'lar kırılmaz)
```

- [ ] **Step 3b: `_row_to_alert` taşısın** (`src/storage/repository.py`, `_row_to_alert` içinde `resolved_at=row.resolved_at,` satırından sonra)

```python
            resolved_at=row.resolved_at,
            clean_streak=row.clean_streak,
```

- [ ] **Step 3c: `update_alert` reset** (`src/storage/repository.py`, `update_alert` `.values(...)` içine, `description=description,` satırından sonra)

```python
                    description=description,
                    clean_streak=0,
```
Docstring'e tek satır: "firing → `clean_streak=0` (deadband sayacı sıfırlanır, Iter 8.7)."

- [ ] **Step 3d: Add `set_clean_streak`** (`src/storage/repository.py`, `resolve_alert_by_id`'dan sonra)

```python
    def set_clean_streak(self, alert_id: int, streak: int) -> bool:
        """Açık bir uyarının deadband sayacını yazar (Iter 8.7).

        clean+open poll'da arıza yoksa sayaç artırılır; `deadband_clean_polls`'a ulaşınca resolve edilir
        (anti-flap). Firing → `update_alert` 0'a sıfırlar.

        Args:
            alert_id: Güncellenecek satır id'si.
            streak: Yeni clean_streak değeri.

        Returns:
            Satır güncellendiyse True; id yoksa False.
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update().where(anomalies.c.id == alert_id).values(clean_streak=streak)
            )
        return result.rowcount > 0
```

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_alert_repository.py -q -p no:cacheprovider --no-cov`
Expected: PASS (3 yeni + mevcutlar — mevcut Alert(...) constructor'ları default sayesinde kırılmaz).

- [ ] **Step 5: Commit**

```bash
git add src/alerts/models.py src/storage/repository.py tests/unit/test_storage_alert_repository.py
git commit -m "feat(storage): Alert.clean_streak + set_clean_streak + update_alert reset (Faz 8 Iter 8.7)"
```

---

### Task 3: Config `deadband_clean_polls`

**Files:**
- Modify: `src/detectors/config.py` (`DetectorConfig` + `load_detector_config`)
- Modify: `config/detectors.yaml.example`, `config/detectors.demo.yaml`
- Test: `tests/unit/detectors/test_config.py`

**Interfaces:**
- Produces: `DetectorConfig.deadband_clean_polls: int = 3`; loader top-level `deadband_clean_polls` okur (yoksa 3).

- [ ] **Step 1: Write failing tests** (append to `tests/unit/detectors/test_config.py`)

```python
def test_load_deadband_clean_polls_from_yaml(tmp_path: Path) -> None:
    """deadband_clean_polls top-level okunur (Faz 8 Iter 8.7)."""
    p = _write(
        tmp_path / "d.yaml",
        "detectors:\n  poll_interval_s: 5.0\n  window_s: 120\n  rules: []\n"
        "deadband_clean_polls: 5\n",
    )
    assert load_detector_config(p).deadband_clean_polls == 5


def test_deadband_clean_polls_default_when_absent(tmp_path: Path) -> None:
    """deadband_clean_polls yoksa default 3."""
    p = _write(
        tmp_path / "d.yaml",
        "detectors:\n  poll_interval_s: 5.0\n  window_s: 120\n  rules: []\n",
    )
    assert load_detector_config(p).deadband_clean_polls == 3
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_config.py -k deadband -q -p no:cacheprovider --no-cov`
Expected: FAIL (`AttributeError: ... 'deadband_clean_polls'`).

- [ ] **Step 3a: Add field** (`src/detectors/config.py`, `DetectorConfig`, `severity_bands` alanından sonra)

```python
    severity_bands: SeverityBands = SeverityBands()
    deadband_clean_polls: int = 3
```

- [ ] **Step 3b: Loader parse** (`src/detectors/config.py`, `load_detector_config`, `severity_bands = ...` bloğundan sonra; `return DetectorConfig(...)`'a ekle)

```python
        deadband_clean_polls = int(data.get("deadband_clean_polls", 3))
        return DetectorConfig(
            poll_interval_s=float(det["poll_interval_s"]),
            window_s=int(det["window_s"]),
            rules=rules,
            statistical=statistical,
            severity_bands=severity_bands,
            deadband_clean_polls=deadband_clean_polls,
        )
```

- [ ] **Step 3c: YAML knob** (her iki dosya sonuna, top-level)

`config/detectors.yaml.example` ve `config/detectors.demo.yaml`:
```yaml
# Deadband hysteresis (Faz 8 Iter 8.7): arıza N ardışık temiz poll yoksa resolve (anti-flap).
deadband_clean_polls: 3
```

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_config.py -q -p no:cacheprovider --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/detectors/config.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/detectors/test_config.py
git commit -m "feat(detectors): deadband_clean_polls config (Faz 8 Iter 8.7)"
```

---

### Task 4: `_detect_once` clean+open deadband + `run()` wire + mevcut test uyarlaması

**Files:**
- Modify: `src/detectors/service.py` (`_detect_once` imza + clean+open dalı, `run()`)
- Test: `tests/unit/detectors/test_service_detect_once.py`

**Interfaces:**
- Consumes: `set_clean_streak`, `resolve_open_alerts`, `Alert.clean_streak` (Task 1-2); `DetectorConfig.deadband_clean_polls` (Task 3).
- Produces: `_detect_once(repository, detector_groups, now, severity_bands=_DEFAULT_SEVERITY_BANDS, deadband_clean_polls=3)`.

- [ ] **Step 1: Write/adapt tests** (`tests/unit/detectors/test_service_detect_once.py`)

**(a) Mevcut iki clean-path testini deadband=1 ile uyarla** (tek temiz poll resolve = eski davranış):

`test_auto_resolves_on_clear` içindeki İKİNCİ `_detect_once` çağrısı (arıza temizlendikten sonraki):
```python
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 1)  # deadband=1 → anlık resolve
```
`test_resolves_preexisting_open_on_clean_device` içindeki `_detect_once` çağrısı:
```python
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 1)  # deadband=1 → anlık resolve
```

**(b) Yeni deadband testleri** (dosya sonuna ekle):
```python
def test_deadband_holds_open_until_threshold(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 3)  # firing → açık
    assert len(_active(repo)) == 1
    # Arıza temizlenir; deadband=3 → 2 temiz poll açık tutar, 3.'de resolve.
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 25.0 WHERE sensor='motor_temperature'"))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 3)  # temiz #1
    assert len(_active(repo)) == 1 and _active(repo)[0].clean_streak == 1
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 3)  # temiz #2
    assert len(_active(repo)) == 1 and _active(repo)[0].clean_streak == 2
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 3)  # temiz #3 → resolve
    assert _active(repo) == []
    assert len(repo.fetch_alerts(("resolved",), limit=10)) == 1


def test_deadband_firing_resets_streak_no_flap(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 3)  # firing → açık
    first_id = _active(repo)[0].id
    # temiz #1, #2 (streak 1,2)
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 25.0 WHERE sensor='motor_temperature'"))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 3)
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 3)
    assert _active(repo)[0].clean_streak == 2
    # arıza geri döner (flap): firing → streak 0'a sıfırlanır, AYNI satır (yeni incident yok)
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 95.0 WHERE sensor='motor_temperature'"))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS, 3)
    open_now = _active(repo)
    assert len(open_now) == 1 and open_now[0].id == first_id and open_now[0].clean_streak == 0
    assert len(repo.fetch_recent_anomalies(limit=10)) == 1  # tek satır, flap-reopen yok
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -q -p no:cacheprovider --no-cov`
Expected: FAIL (yeni deadband testleri — `_detect_once` 5. param kabul etmez / deadband mantığı yok).

- [ ] **Step 3a: `_detect_once` imza + clean+open dalı** (`src/detectors/service.py`)

İmza:
```python
def _detect_once(
    repository: TelemetryRepository,
    detector_groups: list[tuple[list[Detector], int]],
    now: datetime,
    severity_bands: SeverityBands = _DEFAULT_SEVERITY_BANDS,
    deadband_clean_polls: int = 3,
) -> None:
```

clean+open dalını (`if not rule_set:` bloğu) tümüyle değiştir:
```python
        if not rule_set:  # cihaz temiz
            if open_list:
                # Deadband: hemen resolve etme; N ardışık temiz poll'dan sonra kapat (anti-flap).
                primary = max(open_list, key=lambda a: (a.created_at, a.id))
                new_streak = primary.clean_streak + 1
                try:
                    if new_streak >= deadband_clean_polls:
                        closed = repository.resolve_open_alerts(device_id, created_at)
                        if closed:
                            logger.info(
                                "Auto-resolve: device={} kapatılan={} (deadband {}p)",
                                device_id, closed, deadband_clean_polls,
                            )
                    else:
                        repository.set_clean_streak(primary.id, new_streak)
                except OperationalError as e:
                    logger.error("Deadband/auto-resolve yazılamadı (atlandı): {}", e)
            continue
```
(Docstring'e tek satır: "clean+open → deadband: `clean_streak`++ → `deadband_clean_polls`'da resolve; firing `update_alert` ile 0'a sıfırlar.")

- [ ] **Step 3b: `run()` wire** (`src/detectors/service.py`, poll çağrısı)

```python
                _detect_once(
                    repository,
                    detector_groups,
                    datetime.now(UTC),
                    detector_config.severity_bands,
                    detector_config.deadband_clean_polls,
                )
```

- [ ] **Step 4: Run unit + full suite**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -q -p no:cacheprovider --no-cov`
Expected: PASS (deadband testleri + uyarlanan resolve testleri).

Run: `.venv/bin/python -m pytest -q -p no:cacheprovider --no-cov`
Expected: tümü yeşil. **Olası kırılma:** integration/scenario testleri `_detect_once`'ı 4 arg (severity_bands'siz veya bands'le) çağırıyorsa deadband default 3 → tek temiz poll resolve etmez. Bu testler firing/fused doğruluyor (resolve değil) → etkilenmemeli; biri tek-poll-resolve'a dayanıyorsa `deadband_clean_polls=1` geçir (firing testleri default'la çalışır). Kırılırsa o testte 5. arg=1 ekle.

- [ ] **Step 5: mypy + ruff + commit**

Run: `.venv/bin/python -m mypy src/detectors src/storage tests/unit tests/integration tests/scenarios` + `ruff check src/detectors src/storage tests/unit tests/integration tests/scenarios`
Expected: temiz.

```bash
git add src/detectors/service.py tests/unit/detectors/test_service_detect_once.py
git commit -m "feat(detectors): _detect_once clean+open deadband hysteresis + run() wire (Faz 8 Iter 8.7)"
```

---

### Task 5: Closure — canlı smoke (anti-flap) + docs/memory

> **Controller-run (TDD task değil).**

- [ ] **Step 1: Tam suite + mypy + ruff (final)** — hepsi yeşil (~+8 test: migrator 0-net, repo +3, config +2, detect_once +2 -0).

- [ ] **Step 2: Canlı 6-cihaz demo smoke** (`./scripts/demo_up.sh`)
  - Eşik civarı yavaş-geçiş / ramp sonunda **resolve↔reopen flapping olmadığını** doğrula (DB: cihaz başına tek satır, resolve/insert churn yok).
  - Gerçek düzelmede uyarının ~`deadband_clean_polls` poll sonra resolve olduğunu gözle (`clean_streak` 1→2→3 izlenebilir).
  - 8.6 regresyon: skor/severity refresh, ack→band-up re-activate, detector restart orphan/duplikat-yok korunur.
  - Gerekirse `deadband_clean_polls`'u smoke ölçümüyle kalibre et (demo + example YAML).
  - Teardown: `./scripts/demo_down.sh` + config `.bak` geri yükle.

- [ ] **Step 3: Docs** — `CLAUDE.md` Mevcut Faz + Faz 8'e Iter 8.7 closure özeti; sıradaki Iter 8.8 = (5) sensör-sağlığı ekseni.

- [ ] **Step 4: Memory** — `project_active_phase.md`: Iter 8.7 DONE runtime contract + HANDOFF → Iter 8.8.

- [ ] **Step 5: Final whole-branch review** (salt-okunur reviewer) → fix loop.

- [ ] **Step 6:** Kullanıcı onayıyla PR/merge (push proaktif YAPMA).

---

## Self-Review (yazar kontrolü)

**1. Spec coverage:** §1 deadband amaç → T4. §3 migration 005 + Alert.clean_streak → T1+T2. §4 reconciliation clean+open deadband → T4. §5 repository (set_clean_streak, update_alert reset, _row_to_alert) → T2. §6 config → T3. §7 dashboard değişiklik yok → task yok (doğru). §8 test + smoke → her task TDD + T5. §9 değişmez kontratlar → Global Constraints + hiçbir task Anomaly/fuse/8.6-iskelet/migration-şema-dışına dokunmaz. ✓ Boşluk yok.

**2. Placeholder scan:** Tüm kod blokları tam; "TBD/handle edge cases" yok. ✓

**3. Type consistency:** `set_clean_streak(alert_id:int, streak:int)->bool` (T2) ↔ `_detect_once` çağrısı `repository.set_clean_streak(primary.id, new_streak)` (T4) tutarlı. `Alert.clean_streak:int` (T2) ↔ `primary.clean_streak` okuma (T4) tutarlı. `deadband_clean_polls:int` (T3 config ↔ T4 param ↔ T4 run wire) tutarlı. `clean_streak` kolon adı T1 schema ↔ T1 SQL ↔ T2 _row_to_alert ↔ T2 update_alert values hepsinde aynı. ✓

# Faz 7 Iter 7.1 — Alert Manager (Uyarı Yaşam Döngüsü) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ham anomalileri yönetilebilir uyarılara dönüştürmek: `active → acknowledged → resolved` yaşam döngüsü + detector auto-resolve (arıza temizlenince) + dashboard'dan manuel ack/resolve + duruma göre filtre.

**Architecture:** Mevcut `anomalies` tablosu 3 kolonla genişletilir (`status`/`acknowledged_at`/`resolved_at`, migration 003). Yeni saf `src/alerts/` paketi durum-geçiş kurallarını (`lifecycle.py`) ve okuma/yönetim modelini (`models.py` `Alert`) barındırır. `TelemetryRepository` 4 alert metodu kazanır (geçişler SQL `WHERE` ile atomik zorlanır). Detector `_detect_once` re-arm dalında auto-resolve eder. Dashboard durum kolonu + filtre + ack/resolve butonları kazanır (gözlem modu korunur — yalnız uyarı durumu yazılır). `Detector` ABC, `Anomaly`, `fuse_anomalies`, `insert_anomaly` DEĞİŞMEZ.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 Core, SQLite (script-based migration), pytest, Streamlit 1.36 (`st.experimental_fragment`). Venv: `.venv/bin/python -m pytest|mypy`, ruff = homebrew `ruff` (PATH; `.venv -m ruff` YOK).

---

## Spec Referansı

Tek hakem: `docs/specs/2026-06-03-faz7-alert-manager-design.md`. Kabul kriterleri § 11, veri modeli § 5, repository API § 7, yaşam döngüsü § 6, dashboard § 8, hata/sınırlar § 9.

## Dosya Yapısı

**Yeni:**
- `src/alerts/__init__.py` — boş paket işaretçisi.
- `src/alerts/lifecycle.py` — SAF: `ACTIVE/ACKNOWLEDGED/RESOLVED` sabitleri + `ALLOWED_TRANSITIONS` + `can_transition`.
- `src/alerts/models.py` — `Alert` frozen dataclass (okuma/yönetim görünümü).
- `src/storage/migrations/003_alert_lifecycle.sql` — ALTER TABLE + index (version-gated).
- `tests/unit/alerts/__init__.py`, `tests/unit/alerts/test_lifecycle.py` — lifecycle birim testleri.
- `tests/integration/test_alert_repository.py` — migration default + repository alert metotları.

**Değişen:**
- `src/storage/schema.py` — `anomalies` Table'a 3 kolon + `idx_anomalies_status` (DDL ÇALIŞTIRMAZ).
- `src/storage/repository.py` — `_row_to_alert` + `acknowledge_alert`/`resolve_alert`/`resolve_open_alerts`/`fetch_alerts`.
- `src/detectors/service.py` — `_detect_once` re-arm dalı → `resolve_open_alerts`.
- `src/dashboard/transform.py` — `anomalies_to_frame` → `alerts_to_frame` (Alert + `durum` kolonu).
- `src/dashboard/app.py` — `_render_alerts` filtre + yönetim kontrolü (`fetch_alerts`).
- `tests/unit/dashboard/test_transform.py` — `anomalies_to_frame` testi → `alerts_to_frame`.

**Değişmez:** `src/detectors/base.py`, `src/detectors/fusion.py`, `repository.insert_anomaly`, `repository.fetch_recent_anomalies` (Faz 5 integration testleri kullanıyor — kalır).

---

### Task 1: Migration 003 + schema.py kolonları

**Files:**
- Create: `src/storage/migrations/003_alert_lifecycle.sql`
- Modify: `src/storage/schema.py`
- Test: `tests/integration/test_alert_repository.py`

- [ ] **Step 1: Failing test yaz** (`tests/integration/test_alert_repository.py`)

```python
"""Alert yaşam döngüsü: migration 003 + repository metotları (Faz 7 Iter 7.1, spec § 5/§ 7)."""
from __future__ import annotations

from sqlalchemy import Engine, text

from detectors.base import Anomaly
from storage.repository import TelemetryRepository

_CREATED = "2026-06-03T10:00:00.000Z"


def _anom(device: str = "device_001", rule: str = "motor_current_high") -> Anomaly:
    return Anomaly(
        device_id=device, rule_name=rule, sensor="motor_current", severity="high",
        score=0.9, window_start="2026-06-03T09:59:00.000Z", window_end="2026-06-03T10:00:00.000Z",
        value=10.0, description="test",
    )


def test_insert_anomaly_defaults_status_active(migrated_engine: Engine) -> None:
    """insert_anomaly status set etmez → DB DEFAULT 'active'; acknowledged_at/resolved_at NULL."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), _CREATED)
    with migrated_engine.connect() as conn:
        row = conn.execute(text("SELECT status, acknowledged_at, resolved_at FROM anomalies")).one()
    assert row.status == "active"
    assert row.acknowledged_at is None
    assert row.resolved_at is None
```

- [ ] **Step 2: Testi koştur, fail doğrula**

Run: `.venv/bin/python -m pytest tests/integration/test_alert_repository.py::test_insert_anomaly_defaults_status_active -v`
Expected: FAIL — `OperationalError: no such column: status`.

- [ ] **Step 3: Migration 003 yaz** (`src/storage/migrations/003_alert_lifecycle.sql`)

```sql
-- Iter 7.1 uyarı yaşam döngüsü: anomalies satırları yönetilebilir uyarı olur (spec § 5).
-- Version-gated (migrator schema_version ile bir kez uygular).
ALTER TABLE anomalies ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE anomalies ADD COLUMN acknowledged_at TEXT;
ALTER TABLE anomalies ADD COLUMN resolved_at TEXT;
CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies (status, created_at);
```

- [ ] **Step 4: schema.py'ye kolonları + index ekle**

`src/storage/schema.py` — `anomalies` Table'ında `Column("created_at", Text, nullable=False),` satırından SONRA (Table parantezinin içinde) ekle:
```python
    Column("status", Text, nullable=False),  # active | acknowledged | resolved (migration 003)
    Column("acknowledged_at", Text),  # nullable
    Column("resolved_at", Text),  # nullable
```
ve `idx_anomalies_device_created = Index(...)` bloğundan SONRA ekle:
```python
# Dashboard durum filtresi (Faz 7 Iter 7.1, spec § 5).
idx_anomalies_status = Index(
    "idx_anomalies_status",
    anomalies.c.status,
    anomalies.c.created_at,
)
```

- [ ] **Step 5: Testi koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/integration/test_alert_repository.py -v`
Expected: PASS (1 test). Ayrıca mevcut storage testleri kırılmamalı: `.venv/bin/python -m pytest tests/integration tests/unit/storage -q` → tümü PASS (migrated_engine fixture 003'ü de uygular; schema.py Table ↔ migration tutarlı).

- [ ] **Step 6: mypy + ruff + commit**

```bash
.venv/bin/python -m mypy src/storage tests/integration
ruff check src/storage tests/integration
git add src/storage/migrations/003_alert_lifecycle.sql src/storage/schema.py tests/integration/test_alert_repository.py
git commit -m "feat(storage): migration 003 anomalies yaşam döngüsü kolonları + schema (Faz 7 Iter 7.1)"
```
Expected: mypy `Success`, ruff `All checks passed!`.

---

### Task 2: `src/alerts/` paketi — lifecycle (saf) + Alert modeli

**Files:**
- Create: `src/alerts/__init__.py`, `src/alerts/lifecycle.py`, `src/alerts/models.py`
- Create: `tests/unit/alerts/__init__.py`, `tests/unit/alerts/test_lifecycle.py`

- [ ] **Step 1: Failing test yaz** (`tests/unit/alerts/test_lifecycle.py`)

```python
"""alerts.lifecycle saf durum-geçiş kuralları (Faz 7 Iter 7.1, spec § 6)."""
from __future__ import annotations

import pytest

from alerts.lifecycle import (
    ACKNOWLEDGED,
    ACTIVE,
    RESOLVED,
    can_transition,
)


@pytest.mark.parametrize(
    ("current", "target", "expected"),
    [
        (ACTIVE, ACKNOWLEDGED, True),
        (ACTIVE, RESOLVED, True),
        (ACKNOWLEDGED, RESOLVED, True),
        (ACKNOWLEDGED, ACTIVE, False),
        (RESOLVED, ACTIVE, False),
        (RESOLVED, ACKNOWLEDGED, False),
        (ACTIVE, ACTIVE, False),
        (ACKNOWLEDGED, ACKNOWLEDGED, False),
    ],
)
def test_can_transition(current: str, target: str, expected: bool) -> None:
    assert can_transition(current, target) is expected


def test_can_transition_unknown_status_false() -> None:
    """Bilinmeyen mevcut durum → hiçbir geçiş geçerli değil."""
    assert can_transition("bogus", RESOLVED) is False
```

- [ ] **Step 2: Testi koştur, fail doğrula**

Run: `.venv/bin/python -m pytest tests/unit/alerts/test_lifecycle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alerts'`.

- [ ] **Step 3: Paket + modülleri yaz**

`src/alerts/__init__.py`:
```python
"""Alert yaşam döngüsü paketi (Faz 7): saf durum-geçiş kuralları + Alert okuma modeli."""
```

`src/alerts/lifecycle.py`:
```python
"""Uyarı durum makinesi: geçerli geçişler (Faz 7 Iter 7.1, spec § 6).

SAF — dış bağımlılık yok. Repository geçişleri SQL WHERE ile atomik zorlar; dashboard
hangi butonu göstereceğine bununla karar verir. Geçiş matrisi tek kaynak burada.
"""
from __future__ import annotations

ACTIVE = "active"
ACKNOWLEDGED = "acknowledged"
RESOLVED = "resolved"

# Geçerli geçişler: active→{ack,resolved}, acknowledged→{resolved}, resolved→{} (terminal).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ACTIVE: frozenset({ACKNOWLEDGED, RESOLVED}),
    ACKNOWLEDGED: frozenset({RESOLVED}),
    RESOLVED: frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    """current durumundan target durumuna geçiş geçerli mi?

    Args:
        current: Mevcut durum (active/acknowledged/resolved).
        target: Hedef durum.

    Returns:
        Geçiş ALLOWED_TRANSITIONS'ta tanımlıysa True; bilinmeyen current → False.
    """
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())
```

`src/alerts/models.py`:
```python
"""Alert okuma/yönetim modeli (Faz 7 Iter 7.1, spec § 5).

Anomaly (detector yazma kontratı) DEĞİŞMEZ; Alert ayrı bir okuma görünümüdür — kimlik (id),
durum ve yaşam döngüsü zaman damgalarını içerir. Düz (flat) dataclass: DataFrame transform
ve dashboard tüketimi için sade.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Alert:
    """anomalies tablosundan okunan, yaşam döngüsü durumu olan bir uyarı."""

    id: int
    device_id: str
    rule_name: str
    sensor: str
    severity: str
    score: float
    window_start: str
    window_end: str
    value: float
    description: str
    created_at: str
    status: str
    acknowledged_at: str | None
    resolved_at: str | None
```

- [ ] **Step 4: Testi koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/unit/alerts/test_lifecycle.py -v`
Expected: PASS (9 test: 8 parametrize + 1 unknown).

- [ ] **Step 5: mypy + ruff + commit**

```bash
.venv/bin/python -m mypy src/alerts tests/unit/alerts
ruff check src/alerts tests/unit/alerts
git add src/alerts tests/unit/alerts
git commit -m "feat(alerts): saf lifecycle durum makinesi + Alert modeli (Faz 7 Iter 7.1)"
```

---

### Task 3: Repository alert metotları + `_row_to_alert`

**Files:**
- Modify: `src/storage/repository.py`
- Test: `tests/integration/test_alert_repository.py` (Task 1 dosyasına ekle)

- [ ] **Step 1: Failing testleri ekle** (`tests/integration/test_alert_repository.py` dosyasının SONUNA)

```python
def test_acknowledge_then_resolve_alert(migrated_engine: Engine) -> None:
    """active→acknowledged→resolved geçişleri zaman damgalarını yazar."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), _CREATED)
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id

    assert repo.acknowledge_alert(alert_id, "2026-06-03T10:01:00.000Z") is True
    acked = repo.fetch_alerts(("acknowledged",), limit=10)
    assert len(acked) == 1 and acked[0].acknowledged_at == "2026-06-03T10:01:00.000Z"

    assert repo.resolve_alert(alert_id, "2026-06-03T10:02:00.000Z") is True
    resolved = repo.fetch_alerts(("resolved",), limit=10)
    assert len(resolved) == 1 and resolved[0].resolved_at == "2026-06-03T10:02:00.000Z"


def test_acknowledge_resolved_alert_is_noop(migrated_engine: Engine) -> None:
    """resolved bir uyarı ack'lenemez (geçersiz geçiş → 0 satır → False)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), _CREATED)
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id
    repo.resolve_alert(alert_id, "2026-06-03T10:02:00.000Z")
    assert repo.acknowledge_alert(alert_id, "2026-06-03T10:03:00.000Z") is False


def test_resolve_open_alerts_closes_all_non_resolved_for_device(migrated_engine: Engine) -> None:
    """resolve_open_alerts cihazın tüm açık (active+acknowledged) uyarılarını kapatır, resolved'a dokunmaz."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(rule="motor_current_high"), _CREATED)
    repo.insert_anomaly(_anom(rule="fused(2)"), "2026-06-03T10:00:05.000Z")
    repo.insert_anomaly(_anom(device="device_002"), _CREATED)  # başka cihaz — etkilenmemeli
    # device_001'in birini ack'le (yine açık sayılır)
    d1_first = repo.fetch_alerts(("active",), limit=10)
    repo.acknowledge_alert([a.id for a in d1_first if a.device_id == "device_001"][0],
                           "2026-06-03T10:01:00.000Z")

    closed = repo.resolve_open_alerts("device_001", "2026-06-03T10:05:00.000Z")
    assert closed == 2  # device_001'in iki açık satırı
    assert {a.device_id for a in repo.fetch_alerts(("resolved",), limit=10)} == {"device_001"}
    assert len(repo.fetch_alerts(("active",), limit=10)) == 1  # device_002 hâlâ açık


def test_fetch_alerts_status_filter_and_all(migrated_engine: Engine) -> None:
    """statuses=None tümünü; tuple verince IN filtreler; created_at DESC."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), _CREATED)
    repo.insert_anomaly(_anom(device="device_002"), "2026-06-03T10:00:05.000Z")
    repo.resolve_alert(repo.fetch_alerts(("active",), limit=10)[-1].id, "2026-06-03T10:06:00.000Z")
    assert len(repo.fetch_alerts(None, limit=10)) == 2
    assert len(repo.fetch_alerts(("active", "acknowledged"), limit=10)) == 1
    assert len(repo.fetch_alerts(("resolved",), limit=10)) == 1
```

- [ ] **Step 2: Testi koştur, fail doğrula**

Run: `.venv/bin/python -m pytest tests/integration/test_alert_repository.py -v`
Expected: FAIL — `AttributeError: 'TelemetryRepository' object has no attribute 'fetch_alerts'`.

- [ ] **Step 3: Repository'ye import + `_row_to_alert` + 4 metot ekle**

`src/storage/repository.py` — dosya başındaki import bloğuna ekle (mevcut `from detectors.base import Anomaly` yanına):
```python
from alerts.lifecycle import ACKNOWLEDGED, ACTIVE, RESOLVED
from alerts.models import Alert
```
`_row_to_anomaly` static metodundan SONRA ekle:
```python
    @staticmethod
    def _row_to_alert(row: Row[Any]) -> Alert:
        """SQLAlchemy Row'u Alert'e çevirir (id + status + lifecycle zaman damgaları dahil)."""
        return Alert(
            id=row.id,
            device_id=row.device_id,
            rule_name=row.rule_name,
            sensor=row.sensor,
            severity=row.severity,
            score=row.score,
            window_start=row.window_start,
            window_end=row.window_end,
            value=row.value,
            description=row.description,
            created_at=row.created_at,
            status=row.status,
            acknowledged_at=row.acknowledged_at,
            resolved_at=row.resolved_at,
        )
```
`fetch_recent_anomalies` metodundan SONRA ekle:
```python
    def acknowledge_alert(self, alert_id: int, acknowledged_at: str) -> bool:
        """active bir uyarıyı acknowledged yapar (spec § 7). Geçiş SQL WHERE ile atomik zorlanır.

        Returns:
            Satır güncellendiyse True (geçiş geçerliydi); 0 satır → False (zaten ack/resolved).
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update()
                .where(anomalies.c.id == alert_id, anomalies.c.status == ACTIVE)
                .values(status=ACKNOWLEDGED, acknowledged_at=acknowledged_at)
            )
        return result.rowcount > 0

    def resolve_alert(self, alert_id: int, resolved_at: str) -> bool:
        """active|acknowledged bir uyarıyı resolved yapar (spec § 7).

        Returns:
            Satır güncellendiyse True; 0 satır → False (zaten resolved).
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update()
                .where(
                    anomalies.c.id == alert_id,
                    anomalies.c.status.in_((ACTIVE, ACKNOWLEDGED)),
                )
                .values(status=RESOLVED, resolved_at=resolved_at)
            )
        return result.rowcount > 0

    def resolve_open_alerts(self, device_id: str, resolved_at: str) -> int:
        """Bir cihazın TÜM açık (resolved olmayan) uyarılarını resolved yapar (detector auto-resolve, spec § 6).

        Returns:
            Kapatılan satır sayısı.
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update()
                .where(anomalies.c.device_id == device_id, anomalies.c.status != RESOLVED)
                .values(status=RESOLVED, resolved_at=resolved_at)
            )
        return int(result.rowcount)

    def fetch_alerts(self, statuses: tuple[str, ...] | None, limit: int) -> list[Alert]:
        """Uyarıları (opsiyonel status filtresiyle) created_at DESC döndürür (dashboard, spec § 7/§ 8).

        Args:
            statuses: Filtre durum tuple'ı (status IN ...); None → tümü.
            limit: Maksimum satır sayısı.

        Returns:
            created_at DESC sıralı Alert listesi.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        stmt = select(anomalies)
        if statuses is not None:
            stmt = stmt.where(anomalies.c.status.in_(statuses))
        stmt = stmt.order_by(anomalies.c.created_at.desc()).limit(limit)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_alert(row) for row in rows]
```

> **Not:** `anomalies` zaten `repository.py`'de import edili (`from storage.schema import ... anomalies ...`). `select`/`func` de import edili. `anomalies.update()` ekstra import gerektirmez. `result.rowcount` SQLAlchemy Core `CursorResult` özelliğidir.

- [ ] **Step 4: Testi koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/integration/test_alert_repository.py -v`
Expected: PASS (5 test: Task 1'in 1 + bu 4).

- [ ] **Step 5: mypy + ruff + commit**

```bash
.venv/bin/python -m mypy src/storage src/alerts tests/integration
ruff check src/storage tests/integration
git add src/storage/repository.py tests/integration/test_alert_repository.py
git commit -m "feat(storage): alert ack/resolve/resolve_open/fetch_alerts repository metotları (Faz 7 Iter 7.1)"
```

---

### Task 4: Detector auto-resolve (`_detect_once` re-arm dalı)

**Files:**
- Modify: `src/detectors/service.py`
- Test: `tests/unit/detectors/test_service_detect_once.py`

- [ ] **Step 1: Failing testleri ekle** (`tests/unit/detectors/test_service_detect_once.py` dosyasının SONUNA)

Dosyanın import bloğunda `from sqlalchemy import Engine, text` zaten var. Ekle:
```python
def test_detect_once_auto_resolves_open_alert_on_clear(migrated_engine: Engine) -> None:
    """Arıza temizlenince (re-arm) cihazın açık uyarısı otomatik resolved olur (Faz 7)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    active: dict[str, frozenset[str]] = {}

    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], active, _NOW)  # active uyarı yazılır
    assert [a.status for a in repo.fetch_alerts(None, limit=10)] == ["active"]

    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 25.0 WHERE sensor = 'motor_temperature'"))
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], active, _NOW)  # arıza temizlendi → auto-resolve

    resolved = repo.fetch_alerts(("resolved",), limit=10)
    assert len(resolved) == 1
    assert resolved[0].resolved_at is not None
    assert active == {}


def test_detect_once_no_resolve_when_device_never_active(migrated_engine: Engine) -> None:
    """Hiç arıza vermemiş cihaz için re-arm dalı resolve_open_alerts çağırmaz (boşa UPDATE yok)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))  # eşik altı
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    active: dict[str, frozenset[str]] = {}
    # Önce manuel bir resolved-olmayan satır ekle; clean cihaz turu buna DOKUNMAMALI.
    repo.insert_anomaly(
        Anomaly(device_id="device_001", rule_name="x", sensor="s", severity="warning",
                score=0.1, window_start="a", window_end="b", value=1.0, description="d"),
        "2026-05-30T00:00:00.000Z",
    )
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], active, _NOW)
    assert [a.status for a in repo.fetch_alerts(None, limit=10)] == ["active"]  # dokunulmadı
```

- [ ] **Step 2: Testi koştur, fail doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py::test_detect_once_auto_resolves_open_alert_on_clear -v`
Expected: FAIL — uyarı `resolved` olmaz (auto-resolve henüz yok), `fetch_alerts(("resolved",))` boş döner → assert hatası.

- [ ] **Step 3: `_detect_once` re-arm dalını güncelle**

`src/detectors/service.py` — `_detect_once` içindeki mevcut re-arm bloğunu:
```python
        rule_set = frozenset(a.rule_name for a in device_anomalies)
        if not rule_set:
            active.pop(device_id, None)  # fault temizlendi → re-arm
            continue
```
şununla değiştir:
```python
        rule_set = frozenset(a.rule_name for a in device_anomalies)
        if not rule_set:
            if device_id in active:  # izlenen arıza gerçekten temizlendi → auto-resolve (Faz 7)
                active.pop(device_id, None)
                try:
                    closed = repository.resolve_open_alerts(device_id, created_at)
                    if closed:
                        logger.info(
                            "Auto-resolve: device={} kapatılan uyarı={}", device_id, closed
                        )
                except OperationalError as e:
                    logger.error("Auto-resolve yazılamadı (atlandı): {}", e)
            continue
```

> **Not:** `created_at`, `_detect_once` başında zaten hesaplanıyor (`created_at = now.isoformat(...)`). `logger` ve `OperationalError` zaten import edili. Guard (`if device_id in active`) her poll'da temiz cihaz için boşa UPDATE'i önler (spec § 6).

- [ ] **Step 4: Testi koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -v`
Expected: PASS (mevcut tüm _detect_once testleri + 2 yeni). Özellikle `test_detect_once_escalation_writes_new_row` hâlâ PASS olmalı (eskalasyon davranışı değişmedi — eski satır resolve edilmez).

- [ ] **Step 5: mypy + ruff + commit**

```bash
.venv/bin/python -m mypy src/detectors tests/unit/detectors
ruff check src/detectors tests/unit/detectors
git add src/detectors/service.py tests/unit/detectors/test_service_detect_once.py
git commit -m "feat(detectors): _detect_once re-arm'da uyarı auto-resolve (Faz 7 Iter 7.1)"
```

---

### Task 5: Dashboard — `alerts_to_frame` + filtre + yönetim kontrolü

**Files:**
- Modify: `src/dashboard/transform.py`
- Modify: `src/dashboard/app.py`
- Test: `tests/unit/dashboard/test_transform.py`

- [ ] **Step 1: transform testini `alerts_to_frame`'e güncelle (failing)**

`tests/unit/dashboard/test_transform.py` — mevcut `anomalies_to_frame` testini bul. Onu şununla DEĞİŞTİR (Anomaly yerine Alert kurar, `durum` kolonunu doğrular):
```python
def test_alerts_to_frame_columns_and_status() -> None:
    """alerts_to_frame durum kolonu içerir; girdi sırasını korur; skor yuvarlanır."""
    from alerts.models import Alert
    from dashboard.transform import alerts_to_frame

    alerts = [
        Alert(id=1, device_id="device_001", rule_name="motor_current_high", sensor="motor_current",
              severity="high", score=0.912, window_start="s", window_end="2026-06-03T10:00:00.000Z",
              value=10.0, description="d", created_at="c", status="active",
              acknowledged_at=None, resolved_at=None),
    ]
    frame = alerts_to_frame(alerts)
    assert list(frame.columns) == ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"]
    assert frame.iloc[0]["durum"] == "active"
    assert frame.iloc[0]["skor"] == 0.91
    assert frame.iloc[0]["zaman"] == "2026-06-03T10:00:00.000Z"


def test_alerts_to_frame_empty_correct_schema() -> None:
    """Boş girdi → 0 satırlı, doğru kolonlu DataFrame."""
    from dashboard.transform import alerts_to_frame

    frame = alerts_to_frame([])
    assert list(frame.columns) == ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"]
    assert len(frame) == 0
```
(Eski `anomalies_to_frame` test fonksiyon(lar)ını sil. Ayrıca dosyanın ÜST kısmında modül-seviyesi `from dashboard.transform import anomalies_to_frame` veya `from detectors.base import Anomaly` importu varsa kaldır — yeni testler importları fonksiyon içinde yapıyor; aksi halde `ImportError`/ruff unused-import.)

- [ ] **Step 2: Testi koştur, fail doğrula**

Run: `.venv/bin/python -m pytest tests/unit/dashboard/test_transform.py -v`
Expected: FAIL — `ImportError: cannot import name 'alerts_to_frame'`.

- [ ] **Step 3: `transform.py` — `anomalies_to_frame`'i `alerts_to_frame` ile değiştir**

`src/dashboard/transform.py` — dosya başındaki `from detectors.base import Anomaly` importunu şununla değiştir:
```python
from alerts.models import Alert
```
ve mevcut `_ALERT_COLUMNS` + `anomalies_to_frame` bloğunu şununla DEĞİŞTİR:
```python
_ALERT_COLUMNS = ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"]


def alerts_to_frame(alerts: list[Alert]) -> pd.DataFrame:
    """Alert listesini "Uyarılar" tablosu için DataFrame'e çevirir (spec § 8).

    Args:
        alerts: fetch_alerts çıktısı (created_at DESC sıralı; boş olabilir).

    Returns:
        [zaman, cihaz, severity, sensör, kural, skor, durum, açıklama] kolonlu DataFrame;
        girdi sırasını korur. `zaman` = window_end, `skor` 2 ondalığa yuvarlanır, `durum` =
        yaşam döngüsü durumu. Boş girdi → 0 satırlı ama doğru-şemalı DataFrame.
    """
    return pd.DataFrame(
        {
            "zaman": [a.window_end for a in alerts],
            "cihaz": [a.device_id for a in alerts],
            "severity": [a.severity for a in alerts],
            "sensör": [a.sensor for a in alerts],
            "kural": [a.rule_name for a in alerts],
            "skor": [round(a.score, 2) for a in alerts],
            "durum": [a.status for a in alerts],
            "açıklama": [a.description for a in alerts],
        },
        columns=_ALERT_COLUMNS,
    )
```

- [ ] **Step 4: Testi koştur, geç doğrula**

Run: `.venv/bin/python -m pytest tests/unit/dashboard/test_transform.py -v`
Expected: PASS.

- [ ] **Step 5: `app.py` — `_render_alerts`'i filtre + yönetim ile güncelle**

`src/dashboard/app.py` — import güncellemeleri:
- `from dashboard.transform import (...)` listesinde `anomalies_to_frame` → `alerts_to_frame`.
- Yeni importlar ekle (dosya başındaki uygun gruplara):
```python
from collections.abc import Callable

from alerts.lifecycle import ACKNOWLEDGED, RESOLVED, can_transition
from storage.repository import TelemetryRepository
```
(`TelemetryRepository`, `datetime`, `UTC`, `OperationalError`, `logger`, `st` zaten import edili — yoksa ekle.)

Mevcut `_render_alerts` fonksiyonunu (tamamı) şununla DEĞİŞTİR:
```python
_STATUS_FILTERS: dict[str, tuple[str, ...] | None] = {
    "Açık": ("active", "acknowledged"),
    "Tümü": None,
    "active": ("active",),
    "acknowledged": ("acknowledged",),
    "resolved": ("resolved",),
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _apply_transition(fn: Callable[[int, str], bool], alert_id: int) -> None:
    """Geçiş metodunu çağırır; sonuca göre kullanıcıyı bilgilendirir (spec § 9)."""
    try:
        ok = fn(alert_id, _now_iso())
    except OperationalError as e:
        logger.error("Uyarı durumu yazılamadı: {}", e)
        st.error("Uyarı durumu güncellenemedi (DB hatası).")
        return
    if not ok:
        st.info("Uyarı durumu değişmiş olabilir — listeyi yenileyin.")


@st.experimental_fragment(run_every="5s")
def _render_alerts(repository: TelemetryRepository) -> None:
    """Filo geneli uyarıları durum kolonu + filtre + ack/resolve yönetimiyle gösterir (spec § 8).

    Gözlem modu: yalnız uyarı DURUMU yazılır (telemetri değil, cihaz komutu değil). anomalies
    tablosu yoksa bilgilendirir; çökmez (spec § 7/§ 9).
    """
    st.subheader("🚨 Uyarılar")
    choice = st.selectbox("Durum filtresi", list(_STATUS_FILTERS.keys()), index=0, key="alert_filter")
    statuses = _STATUS_FILTERS[choice or "Açık"]
    try:
        alerts = repository.fetch_alerts(statuses, limit=50)
    except OperationalError as e:
        logger.info("anomalies tablosu henüz yok: {}", e)
        st.info("Henüz anomali yok — detector servisi (`python -m detectors`) çalıştı mı?")
        return
    if not alerts:
        st.caption("Bu filtrede uyarı yok.")
        return
    st.dataframe(alerts_to_frame(alerts), use_container_width=True, hide_index=True)

    open_alerts = [a for a in alerts if a.status != RESOLVED]
    if not open_alerts:
        return
    options = {f"#{a.id} {a.device_id} · {a.rule_name} ({a.status})": a for a in open_alerts}
    label = st.selectbox("Uyarı yönet", list(options.keys()), key="alert_manage")
    selected = options.get(label) if label else None
    if selected is None:
        return
    cols = st.columns(2)
    if can_transition(selected.status, ACKNOWLEDGED) and cols[0].button("Gör (ack)", key="ack_btn"):
        _apply_transition(repository.acknowledge_alert, selected.id)
    if can_transition(selected.status, RESOLVED) and cols[1].button("Çöz (resolve)", key="resolve_btn"):
        _apply_transition(repository.resolve_alert, selected.id)
```

- [ ] **Step 6: Tüm dashboard + transform testleri + headless boot smoke**

Run: `.venv/bin/python -m pytest tests/unit/dashboard -v`
Expected: PASS.
Headless import/boot smoke (app.py import hatası vermesin):
Run: `PYTHONPATH=src .venv/bin/python -c "import dashboard.app; print('import OK')"`
Expected: `import OK` (Streamlit context uyarıları olabilir; ImportError OLMAMALI).

- [ ] **Step 7: mypy + ruff + commit**

```bash
.venv/bin/python -m mypy src/dashboard src/alerts tests/unit/dashboard
ruff check src/dashboard tests/unit/dashboard
git add src/dashboard/transform.py src/dashboard/app.py tests/unit/dashboard/test_transform.py
git commit -m "feat(dashboard): uyarı durum kolonu + filtre + ack/resolve yönetimi (Faz 7 Iter 7.1)"
```

---

### Task 6: İterasyon kapanış doğrulaması (controller)

Bu task subagent'a verilmez — controller (ana oturum) yürütür. Faz 4/5 kapanış deseni.

- [ ] **Step 1: Tam test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: tüm testler PASS (293 + Task1 1 + Task2 9 + Task3 4 + Task4 2 + Task5 2 ≈ 311; smoke skipped 1). Kesin sayı yürütmede doğrulanır.

- [ ] **Step 2: mypy strict (alerts dahil)**

Run: `.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/alerts src/dashboard tests/unit tests/integration tests/scenarios`
Expected: `Success: no issues found`.

- [ ] **Step 3: ruff**

Run: `ruff check src/simulator src/ingestion src/storage src/detectors src/alerts src/dashboard tests/unit tests/integration tests/scenarios`
Expected: `All checks passed!`

- [ ] **Step 4: Canlı uçtan-uca smoke**

Gerçek `detectors.service.run()` (reduced config) + seeded DB ile auto-resolve doğrula (Faz 5 smoke deseni):
1. Smoke DB seed: device_stat'a önce eşik-üstü `motor_temperature` (95°C) → bir poll turu → `anomalies` tek `active` satır. Sonra değeri 25°C'ye düşür → bir poll daha → satır `resolved` (resolved_at dolu).
2. Dashboard tarafı (opsiyonel manuel): `streamlit run src/dashboard/app.py` → "Gör (ack)" / "Çöz (resolve)" butonları durum değiştirir; filtre çalışır; gözlem modu (telemetri yazılmaz).
3. `sqlite3 <db> "SELECT device_id, status, resolved_at FROM anomalies"` ile auto-resolve doğrula.
Sonucu kapanış notuna yaz (memory dersi: canlı smoke şart).

- [ ] **Step 5: Dokümanları güncelle (controller)**

- `CLAUDE.md` → "Mevcut Faz" + Faz 7 closure özeti (yaşam döngüsü + auto-resolve + dashboard yönetimi + ML'in atlandığı kararı).
- `docs/ROADMAP.md` → Faz 7 kabul kriterleri (1 zaten, 2 bu iterasyon, 3 dürüst çerçeve) + **Faz 6 (ML) ertelendi/stretch'e taşındı** kararı.
- `docs/ARCHITECTURE.md` → § 5 Alert Katmanı: yaşam döngüsü `anomalies` tablosunda (ayrı süreç değil), gözlem-modu uyarı-durumu istisnası.
- Memory `project_active_phase.md` → Faz 7 Iter 7.1 DONE, alert runtime contract, ML atlandı.

- [ ] **Step 6: Final whole-iteration review + closure commit**

Faz 4/5 deseni: tüm iterasyon diff'ine son review, sonra `docs(faz7): Iter 7.1 closure ...` commit. Push **proaktif yapılmaz** — kullanıcı onayı alınır.

---

## Self-Review (yazım sonrası, spec karşılaştırması)

**Spec coverage:**
- § 5 veri modeli (migration 003 + schema kolonları + status index) → Task 1 ✅
- § 6 yaşam döngüsü (lifecycle saf modül + auto-resolve) → Task 2 (lifecycle) + Task 4 (auto-resolve) ✅
- § 7 repository API (acknowledge/resolve/resolve_open/fetch_alerts + WHERE guard'lar) → Task 3 ✅
- § 8 dashboard (alerts_to_frame durum kolonu + filtre + ack/resolve butonları + statuses tuple) → Task 5 ✅
- § 9 hata yönetimi (geçersiz geçiş → False → info; OperationalError → error; gözlem modu) → Task 3 (rowcount→bool) + Task 5 (`_apply_transition`) ✅
- § 10 test stratejisi (lifecycle birim, repository integration, detector auto-resolve, transform birim, coverage, canlı smoke) → Task 2/3/4/5 + Task 6 ✅
- § 11 kabul kriterleri: (1) fused zaten var [regresyon suite'te], (2) dashboard yönetimi [Task 5], (3) dürüst çerçeve [closure notu] ✅
- § 2.3/§ 9 eskalasyon davranışı değişmez → Task 4 Step 4 `test_detect_once_escalation_writes_new_row` regresyonu ✅

**Placeholder taraması:** Yok — her kod adımı tam içerik, her komut beklenen çıktıyla.

**Type/isim tutarlılığı:**
- `Alert` alanları: Task 2 (models.py tanımı) ↔ Task 3 (`_row_to_alert`) ↔ Task 5 (transform + app) tutarlı (14 alan).
- `can_transition(current, target) -> bool`, sabitler `ACTIVE/ACKNOWLEDGED/RESOLVED`: Task 2 tanımı ↔ Task 3 (repository import) ↔ Task 5 (app import) tutarlı.
- Repository imzaları: `acknowledge_alert(id, at)->bool`, `resolve_alert(id, at)->bool`, `resolve_open_alerts(device, at)->int`, `fetch_alerts(statuses|None, limit)->list[Alert]` — Task 3 tanımı ↔ Task 4 (`resolve_open_alerts` çağrısı) ↔ Task 5 (`acknowledge_alert`/`resolve_alert`/`fetch_alerts` çağrıları) tutarlı.
- `alerts_to_frame(list[Alert])` + 8-kolon `durum` dahil: Task 5 tanımı ↔ test tutarlı.
- `_detect_once` re-arm guard `device_id in active` → `resolve_open_alerts`: Task 4 ↔ spec § 6 tutarlı.

**Bağımlılık döngüsü kontrolü:** `alerts` saf (dış bağımlılık yok) ← `storage.repository` (alerts.models + alerts.lifecycle) ← `detectors.service` / `dashboard`. Döngü yok.

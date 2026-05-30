# Faz 4 — Iterasyon 4.1: Walking Skeleton (Detector arayüzü + Anomali persistence + 1 kural + servis) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Detector` ABC + `Anomaly` dataclass, `anomalies` tablosu (migration 002) + repository yazma/okuma, ilk kural (`MotorTemperatureHigh`), ve standalone polling servisi (`python -m detectors`) — bir cihazın motor sıcaklığı eşiği aşınca anomali DB'ye yazılır.

**Architecture:** Yeni `src/detectors/` paketi. `base.py` saf veri kontratı (pandas + abc, başka import yok). `storage/repository.py` anomalies yazma/okuma kazanır (telemetry'deki `IngestedReading` deseninin aynısı — repository `detectors.base.Anomaly`'yi import eder, döngü yok çünkü `base.py` storage'a bağımlı değil). `service.py` ingestion `run()` desenine paralel poll loop: periyodik `fetch_window` → uzun-format pencere kur → her aktif dedektör `detect()` → dedup → `insert_anomaly`. Gözlem modu: yalnız `telemetry` okur, yalnız `anomalies` yazar.

**Tech Stack:** Python 3.11, pandas, SQLAlchemy 2.0 Core, loguru, pytest. Yeni bağımlılık YOK.

---

## Spec Hizalama Notları (uygulamadan önce oku)

Bu plan `docs/specs/2026-05-30-faz4-rule-detector-design.md` (tek hakem) Iter 4.1 maddesini uygular. İki küçük netleştirme:

1. **Pencere şemasına `device_id` kolonu eklendi.** Spec § 5 pencereyi `[timestamp, sensor, state, value]` olarak listeler, ama `Anomaly.device_id` zorunlu ve `detect(window)` imzası sabit (window dışında parametre yok). `fetch_window`'un döndürdüğü `IngestedReading` zaten `device_id` taşıdığından, pencere `[device_id, timestamp, sensor, state, value]` uzun-format olarak kurulur; kural `device_id`'yi pencereden okur. **Spec § 5 kolon listesi bu plana göre güncellenmelidir** (controller closure adımı). Bu, spec'in niyetini (tek-cihaz penceresi) bozmaz, yalnız cihaz kimliğini taşır.

2. **`config/detectors.yaml` Iter 4.2'ye ait.** Walking skeleton'da kural eşiği (`critical_threshold_c`) servise constructor ile (dependency injection — CLAUDE.md) verilir; servis `run()` literal default kullanır. Iter 4.2 bunu `detectors.yaml`'dan okuyup simülatör çıktısına kalibre eder. `motor_temperature_high` universal eşik kuralıdır (DOMAIN Senaryo F), simülatör F üretmez → yalnız birim test (sentetik pencere) ile doğrulanır.

**Coverage istisnası:** `service.py` `run()` poll loop'u (sonsuz döngü + signal) ingestion `run()` gibi coverage'tan muaf tutulabilir (`# pragma: no cover`). Saf yardımcı `build_window` ve kural/`base`/repository tam test edilir. `detectors` paketi hedef ≥%85.

---

## Dosya Yapısı

**Oluşturulacak:**
- `src/detectors/__init__.py` — boş paket marker
- `src/detectors/base.py` — `Anomaly` frozen dataclass + `Detector` ABC
- `src/detectors/service.py` — `build_window` saf helper + `run()` poll loop + `SENSORS` sabiti
- `src/detectors/__main__.py` — `python -m detectors` entry (ince)
- `src/detectors/rules/__init__.py` — `RULE_REGISTRY`
- `src/detectors/rules/motor_temperature_high.py` — `MotorTemperatureHigh` kuralı
- `src/storage/migrations/002_anomalies.sql` — anomalies tablo + index
- `tests/unit/detectors/__init__.py`
- `tests/unit/detectors/test_base.py` — Anomaly + Detector ABC
- `tests/unit/detectors/test_motor_temperature_high.py` — kural birim testi
- `tests/unit/detectors/test_service_build_window.py` — build_window saf helper testi
- `tests/unit/test_storage_anomaly_repository.py` — insert_anomaly / fetch_recent_anomalies
- `tests/integration/test_detector_persistence.py` — tmp DB seed → build_window + detect → insert → fetch

**Değiştirilecek:**
- `pyproject.toml:18` — `packages.find.include`'a `"detectors*"` ekle; mypy/ruff yorumları için bir şey gerekmez ama test komutu CLAUDE.md'de güncellenecek (controller).
- `src/storage/repository.py` — `insert_anomaly`, `fetch_recent_anomalies`, `_anomaly_to_dict`, `_row_to_anomaly` ekle.

**Test/lint komutu (her task sonunda):**
```bash
pytest -q
mypy src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios
```

---

## Task 1: detectors paketi + Anomaly dataclass + Detector ABC

**Files:**
- Create: `src/detectors/__init__.py`
- Create: `src/detectors/base.py`
- Create: `tests/unit/detectors/__init__.py`
- Test: `tests/unit/detectors/test_base.py`
- Modify: `pyproject.toml:18`

- [ ] **Step 1: pyproject paket keşfine detectors ekle**

`pyproject.toml` içinde `include` satırını güncelle:

```toml
include = ["simulator*", "ingestion*", "storage*", "dashboard*", "detectors*"]
```

- [ ] **Step 2: Boş paket marker'ları oluştur**

`src/detectors/__init__.py`:

```python
"""Detector katmanı: kural tabanlı anomali tespiti (Faz 4)."""
```

`tests/unit/detectors/__init__.py`:

```python
```

(boş dosya — pytest paketi)

- [ ] **Step 3: Failing test yaz** — `tests/unit/detectors/test_base.py`

```python
"""detectors.base: Anomaly dataclass + Detector ABC kontratı (Faz 4 Iter 4.1, spec § 5)."""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from detectors.base import Anomaly, Detector


def _anomaly(**overrides: object) -> Anomaly:
    base: dict[str, object] = dict(
        device_id="device_001",
        rule_name="motor_temperature_high",
        sensor="motor_temperature",
        severity="critical",
        score=0.9,
        window_start="2026-05-30T00:00:00.000Z",
        window_end="2026-05-30T00:01:00.000Z",
        value=92.0,
        description="motor_temperature 92.0°C eşik 80.0°C üstünde",
    )
    base.update(overrides)
    return Anomaly(**base)  # type: ignore[arg-type]


def test_anomaly_holds_all_fields() -> None:
    """Anomaly tüm spec § 5 alanlarını taşır."""
    a = _anomaly()
    assert a.device_id == "device_001"
    assert a.rule_name == "motor_temperature_high"
    assert a.sensor == "motor_temperature"
    assert a.severity == "critical"
    assert a.score == 0.9
    assert a.value == 92.0


def test_anomaly_is_frozen() -> None:
    """Anomaly immutable (frozen) — yazıldıktan sonra değişmez."""
    a = _anomaly()
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.score = 0.1  # type: ignore[misc]


def test_detector_cannot_be_instantiated_directly() -> None:
    """Detector ABC; abstract metotlar implemente edilmeden örneklenemez."""
    with pytest.raises(TypeError):
        Detector()  # type: ignore[abstract]


def test_detector_subclass_contract() -> None:
    """Somut alt sınıf name property + detect(window) sağlar."""

    class _Noop(Detector):
        @property
        def name(self) -> str:
            return "noop"

        def detect(self, window: pd.DataFrame) -> list[Anomaly]:
            return []

    det = _Noop()
    assert det.name == "noop"
    assert det.detect(pd.DataFrame()) == []
```

- [ ] **Step 4: Testi çalıştır, FAIL gör**

Run: `pytest tests/unit/detectors/test_base.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.base'`

- [ ] **Step 5: `src/detectors/base.py` yaz**

```python
"""Anomaly veri kontratı + Detector ABC (Faz 4 Iter 4.1, spec § 5).

Bu modül SAF kontrattır: yalnız pandas + dataclasses + abc import eder; storage,
ingestion veya servis katmanına bağımlı DEĞİLDİR (repository bunu import eder —
ters yönde döngü olmasın diye).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Anomaly:
    """Bir kuralın tetiklediği tek anomali (spec § 5).

    Attributes:
        device_id: Anomalinin ait olduğu cihaz.
        rule_name: Tetikleyen kuralın adı (örn. "motor_temperature_high").
        sensor: İlgili sensör adı.
        severity: "info" / "warning" / "critical" (kural/config-driven).
        score: 0-1 normalize şiddet skoru (fusion için, Iter 4.3).
        window_start: Pencere başı ISO 8601 ms (YYYY-MM-DDTHH:MM:SS.sssZ).
        window_end: Pencere sonu / tespit anı ISO 8601 ms.
        value: Tetikleyen değer (örn. tepe sıcaklık).
        description: İnsan-okur açıklama.
    """

    device_id: str
    rule_name: str
    sensor: str
    severity: str
    score: float
    window_start: str
    window_end: str
    value: float
    description: str


class Detector(ABC):
    """Anomali dedektörü kontratı (ARCHITECTURE.md § 4).

    Her dedektör tek-cihaz penceresini alır ve sıfır veya daha çok Anomaly döndürür.
    Pencere uzun-formattır; kolonlar: [device_id, timestamp, sensor, state, value].
    Kural ilgili sensör(ler)i `sensor` kolonundan filtreler.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Kuralın benzersiz adı (registry anahtarı + Anomaly.rule_name)."""

    @abstractmethod
    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        """Pencerede anomali ara.

        Args:
            window: Tek cihazın son N saniyelik okumaları; uzun-format
                [device_id, timestamp, sensor, state, value] kolonları.

        Returns:
            Tetiklenen Anomaly listesi (tetikleme yoksa boş liste).
        """
```

- [ ] **Step 6: Testi çalıştır, PASS gör**

Run: `pytest tests/unit/detectors/test_base.py -q`
Expected: PASS (4 passed)

- [ ] **Step 7: mypy + ruff (yeni dosyalar)**

Run: `mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors`
Expected: temiz (hata yok)

- [ ] **Step 8: Commit**

```bash
git add src/detectors/__init__.py src/detectors/base.py tests/unit/detectors/__init__.py tests/unit/detectors/test_base.py pyproject.toml
git commit -m "feat(detectors): Anomaly dataclass + Detector ABC (Faz 4 Iter 4.1)"
```

---

## Task 2: anomalies tablosu (migration 002) + repository yazma/okuma

**Files:**
- Create: `src/storage/migrations/002_anomalies.sql`
- Modify: `src/storage/repository.py`
- Test: `tests/unit/test_storage_anomaly_repository.py`

- [ ] **Step 1: Migration dosyası oluştur** — `src/storage/migrations/002_anomalies.sql`

```sql
-- Iter 4.1 anomalies tablosu: kural dedektörlerinin yazdığı anomaliler (spec § 5).
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    sensor TEXT NOT NULL,
    severity TEXT NOT NULL,
    score REAL NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    value REAL NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anomalies_device_created
    ON anomalies (device_id, created_at);
```

- [ ] **Step 2: Failing test yaz** — `tests/unit/test_storage_anomaly_repository.py`

```python
"""storage.repository anomalies yazma/okuma (Faz 4 Iter 4.1, spec § 5)."""
from __future__ import annotations

from sqlalchemy import Engine, text

from detectors.base import Anomaly
from storage.repository import TelemetryRepository


def _anomaly(
    *,
    device_id: str = "device_001",
    rule_name: str = "motor_temperature_high",
    score: float = 0.9,
    value: float = 92.0,
    window_end: str = "2026-05-30T00:01:00.000Z",
) -> Anomaly:
    return Anomaly(
        device_id=device_id,
        rule_name=rule_name,
        sensor="motor_temperature",
        severity="critical",
        score=score,
        window_start="2026-05-30T00:00:00.000Z",
        window_end=window_end,
        value=value,
        description="test anomali",
    )


def test_insert_anomaly_then_fetch_roundtrip(migrated_engine: Engine) -> None:
    """insert_anomaly sonrası fetch_recent_anomalies aynı alanları döndürür."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anomaly(value=92.0), created_at="2026-05-30T00:01:00.500Z")

    rows = repo.fetch_recent_anomalies(limit=10)
    assert len(rows) == 1
    assert rows[0].device_id == "device_001"
    assert rows[0].rule_name == "motor_temperature_high"
    assert rows[0].sensor == "motor_temperature"
    assert rows[0].severity == "critical"
    assert rows[0].value == 92.0
    assert rows[0].score == 0.9


def test_fetch_recent_anomalies_orders_by_created_desc_and_limits(
    migrated_engine: Engine,
) -> None:
    """fetch_recent_anomalies created_at DESC sıralar ve limit uygular."""
    repo = TelemetryRepository(migrated_engine)
    for i in range(5):
        repo.insert_anomaly(
            _anomaly(value=float(i)),
            created_at=f"2026-05-30T00:0{i}:00.000Z",
        )

    rows = repo.fetch_recent_anomalies(limit=3)
    assert [r.value for r in rows] == [4.0, 3.0, 2.0]  # en yeni created_at 3 tanesi


def test_fetch_recent_anomalies_empty(migrated_engine: Engine) -> None:
    """Boş tablo → boş liste."""
    repo = TelemetryRepository(migrated_engine)
    assert repo.fetch_recent_anomalies(limit=10) == []


def test_anomalies_table_has_device_created_index(migrated_engine: Engine) -> None:
    """002 migration index'i oluşturuldu (sqlite_master ile doğrula)."""
    with migrated_engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index'")
            ).all()
        }
    assert "idx_anomalies_device_created" in names
```

- [ ] **Step 3: Testi çalıştır, FAIL gör**

Run: `pytest tests/unit/test_storage_anomaly_repository.py -q`
Expected: FAIL — `AttributeError: 'TelemetryRepository' object has no attribute 'insert_anomaly'`

- [ ] **Step 4: repository.py'ye anomalies metotlarını ekle**

`src/storage/repository.py` — import bölümüne ekle (mevcut `from storage.schema import telemetry` satırının altına):

```python
from detectors.base import Anomaly
from storage.schema import anomalies, telemetry
```

> NOT: `storage.schema`'da `anomalies` Table tanımı henüz yok — bu adımda ekleyeceğiz (Step 5). Şimdilik repository metotlarını Core `text()` yerine `anomalies` Table ile yaz (telemetry deseniyle tutarlı).

`TelemetryRepository` sınıfının içine, `_row_to_reading` staticmethod'unun altına ekle:

```python
    @staticmethod
    def _anomaly_to_dict(anomaly: Anomaly, created_at: str) -> dict[str, object]:
        """Anomaly + created_at'i anomalies kolon dict'ine çevirir."""
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
        }

    @staticmethod
    def _row_to_anomaly(row: Row[Any]) -> Anomaly:
        """SQLAlchemy Row'u Anomaly'e çevirir (id + created_at dropped)."""
        return Anomaly(
            device_id=row.device_id,
            rule_name=row.rule_name,
            sensor=row.sensor,
            severity=row.severity,
            score=row.score,
            window_start=row.window_start,
            window_end=row.window_end,
            value=row.value,
            description=row.description,
        )
```

Ve `fetch_window`'un altına (sınıf sonu) iki public metot ekle:

```python
    def insert_anomaly(self, anomaly: Anomaly, created_at: str) -> None:
        """Tek bir Anomaly'i anomalies tablosuna yazar.

        Args:
            anomaly: Bir kuralın tetiklediği anomali.
            created_at: Kalıcılık zamanı ISO 8601 ms (çağıran kendi saatinden verir —
                test edilebilirlik için DI; telemetry insert deseniyle tutarlı).

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        with self._engine.begin() as conn:
            conn.execute(
                anomalies.insert().values(**self._anomaly_to_dict(anomaly, created_at))
            )

    def fetch_recent_anomalies(self, limit: int) -> list[Anomaly]:
        """En yeni `limit` anomaliyi created_at DESC döndürür (dashboard Iter 4.3 + doğrulama).

        Args:
            limit: Maksimum satır sayısı.

        Returns:
            created_at DESC sıralı Anomaly listesi (id + created_at alanları dropped).

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        stmt = (
            select(anomalies)
            .order_by(anomalies.c.created_at.desc())
            .limit(limit)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_anomaly(row) for row in rows]
```

- [ ] **Step 5: `storage/schema.py`'ye anomalies Table tanımını ekle**

`src/storage/schema.py` dosyasının sonuna ekle. Mevcut dosya stilini birebir izle: `metadata` nesnesi var, `REAL` (Float değil) kullanılır, `Index` Table dışında ayrı tanımlanır. Import satırı zaten `REAL, Column, Index, Integer, MetaData, Table, Text` içerir — **yeni import gerekmez**.

```python
anomalies = Table(
    "anomalies",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("device_id", Text, nullable=False),
    Column("rule_name", Text, nullable=False),
    Column("sensor", Text, nullable=False),
    Column("severity", Text, nullable=False),
    Column("score", REAL, nullable=False),
    Column("window_start", Text, nullable=False),
    Column("window_end", Text, nullable=False),
    Column("value", REAL, nullable=False),
    Column("description", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

# Dashboard (Iter 4.3) + doğrulama "son anomaliler" sorgular (spec § 5).
idx_anomalies_device_created = Index(
    "idx_anomalies_device_created",
    anomalies.c.device_id,
    anomalies.c.created_at,
)
```

> NOT: `schema.py` DDL ÇALIŞTIRMAZ (modül docstring'i: "yalnızca insert/select expression builder"). Bu Table runtime DDL kaynağı DEĞİL — DDL `migrations/002_anomalies.sql`'dedir. Table yalnız repository'nin tip-güvenli sorgu kurması için. `migrated_engine` fixture'ı 002 migration'ı çalıştırdığından repository testleri Table ↔ SQL DDL tutarlılığını implicit doğrular (telemetry deseni).

- [ ] **Step 6: Testi çalıştır, PASS gör**

Run: `pytest tests/unit/test_storage_anomaly_repository.py -q`
Expected: PASS (4 passed)

- [ ] **Step 7: Mevcut storage testleri hâlâ yeşil mi**

Run: `pytest tests/unit/test_storage_repository.py tests/unit/test_storage_schema.py tests/unit/test_storage_migrator.py -q`
Expected: tümü PASS (yeni Table + migration mevcut testleri bozmadı)

- [ ] **Step 8: mypy + ruff**

Run: `mypy src/storage tests/unit/test_storage_anomaly_repository.py && ruff check src/storage tests/unit/test_storage_anomaly_repository.py`
Expected: temiz

- [ ] **Step 9: Commit**

```bash
git add src/storage/migrations/002_anomalies.sql src/storage/schema.py src/storage/repository.py tests/unit/test_storage_anomaly_repository.py
git commit -m "feat(storage): anomalies tablosu (migration 002) + insert/fetch_recent_anomalies (Faz 4 Iter 4.1)"
```

---

## Task 3: İlk kural — MotorTemperatureHigh + RULE_REGISTRY

**Files:**
- Create: `src/detectors/rules/__init__.py`
- Create: `src/detectors/rules/motor_temperature_high.py`
- Test: `tests/unit/detectors/test_motor_temperature_high.py`

- [ ] **Step 1: Failing test yaz** — `tests/unit/detectors/test_motor_temperature_high.py`

```python
"""MotorTemperatureHigh kuralı birim testi (Faz 4 Iter 4.1, spec § 6 — F universal)."""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly
from detectors.rules.motor_temperature_high import MotorTemperatureHigh


def _window(values: list[float], sensor: str = "motor_temperature") -> pd.DataFrame:
    """Tek-cihaz uzun-format pencere kurar (device_id, timestamp, sensor, state, value)."""
    return pd.DataFrame(
        {
            "device_id": ["device_001"] * len(values),
            "timestamp": [f"2026-05-30T00:00:{i:02d}.000Z" for i in range(len(values))],
            "sensor": [sensor] * len(values),
            "state": ["holding"] * len(values),
            "value": values,
        }
    )


def test_name_is_rule_key() -> None:
    """name property registry anahtarıyla aynı."""
    assert MotorTemperatureHigh(critical_threshold_c=80.0).name == "motor_temperature_high"


def test_triggers_when_peak_exceeds_threshold() -> None:
    """Tepe sıcaklık eşiği aşınca tek Anomaly döner; alanları doğru."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    window = _window([70.0, 85.0, 92.0, 60.0])

    anomalies = rule.detect(window)

    assert len(anomalies) == 1
    a = anomalies[0]
    assert isinstance(a, Anomaly)
    assert a.device_id == "device_001"
    assert a.rule_name == "motor_temperature_high"
    assert a.sensor == "motor_temperature"
    assert a.severity == "critical"
    assert a.value == 92.0  # tepe değer
    assert a.window_start == "2026-05-30T00:00:00.000Z"
    assert a.window_end == "2026-05-30T00:00:03.000Z"
    assert 0.0 <= a.score <= 1.0


def test_no_trigger_when_below_threshold() -> None:
    """Tüm değerler eşik altındaysa boş liste."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    assert rule.detect(_window([60.0, 70.0, 79.9])) == []


def test_boundary_equal_threshold_does_not_trigger() -> None:
    """Eşiğe eşit değer tetiklemez (strict >)."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    assert rule.detect(_window([80.0, 80.0])) == []


def test_ignores_other_sensors() -> None:
    """Yalnız motor_temperature satırlarına bakar; başka sensör eşiği geçse bile yok sayar."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    window = _window([200.0, 300.0], sensor="motor_current")
    assert rule.detect(window) == []


def test_empty_window_returns_empty() -> None:
    """Boş pencere → boş liste (KeyError yok)."""
    rule = MotorTemperatureHigh(critical_threshold_c=80.0)
    empty = pd.DataFrame(columns=["device_id", "timestamp", "sensor", "state", "value"])
    assert rule.detect(empty) == []
```

- [ ] **Step 2: Testi çalıştır, FAIL gör**

Run: `pytest tests/unit/detectors/test_motor_temperature_high.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.rules'`

- [ ] **Step 3: Kural implementasyonu** — `src/detectors/rules/motor_temperature_high.py`

```python
"""MotorTemperatureHigh: motor sıcaklığı kritik eşiği aşınca anomali (spec § 6).

Universal eşik kuralı (DOMAIN Senaryo F — Sıcaklık Aşımı). Simülatör F üretmediğinden
yalnız birim test (sentetik pencere) ile doğrulanır. Eşik constructor ile enjekte edilir
(DI); Iter 4.2 bunu config'ten okuyup kalibre eder.
"""
from __future__ import annotations

import pandas as pd

from detectors.base import Anomaly, Detector

SENSOR = "motor_temperature"


class MotorTemperatureHigh(Detector):
    """Pencere içindeki tepe motor sıcaklığı `critical_threshold_c`'yi (strict) aşarsa tetikler."""

    def __init__(self, critical_threshold_c: float) -> None:
        """Args: critical_threshold_c — kritik sıcaklık eşiği (°C). value > eşik → anomali."""
        self._threshold = critical_threshold_c

    @property
    def name(self) -> str:
        return "motor_temperature_high"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        """motor_temperature satırlarında tepe değer eşiği aşarsa tek Anomaly döndür."""
        if window.empty:
            return []
        sub = window[window["sensor"] == SENSOR]
        if sub.empty:
            return []

        peak = float(sub["value"].max())
        if peak <= self._threshold:
            return []

        device_id = str(sub["device_id"].iloc[0])
        window_start = str(sub["timestamp"].iloc[0])
        window_end = str(sub["timestamp"].iloc[-1])
        # Skor: eşik üstü aşımın eşiğe oranı, [0, 1]'e clamp (basit normalize, Iter 4.3 fusion).
        score = min(1.0, (peak - self._threshold) / self._threshold)
        description = (
            f"motor_temperature {peak:.1f}°C kritik eşik {self._threshold:.1f}°C üstünde"
        )
        return [
            Anomaly(
                device_id=device_id,
                rule_name=self.name,
                sensor=SENSOR,
                severity="critical",
                score=score,
                window_start=window_start,
                window_end=window_end,
                value=peak,
                description=description,
            )
        ]
```

- [ ] **Step 4: RULE_REGISTRY** — `src/detectors/rules/__init__.py`

```python
"""Kural registry: ad → Detector sınıfı (Faz 4 Iter 4.1; tam config-driven aktivasyon Iter 4.2)."""
from __future__ import annotations

from detectors.base import Detector
from detectors.rules.motor_temperature_high import MotorTemperatureHigh

RULE_REGISTRY: dict[str, type[Detector]] = {
    "motor_temperature_high": MotorTemperatureHigh,
}
```

- [ ] **Step 5: Testi çalıştır, PASS gör**

Run: `pytest tests/unit/detectors/test_motor_temperature_high.py -q`
Expected: PASS (6 passed)

- [ ] **Step 6: mypy + ruff**

Run: `mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors`
Expected: temiz

- [ ] **Step 7: Commit**

```bash
git add src/detectors/rules/__init__.py src/detectors/rules/motor_temperature_high.py tests/unit/detectors/test_motor_temperature_high.py
git commit -m "feat(detectors): MotorTemperatureHigh kuralı + RULE_REGISTRY (Faz 4 Iter 4.1)"
```

---

## Task 4: service.py — build_window saf helper + poll loop + __main__

**Files:**
- Create: `src/detectors/service.py`
- Create: `src/detectors/__main__.py`
- Test: `tests/unit/detectors/test_service_build_window.py`

- [ ] **Step 1: Failing test yaz** — `tests/unit/detectors/test_service_build_window.py`

```python
"""service.build_window saf helper testi (Faz 4 Iter 4.1, spec § 7)."""
from __future__ import annotations

from sqlalchemy import Engine

from detectors.service import SENSORS, build_window
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository


def _reading(sensor: str, ts: str, value: float, device: str = "device_001") -> IngestedReading:
    return IngestedReading(
        device_id=device, sensor=sensor, timestamp=ts, state="holding", value=value, unit="x"
    )


def test_build_window_long_format_columns(migrated_engine: Engine) -> None:
    """Pencere [device_id, timestamp, sensor, state, value] kolonlarıyla kurulur."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))
    repo.insert(_reading("motor_current", "2026-05-30T00:00:00.000Z", 0.5))

    frame = build_window(repo, "device_001", SENSORS, since=None)

    assert list(frame.columns) == ["device_id", "timestamp", "sensor", "state", "value"]
    assert set(frame["sensor"]) == {"motor_temperature", "motor_current"}
    assert len(frame) == 2


def test_build_window_filters_by_device(migrated_engine: Engine) -> None:
    """Yalnız istenen cihazın satırları gelir."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0, device="device_001"))
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 99.0, device="device_002"))

    frame = build_window(repo, "device_001", SENSORS, since=None)
    assert list(frame["value"]) == [25.0]


def test_build_window_empty_device_returns_empty_frame(migrated_engine: Engine) -> None:
    """Veri olmayan cihaz → 0 satır ama doğru-şemalı DataFrame."""
    repo = TelemetryRepository(migrated_engine)
    frame = build_window(repo, "device_404", SENSORS, since=None)
    assert list(frame.columns) == ["device_id", "timestamp", "sensor", "state", "value"]
    assert len(frame) == 0
```

- [ ] **Step 2: Testi çalıştır, FAIL gör**

Run: `pytest tests/unit/detectors/test_service_build_window.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.service'`

- [ ] **Step 3: service.py yaz**

```python
"""Detector poll servisi: periyodik fetch_window → detect → insert_anomaly (spec § 7).

ingestion __main__.run() desenine paralel: config + engine + repository kur, SIGINT/SIGTERM
ile graceful shutdown. Gözlem modu (CLAUDE.md): yalnız telemetry okur, yalnız anomalies yazar;
hiçbir cihazı yönetmez, komut göndermez.

build_window saf + test edilebilir; run() poll loop coverage'tan muaf (ingestion deseni).
"""
from __future__ import annotations

import signal
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import FrameType

import pandas as pd
from loguru import logger
from sqlalchemy.exc import OperationalError

from detectors.base import Anomaly, Detector
from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from ingestion.config import load_ingestion_config
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository

# Pencereye dahil edilen sensörler (simülatör 6-sensör seti). Kurallar ilgilendiklerini filtreler.
SENSORS: list[str] = [
    "motor_current",
    "motor_voltage",
    "hydraulic_pressure",
    "motor_temperature",
    "mast_position",
    "vibration",
]

_WINDOW_COLUMNS = ["device_id", "timestamp", "sensor", "state", "value"]


def build_window(
    repository: TelemetryRepository,
    device_id: str,
    sensors: list[str],
    since: str | None,
) -> pd.DataFrame:
    """Bir cihaz için uzun-format pencere DataFrame'i kurar (spec § 5, § 7).

    Her sensör için fetch_window çağrılır, sonuçlar birleştirilir.

    Args:
        repository: TelemetryRepository (telemetry okuma).
        device_id: Cihaz kimliği.
        sensors: Pencereye dahil edilecek sensör adları.
        since: ISO 8601 ms cutoff veya None (tümü).

    Returns:
        [device_id, timestamp, sensor, state, value] kolonlu DataFrame
        (cihazda veri yoksa 0 satırlı ama doğru-şemalı).
    """
    records: list[dict[str, object]] = []
    for sensor in sensors:
        for r in repository.fetch_window(device_id, sensor, since):
            records.append(
                {
                    "device_id": r.device_id,
                    "timestamp": r.timestamp,
                    "sensor": r.sensor,
                    "state": r.state,
                    "value": r.value,
                }
            )
    return pd.DataFrame(records, columns=_WINDOW_COLUMNS)


def _since_cutoff(now: datetime, window_s: int) -> str:
    """now - window_s'i publisher formatında ISO ms cutoff'a çevirir (lexicographic karşılaştırma)."""
    cutoff = now - timedelta(seconds=window_s)
    return cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _detect_once(
    repository: TelemetryRepository,
    detectors: list[Detector],
    window_s: int,
    seen: set[tuple[str, str, str]],
) -> None:  # pragma: no cover
    """Tek poll turu: her cihaz × her dedektör → dedup → insert_anomaly.

    `seen`: (device_id, rule_name, window_end) in-memory dedup (spec § 5 — aynı anomali
    tekrar yazılmasın). Gelişmiş dedup Faz 5.
    """
    now = datetime.now(UTC)
    since = _since_cutoff(now, window_s)
    created_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    for device_id in repository.list_devices():
        window = build_window(repository, device_id, SENSORS, since)
        if window.empty:
            continue
        for detector in detectors:
            try:
                anomalies: list[Anomaly] = detector.detect(window)
            except (KeyError, ValueError) as e:
                logger.error("Kural '{}' hata verdi, atlandı: {}", detector.name, e)
                continue
            for anomaly in anomalies:
                key = (anomaly.device_id, anomaly.rule_name, anomaly.window_end)
                if key in seen:
                    continue
                try:
                    repository.insert_anomaly(anomaly, created_at)
                except OperationalError as e:
                    logger.error("Anomali yazılamadı (atlandı): {}", e)
                    continue
                seen.add(key)
                logger.info(
                    "Anomali: device={} rule={} value={:.2f} sev={}",
                    anomaly.device_id,
                    anomaly.rule_name,
                    anomaly.value,
                    anomaly.severity,
                )


def run(
    ingestion_config_path: Path = Path("config/ingestion.yaml"),
    poll_interval_s: float = 5.0,
    window_s: int = 60,
    motor_temp_threshold_c: float = 80.0,
) -> None:  # pragma: no cover
    """Detector servisini başlat. SIGINT/SIGTERM gelene kadar bloklar.

    db_path ingestion.yaml'dan okunur (telemetry ile aynı DB paylaşılır). Eşik + poll
    parametreleri Iter 4.1'de constructor default (DI); Iter 4.2'de detectors.yaml'a taşınır.

    Args:
        ingestion_config_path: db_path için ingestion.yaml yolu (paylaşılan DB).
        poll_interval_s: Poll periyodu (saniye).
        window_s: Her turda bakılan geri-pencere (saniye).
        motor_temp_threshold_c: MotorTemperatureHigh kritik eşiği (°C).

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: Config geçersizse.
    """
    ingestion_config = load_ingestion_config(ingestion_config_path)
    logger.remove()
    logger.add(sys.stderr, level=ingestion_config.log_level)

    engine = create_sqlite_engine(ingestion_config.db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repository = TelemetryRepository(engine)
        detectors: list[Detector] = [
            MotorTemperatureHigh(critical_threshold_c=motor_temp_threshold_c),
        ]
        seen: set[tuple[str, str, str]] = set()

        shutdown = threading.Event()

        def _on_signal(signum: int, _frame: FrameType | None) -> None:
            logger.info("Shutdown sinyali alındı: {}", signum)
            shutdown.set()

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        logger.info(
            "Detector servisi başladı: poll={}s window={}s kurallar={}",
            poll_interval_s,
            window_s,
            [d.name for d in detectors],
        )
        while not shutdown.is_set():
            try:
                _detect_once(repository, detectors, window_s, seen)
            except OperationalError as e:
                logger.error("Poll turu DB hatası (devam): {}", e)
            shutdown.wait(poll_interval_s)
    finally:
        engine.dispose()
        logger.info("Detector servisi temiz kapandı")
```

> NOT: `migrations/002_anomalies.sql` Task 2'de eklendiği için `apply_migrations` boot'ta hem telemetry (001) hem anomalies (002) tablolarını idempotent kurar.

- [ ] **Step 4: __main__.py yaz** — `src/detectors/__main__.py`

```python
"""Detector servisi entry: python -m detectors (Faz 4 Iter 4.1)."""
from __future__ import annotations

from detectors.service import run

if __name__ == "__main__":  # pragma: no cover
    run()
```

- [ ] **Step 5: Testi çalıştır, PASS gör**

Run: `pytest tests/unit/detectors/test_service_build_window.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: mypy + ruff**

Run: `mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors`
Expected: temiz

- [ ] **Step 7: Commit**

```bash
git add src/detectors/service.py src/detectors/__main__.py tests/unit/detectors/test_service_build_window.py
git commit -m "feat(detectors): poll servisi (build_window + run loop) + python -m detectors (Faz 4 Iter 4.1)"
```

---

## Task 5: Integration testi — seed → detect → persist → fetch

**Files:**
- Test: `tests/integration/test_detector_persistence.py`

- [ ] **Step 1: Failing test yaz** — `tests/integration/test_detector_persistence.py`

```python
"""Integration: telemetry seed → build_window + detect → insert_anomaly → fetch (Faz 4 Iter 4.1).

tmp file-based SQLite (gerçek 001 + 002 migration). Iter 4.1 'bitti' kriteri: bir cihazın
motor_temperature eşiği aşınca anomali DB'ye yazılır ve geri okunur.
"""
from __future__ import annotations

from pathlib import Path

from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.service import SENSORS, build_window
from ingestion.message_parser import IngestedReading
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository


def _reading(sensor: str, ts: str, value: float) -> IngestedReading:
    return IngestedReading(
        device_id="device_001", sensor=sensor, timestamp=ts, state="holding",
        value=value, unit="celsius",
    )


def test_overtemp_seed_produces_persisted_anomaly(tmp_path: Path) -> None:
    """Eşik üstü motor_temperature seed → tek tur tespit → anomalies tablosunda satır."""
    db_path = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)

        # Eşik üstü sıcaklık serisi seed et (tepe 95°C, eşik 80°C).
        for i, temp in enumerate([78.0, 88.0, 95.0]):
            repo.insert(_reading("motor_temperature", f"2026-05-30T00:00:0{i}.000Z", temp))

        # Tek tur: pencere kur → detect → persist.
        window = build_window(repo, "device_001", SENSORS, since=None)
        rule = MotorTemperatureHigh(critical_threshold_c=80.0)
        anomalies = rule.detect(window)
        assert len(anomalies) == 1
        repo.insert_anomaly(anomalies[0], created_at="2026-05-30T00:00:03.000Z")

        stored = repo.fetch_recent_anomalies(limit=10)
        assert len(stored) == 1
        assert stored[0].device_id == "device_001"
        assert stored[0].rule_name == "motor_temperature_high"
        assert stored[0].value == 95.0
    finally:
        engine.dispose()


def test_normal_temp_seed_produces_no_anomaly(tmp_path: Path) -> None:
    """Eşik altı sıcaklık → anomalies tablosu boş (FP yok)."""
    db_path = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        for i, temp in enumerate([24.0, 25.0, 26.0]):
            repo.insert(_reading("motor_temperature", f"2026-05-30T00:00:0{i}.000Z", temp))

        window = build_window(repo, "device_001", SENSORS, since=None)
        rule = MotorTemperatureHigh(critical_threshold_c=80.0)
        for anomaly in rule.detect(window):
            repo.insert_anomaly(anomaly, created_at="2026-05-30T00:00:03.000Z")

        assert repo.fetch_recent_anomalies(limit=10) == []
    finally:
        engine.dispose()
```

- [ ] **Step 2: Testi çalıştır, PASS gör**

Run: `pytest tests/integration/test_detector_persistence.py -q`
Expected: PASS (2 passed)

- [ ] **Step 3: Tam suite + mypy + ruff**

Run:
```bash
pytest -q
mypy src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage src/detectors tests/unit tests/integration tests/scenarios
```
Expected: tüm testler PASS (önceki 180 + yeni Iter 4.1 testleri; 1 smoke skipped), mypy temiz, ruff temiz.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_detector_persistence.py
git commit -m "test(detectors): integration — overtemp seed → persist → fetch (Faz 4 Iter 4.1)"
```

---

## Controller Closure (subagent task'larından SONRA — sen yaparsın)

Bu adımlar plan task'larının dışında, controller (ana oturum) tarafından yapılır:

1. **Manuel uçtan uca smoke** (gerçek Mosquitto + simulator + ingestion + detectors):
   - Terminal A: `python -m simulator` (devices.yaml.example — device_002 MechanicalWear, device_003 HydraulicLeak+ElectricalFault).
   - Terminal B: `python -m ingestion` (telemetry.db'ye yazar).
   - Terminal C: `python -m detectors --` (poll loop). NOT: motor_temperature simülatörde baseline ~25°C ısınmayla artar ama 80°C'ye **ulaşmaz** (F simüle değil). Bu yüzden manuel smoke'ta anomali ÜRETİLMESİNİ görmek için ya geçici düşük eşik (`motor_temp_threshold_c`) ile çalıştır ya da SQL ile yapay eşik-üstü satır ekle:
     ```bash
     sqlite3 data/telemetry.db "INSERT INTO telemetry (device_id,sensor,timestamp,state,value,unit) VALUES ('device_001','motor_temperature','2026-05-30T12:00:00.000Z','holding',95.0,'celsius')"
     ```
   - Doğrula: `sqlite3 data/telemetry.db "SELECT * FROM anomalies"` → satır görünür.
   - SIGINT (Ctrl-C) ile her servis temiz kapanır.
   - **Env not (CLAUDE.md):** `python -m detectors` ImportError verirse `PYTHONPATH=src python -m detectors`.
2. **Doküman güncelle:** CLAUDE.md "Mevcut Faz" → Faz 4 Iter 4.1 closure bloğu (yeni dosyalar, test sayısı, `python -m detectors` çalıştırma satırı, anomalies tablosu); test/lint komutuna `src/detectors` eklendiğini yaz.
3. **Spec § 5 güncelle:** pencere kolon listesine `device_id` ekle (bu plan Spec Hizalama Notu 1).
4. **Memory güncelle:** `project_active_phase` → Iter 4.1 DONE, Iter 4.2 next; detectors runtime contract (Anomaly/Detector/build_window/insert_anomaly/fetch_recent_anomalies/RULE_REGISTRY/SENSORS).
5. **Final whole-iteration review** (subagent-driven kapanış): spec-compliance + code-quality.
6. **Push YAPMA** — kullanıcı onayı al.

---

## Self-Review (writing-plans)

**Spec coverage (Iter 4.1 maddeleri):**
- `base.py` Anomaly + Detector ABC → Task 1 ✓
- `migrations/002_anomalies.sql` + insert_anomaly/fetch_recent_anomalies → Task 2 ✓
- İlk kural MotorTemperatureHigh (rules/) → Task 3 ✓
- Runner service.py poll loop + __main__.py + signal/graceful shutdown → Task 4 ✓
- Birim test (sentetik window → Anomaly) → Task 3 ✓; integration (tmp DB) → Task 5 ✓
- Hata yönetimi (kural exception → skip + log; OperationalError → log; boş pencere → skip) → Task 4 `_detect_once`/`run` ✓
- Dedup (in-memory seen) → Task 4 ✓

**Tip tutarlılığı:** `Anomaly` alanları Task 1'de tanımlandı; Task 2 (`_anomaly_to_dict`/`_row_to_anomaly`), Task 3 (kural), Task 5 (integration) aynı alan adlarını kullanır. `insert_anomaly(anomaly, created_at)` imzası Task 2/4/5'te tutarlı. `build_window(repo, device_id, sensors, since)` + `SENSORS` Task 4/5'te tutarlı. `detect(window) -> list[Anomaly]` ABC ile kural eşleşir.

**Placeholder taraması:** Her kod adımı tam içerik taşıyor; "TODO/TBD/uygun hata yönetimi ekle" yok. Tek dış-bağımlılık: `storage/schema.py`'nin `metadata` adı ve import stili — Step 2.5 dosyaya bakıp gerçek isme uymayı açıkça söylüyor.

# Faz 2 — Iterasyon 2.2: SQLite + Repository Pattern — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task's final verification step MUST run FULL pytest suite + mypy + ruff over src AND ALL tests dirs.

**Goal:** `python -m ingestion` çalışırken Faz 1 simulator'ın her MQTT mesajını SQLite `telemetry` tablosuna tek-tek yazar; şema yalın script-based migration ile idempotent kurulur.

**Architecture:** Yeni `src/storage/` paketi 4 dosya + 1 SQL migration: `schema.py` (SQLAlchemy Core `Table` + composite `Index` — yalnızca insert/select expression builder; DDL'i çalıştırmaz), `engine.py` (`create_sqlite_engine` factory — pragma + dizin oluşturma), `migrator.py` (`apply_migrations` saf fonksiyon + `schema_version` tablosu), `repository.py` (`TelemetryRepository` — `insert` + minimal `count`/`fetch_recent`), `migrations/001_initial.sql` (CREATE TABLE + INDEX — runtime DDL'in TEK kaynağı). Ingestion `__main__.run()` orchestration'da kalır (engine extraction Iter 2.3'e ertelendi): engine kurar → migration apply → repository kurar → handler closure `repository.insert(reading)` çağırır.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0.30 Core (ORM değil — zaten `requirements.txt`'te), paho-mqtt, loguru, pytest, mypy strict, ruff. Yeni runtime dependency YOK.

**Referans:** `docs/specs/2026-05-29-faz2-ingestion-storage-design.md` § 3 Iter 2.2 (kapsam + 6 bitti kriteri), § 5 (SQL şema + IngestedReading), § 7 (index stratejisi + pragma), § 9 (migration mekanizması), § 11 (hata yönetimi), § 12 (test stratejisi). Faz 1 input contract: `docs/specs/2026-05-18-faz1-simulator-design.md` § 7.

**Brainstorming kararları (bu oturum, spec'e uyumlu):**
1. Orchestration `__main__.py`'de kalır (engine.py extraction + `storage/engine.py` isim çakışması YAGNI; Iter 2.3'e ertelendi).
2. `TelemetryRepository(engine: Engine)` — connection_factory callable red.
3. `insert(reading: IngestedReading) -> None` — type-safe, kwargs red.
4. `apply_migrations(engine, migrations_dir) -> None` saf fonksiyon — Migrator class red.
5. `schema_version.version` INTEGER PK (dosya prefix `001_`).
6. Unit test fixture `:memory:` + `StaticPool` (connection paylaşımı); integration `tmp_path` dosya.
7. `schema.py` Core `Table` + standalone `Index` (ORM declarative red).
8. **Inline spec netleştirmeleri** (kod izlemeden önce commit edilir, aşağıda Task 0):
   - § 9 migrator literal `conn.execute(text(sql))` → çok-statement SQL dosyası için statement-split (sqlite3 driver tek statement çalıştırır; aksi halde INDEX sessizce atlanır).
   - § 12 integration "max_messages parametresi" → wired handler'ı doğrudan N sahte mesajla sürmek (run()'a parametre eklemeden); daha temiz.
   - § 11 SQLite IO error "3x retry sonra exit" tam resilience'i Iter 2.3'e (batch_writer ile); Iter 2.2'de `OperationalError` → CRITICAL + skip.
   - Repository'ye `count()` + `fetch_recent()` eklenir (bitti kriteri 2 & 3'ün gereği); `insert_batch` + geniş query API Iter 2.3'te.

---

## Önkoşul

`.venv` aktif, `pip install -e .` yapılmış, Iter 2.1 testleri (141 PASS) yeşil olmalı:

```bash
cd ~/mast-anomaly-detection
source .venv/bin/activate
pytest tests/ -q                                                              # 141 passed beklenir
mypy src/simulator src/ingestion tests/unit tests/integration tests/scenarios # Success
ruff check src/simulator src/ingestion tests/unit tests/integration tests/scenarios  # All checks passed
```

`config/ingestion.yaml.example` zaten `db_path: data/telemetry.db` içeriyor; `IngestionConfig.db_path` Iter 2.1'de forward-compat eklenmiş. `pyproject.toml` `packages.find` zaten `storage*` içeriyor. **Hiçbir config/pyproject değişikliği gerekmez.**

---

## Dosya Yapısı (Iter 2.2 sonunda)

```
src/storage/
├── __init__.py                  # YENİ: boş package marker
├── schema.py                    # YENİ: metadata + telemetry Table + Index
├── engine.py                    # YENİ: create_sqlite_engine(db_path) factory
├── migrator.py                  # YENİ: MIGRATIONS_DIR + apply_migrations + _now_iso
├── repository.py                # YENİ: TelemetryRepository (insert, count, fetch_recent)
└── migrations/
    └── 001_initial.sql          # YENİ: CREATE TABLE telemetry + CREATE INDEX

src/ingestion/__main__.py        # MODIFY: engine + migration + repository wiring;
                                 #         handler repository.insert; OperationalError handling

tests/unit/
├── conftest.py                  # MODIFY: in_memory_engine + migrated_engine fixtures ekle
├── test_storage_schema.py       # YENİ: Table/Index yapısı
├── test_storage_engine.py       # YENİ: factory dizin + pragma
├── test_storage_migrator.py     # YENİ: apply + idempotent + index
├── test_storage_repository.py   # YENİ: insert/count/fetch_recent + EXPLAIN index
└── test_ingestion_main.py       # MODIFY: handler artık repository ile insert eder

tests/integration/
└── test_ingestion_end_to_end.py # YENİ: handler + tmp_path repo, N mesaj → satır + restart append
```

**Beklenen test sayısı:** 141 → ~154 (schema 2 + engine 2 + migrator 3 + repository 4 + integration 2 = 13 yeni; main 2 modified).
**Hedef coverage:** `storage` + `ingestion` paketlerinde ≥%85.

---

## Task 0: Spec inline netleştirmeleri (4 nokta) + commit

**Files:**
- Modify: `docs/specs/2026-05-29-faz2-ingestion-storage-design.md`

Spec tek hakem; kod izlemeden önce 4 küçük netleştirme spec'e işlenir. İçerik değil, uygulama detayı netleştirmesi.

- [ ] **Step 1: § 9 migrator çok-statement notu ekle**

§ 9'daki kod bloğunun hemen altına ekle:

```markdown
**Çok-statement SQL dosyaları:** Bir `.sql` dosyası birden fazla statement
içeriyorsa (örn. `001_initial.sql` = CREATE TABLE + CREATE INDEX), `conn.execute(text(sql))`
tek statement çalıştırır (pysqlite driver davranışı) — kalan statement'lar sessizce
atlanır. Bu yüzden migrator dosyayı `;` ile statement'lara böler ve her birini ayrı
`conn.execute(text(stmt))` ile çalıştırır (DDL için string-literal `;` riski yok).
```

- [ ] **Step 2: § 12 integration test netleştirmesi**

§ 12 "Integration Test" alt başlığındaki "run main loop max_messages parametresiyle" cümlesini şununla değiştir:

```markdown
- wired message handler (`_make_message_handler(repository)`) + `tmp_path` dosya SQLite
  engine; N sahte `MQTTMessage` doğrudan handler'a fire edilir (paho/run() loop'u
  test edilmez — sinyal/thread izolasyonu unit kapsamı dışı). N mesaj sonrası SQL'de
  N satır, `timestamp` sırası korunmuş, restart'ta migration tekrar koşmaz.
```

- [ ] **Step 3: § 3 Iter 2.2 repository okuma metodu notu**

§ 3 Iter 2.2 "Kapsam" listesindeki repository maddesine ekle (mevcut "insert tek tek" satırının sonuna):

```markdown
  `TelemetryRepository` — `insert(reading)` tek tek + minimal okuma `count()` /
  `fetch_recent(device_id, sensor, limit)` (bitti kriteri 2 & 3 doğrulaması için).
  `insert_batch` + geniş query API Iter 2.3.
```

- [ ] **Step 4: Commit**

```bash
git add docs/specs/2026-05-29-faz2-ingestion-storage-design.md
git commit -m "docs(spec): Iter 2.2 inline netleştirmeler (multi-statement migration, integration test, repository read API)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: `storage/schema.py` — Core Table + Index

**Files:**
- Create: `src/storage/__init__.py`
- Create: `src/storage/schema.py`
- Test: `tests/unit/test_storage_schema.py`

SQLAlchemy Core `MetaData` + `telemetry` `Table` + composite `Index`. Bu modül DDL **çalıştırmaz** (`metadata.create_all()` çağrılmaz) — yalnızca insert/select expression builder. Runtime DDL `001_initial.sql` + migrator'ın sorumluluğu.

- [ ] **Step 1: Boş package marker oluştur**

`src/storage/__init__.py`:

```python
"""Storage paketi: SQLite şema, engine factory, migration, repository (Faz 2 Iter 2.2)."""
```

- [ ] **Step 2: Failing test yaz**

`tests/unit/test_storage_schema.py`:

```python
"""storage.schema Table + Index yapı testleri (Iter 2.2, spec § 5)."""
from __future__ import annotations


def test_telemetry_table_has_expected_columns() -> None:
    """telemetry tablosu spec § 5'teki 7 kolonu içerir, hepsi NOT NULL (id PK hariç)."""
    from storage.schema import telemetry

    assert telemetry.name == "telemetry"
    assert set(telemetry.c.keys()) == {
        "id", "device_id", "sensor", "timestamp", "state", "value", "unit"
    }
    assert telemetry.c.id.primary_key is True
    for name in ("device_id", "sensor", "timestamp", "state", "value", "unit"):
        assert telemetry.c[name].nullable is False, f"{name} NOT NULL olmalı"


def test_composite_index_defined_on_device_sensor_timestamp() -> None:
    """Composite index (device_id, sensor, timestamp) doğru ad + kolon sırasıyla tanımlı."""
    from storage.schema import telemetry

    indexes = {idx.name: idx for idx in telemetry.indexes}
    assert "idx_telemetry_device_sensor_ts" in indexes
    idx = indexes["idx_telemetry_device_sensor_ts"]
    assert [col.name for col in idx.columns] == ["device_id", "sensor", "timestamp"]
```

- [ ] **Step 3: Test'i çalıştır, FAIL gör**

Run: `pytest tests/unit/test_storage_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'storage.schema'`

- [ ] **Step 4: `schema.py` yaz**

`src/storage/schema.py`:

```python
"""SQLite telemetry şeması: SQLAlchemy Core Table + composite index (spec § 5, § 7).

Bu modül DDL ÇALIŞTIRMAZ (metadata.create_all() çağrılmaz). Yalnızca insert/select
expression builder olarak kullanılır. Runtime DDL'in tek kaynağı: migrations/001_initial.sql
(migrator.apply_migrations çalıştırır). schema.py Table ile 001_initial.sql arasındaki
tutarlılık migrated_engine fixture üzerinden çalışan repository testleriyle implicit doğrulanır.
"""
from __future__ import annotations

from sqlalchemy import REAL, Column, Index, Integer, MetaData, Table, Text

metadata = MetaData()

telemetry = Table(
    "telemetry",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("device_id", Text, nullable=False),
    Column("sensor", Text, nullable=False),
    Column("timestamp", Text, nullable=False),  # ISO 8601 ms (lexicographic sortable)
    Column("state", Text, nullable=False),
    Column("value", REAL, nullable=False),
    Column("unit", Text, nullable=False),
)

# Dedektörler (Faz 4+) "şu cihazın şu sensörünün son N örneği" sorgular (spec § 7).
idx_telemetry_device_sensor_ts = Index(
    "idx_telemetry_device_sensor_ts",
    telemetry.c.device_id,
    telemetry.c.sensor,
    telemetry.c.timestamp,
)
```

- [ ] **Step 5: Test'i çalıştır, PASS gör**

Run: `pytest tests/unit/test_storage_schema.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 143 passed, mypy Success, ruff clean

- [ ] **Step 7: Commit**

```bash
git add src/storage/__init__.py src/storage/schema.py tests/unit/test_storage_schema.py
git commit -m "feat(storage): telemetry Core Table + composite index (spec § 5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `storage/engine.py` — SQLite engine factory

**Files:**
- Create: `src/storage/engine.py`
- Test: `tests/unit/test_storage_engine.py`

`create_sqlite_engine(db_path)`: parent dizini oluşturur (data/ gitignore'da, fresh clone'da yok), SQLite engine kurar, connect event'inde WAL + synchronous=NORMAL + foreign_keys=ON pragma'ları set eder (spec § 7).

- [ ] **Step 1: Failing test yaz**

`tests/unit/test_storage_engine.py`:

```python
"""storage.engine factory testleri (Iter 2.2, spec § 7)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text


def test_create_engine_makes_parent_dir(tmp_path: Path) -> None:
    """db_path parent dizini yoksa factory oluşturur (data/ gitignore senaryosu)."""
    from storage.engine import create_sqlite_engine

    db_path = tmp_path / "nested" / "telemetry.db"
    assert not db_path.parent.exists()

    engine = create_sqlite_engine(db_path)
    try:
        assert db_path.parent.exists()
    finally:
        engine.dispose()


def test_engine_sets_wal_and_foreign_keys_pragmas(tmp_path: Path) -> None:
    """Connect event WAL journal_mode + foreign_keys=ON set eder."""
    from storage.engine import create_sqlite_engine

    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    try:
        with engine.connect() as conn:
            journal = conn.execute(text("PRAGMA journal_mode")).scalar_one()
            fk = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
        assert str(journal).lower() == "wal"
        assert int(fk) == 1
    finally:
        engine.dispose()
```

- [ ] **Step 2: Test'i çalıştır, FAIL gör**

Run: `pytest tests/unit/test_storage_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'storage.engine'`

- [ ] **Step 3: `engine.py` yaz**

`src/storage/engine.py`:

```python
"""SQLite SQLAlchemy engine factory: pragma + dizin oluşturma (spec § 7)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event


def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Her yeni connection'da WAL + synchronous=NORMAL + foreign_keys=ON (spec § 7)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_sqlite_engine(db_path: Path) -> Engine:
    """Verilen yola SQLite engine kurar; parent dizini ve pragma'ları hazırlar.

    Args:
        db_path: SQLite dosya yolu (örn. data/telemetry.db). Parent dizin yoksa oluşturulur.

    Returns:
        Pragma'ları connect event ile set edilmiş SQLAlchemy Engine.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine
```

- [ ] **Step 4: Test'i çalıştır, PASS gör**

Run: `pytest tests/unit/test_storage_engine.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 145 passed, mypy Success, ruff clean

- [ ] **Step 6: Commit**

```bash
git add src/storage/engine.py tests/unit/test_storage_engine.py
git commit -m "feat(storage): create_sqlite_engine factory (WAL + pragma + dir, spec § 7)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `migrations/001_initial.sql` + `storage/migrator.py`

**Files:**
- Create: `src/storage/migrations/001_initial.sql`
- Create: `src/storage/migrator.py`
- Modify: `tests/unit/conftest.py` (in_memory_engine + migrated_engine fixtures)
- Test: `tests/unit/test_storage_migrator.py`

Yalın script-based migration (spec § 9): `schema_version` tablosu + `NNN_*.sql` dosyalarını sırayla apply. Çok-statement SQL `;` ile bölünür (Task 0 netleştirmesi). İdempotent: uygulanmış versiyonlar atlanır.

- [ ] **Step 1: `001_initial.sql` oluştur**

`src/storage/migrations/001_initial.sql`:

```sql
-- Iter 2.2 initial schema: telemetry wide tablo + composite index (spec § 5, § 7).
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    sensor TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    state TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device_sensor_ts
    ON telemetry (device_id, sensor, timestamp);
```

- [ ] **Step 2: conftest fixtures ekle**

`tests/unit/conftest.py` — dosyanın SONUNA ekle (mevcut importlara dokunma, yeni importları üst bloğa ekle):

Üstteki import bloğuna (mevcut `import pytest` yakınına):

```python
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from storage.migrator import MIGRATIONS_DIR, apply_migrations
```

Dosya sonuna fixtures:

```python
@pytest.fixture
def in_memory_engine() -> Iterator[Engine]:
    """Tek-connection in-memory SQLite engine (StaticPool).

    :memory: connection-başına ayrı DB'dir; StaticPool tüm begin()/connect()
    blokları için TEK connection paylaşır ki tablo testler boyunca yaşasın.
    """
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def migrated_engine(in_memory_engine: Engine) -> Engine:
    """in_memory_engine + apply_migrations → telemetry tablosu hazır.

    Gerçek 001_initial.sql DDL'ini çalıştırır; repository testleri böylece
    schema.py Table ile SQL DDL tutarlılığını implicit doğrular.
    """
    apply_migrations(in_memory_engine, MIGRATIONS_DIR)
    return in_memory_engine
```

- [ ] **Step 3: Failing test yaz**

`tests/unit/test_storage_migrator.py`:

```python
"""storage.migrator apply + idempotency testleri (Iter 2.2, spec § 9)."""
from __future__ import annotations

from sqlalchemy import Engine, text


def _table_names(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).all()
    return {row[0] for row in rows}


def test_apply_creates_telemetry_and_records_version(in_memory_engine: Engine) -> None:
    """Boş db → apply → telemetry + schema_version tabloları var, version=1 kayıtlı."""
    from storage.migrator import MIGRATIONS_DIR, apply_migrations

    apply_migrations(in_memory_engine, MIGRATIONS_DIR)

    assert {"telemetry", "schema_version"} <= _table_names(in_memory_engine)
    with in_memory_engine.connect() as conn:
        versions = [r[0] for r in conn.execute(text("SELECT version FROM schema_version")).all()]
    assert versions == [1]


def test_apply_creates_composite_index(in_memory_engine: Engine) -> None:
    """001_initial.sql ikinci statement'ı (CREATE INDEX) de uygulanır (multi-statement split)."""
    from storage.migrator import MIGRATIONS_DIR, apply_migrations

    apply_migrations(in_memory_engine, MIGRATIONS_DIR)

    with in_memory_engine.connect() as conn:
        idx_rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        ).all()
    assert any(r[0] == "idx_telemetry_device_sensor_ts" for r in idx_rows)


def test_apply_is_idempotent(in_memory_engine: Engine) -> None:
    """İkinci apply no-op: schema_version satır sayısı 1 kalır (re-run güvenli)."""
    from storage.migrator import MIGRATIONS_DIR, apply_migrations

    apply_migrations(in_memory_engine, MIGRATIONS_DIR)
    apply_migrations(in_memory_engine, MIGRATIONS_DIR)

    with in_memory_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar_one()
    assert count == 1
```

- [ ] **Step 4: Test'i çalıştır, FAIL gör**

Run: `pytest tests/unit/test_storage_migrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'storage.migrator'` (conftest import da hata verir; bu beklenen, Step 5 düzeltir)

- [ ] **Step 5: `migrator.py` yaz**

`src/storage/migrator.py`:

```python
"""Yalın script-based migration: schema_version + sıralı NNN_*.sql apply (spec § 9)."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import Engine, text

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _now_iso() -> str:
    """Migration zaman damgası: ISO 8601 ms UTC."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _split_sql_statements(sql: str) -> list[str]:
    """SQL dosyasını ';' ile statement'lara böler (boşları atar).

    pysqlite driver tek execute'ta tek statement çalıştırır; çok-statement DDL
    dosyaları (CREATE TABLE + CREATE INDEX) için her statement ayrı çalıştırılmalı.
    DDL'de string-literal ';' yok, basit split güvenli.
    """
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


def apply_migrations(engine: Engine, migrations_dir: Path) -> None:
    """schema_version tablosunu kontrol eder, eksik migration'ları sırayla uygular.

    İdempotent: zaten uygulanmış versiyonlar atlanır (servis restart'ta no-op).

    Args:
        engine: SQLAlchemy Engine (SQLite).
        migrations_dir: NNN_*.sql dosyalarının bulunduğu dizin.

    Raises:
        sqlalchemy.exc.OperationalError: SQL hatalıysa (bozuk şema — çağıran erken çıkmalı).
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
        )
        applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_version")).all()}

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version in applied:
            continue
        statements = _split_sql_statements(sql_file.read_text(encoding="utf-8"))
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :t)"),
                {"v": version, "t": _now_iso()},
            )
        logger.info("Migration uygulandı: {} (version={})", sql_file.name, version)
```

- [ ] **Step 6: Test'i çalıştır, PASS gör**

Run: `pytest tests/unit/test_storage_migrator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 148 passed, mypy Success, ruff clean

- [ ] **Step 8: Commit**

```bash
git add src/storage/migrations/001_initial.sql src/storage/migrator.py tests/unit/conftest.py tests/unit/test_storage_migrator.py
git commit -m "feat(storage): apply_migrations + 001_initial.sql + test fixtures (spec § 9)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `storage/repository.py` — TelemetryRepository

**Files:**
- Create: `src/storage/repository.py`
- Test: `tests/unit/test_storage_repository.py`

`TelemetryRepository(engine)`: `insert(reading)` tek-tek + minimal `count()` + `fetch_recent(device_id, sensor, limit)`. EXPLAIN QUERY PLAN ile composite index kullanımı doğrulanır (bitti kriteri 3).

- [ ] **Step 1: Failing test yaz**

`tests/unit/test_storage_repository.py`:

```python
"""storage.repository CRUD + index kullanımı testleri (Iter 2.2, spec § 3, § 7)."""
from __future__ import annotations

from sqlalchemy import Engine, text

from ingestion.message_parser import IngestedReading


def _reading(ts: str, value: float, sensor: str = "motor_current", device: str = "device_001") -> IngestedReading:
    return IngestedReading(
        device_id=device, sensor=sensor, timestamp=ts, state="idle", value=value, unit="A"
    )


def test_insert_then_count_and_fetch_roundtrip(migrated_engine: Engine) -> None:
    """insert sonrası count==1 ve fetch_recent aynı değeri döndürür (roundtrip)."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("2026-05-29T00:00:00.000Z", 1.5))

    assert repo.count() == 1
    rows = repo.fetch_recent("device_001", "motor_current", limit=5)
    assert len(rows) == 1
    assert rows[0].value == 1.5
    assert rows[0].device_id == "device_001"


def test_fetch_recent_orders_desc_and_limits(migrated_engine: Engine) -> None:
    """fetch_recent timestamp DESC sıralar ve limit uygular."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    for i in range(5):
        repo.insert(_reading(f"2026-05-29T00:00:{i:02d}.000Z", float(i)))

    rows = repo.fetch_recent("device_001", "motor_current", limit=3)
    assert [r.value for r in rows] == [4.0, 3.0, 2.0]  # en yeni 3, DESC


def test_fetch_recent_filters_by_device_and_sensor(migrated_engine: Engine) -> None:
    """fetch_recent yalnızca eşleşen device_id + sensor satırlarını döndürür."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("2026-05-29T00:00:00.000Z", 1.0, sensor="motor_current"))
    repo.insert(_reading("2026-05-29T00:00:01.000Z", 2.0, sensor="vibration"))
    repo.insert(_reading("2026-05-29T00:00:02.000Z", 3.0, device="device_002"))

    rows = repo.fetch_recent("device_001", "motor_current", limit=10)
    assert len(rows) == 1
    assert rows[0].value == 1.0


def test_fetch_recent_query_uses_composite_index(migrated_engine: Engine) -> None:
    """EXPLAIN QUERY PLAN composite index'i kullanır (bitti kriteri 3)."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    for i in range(10):
        repo.insert(_reading(f"2026-05-29T00:00:{i:02d}.000Z", float(i)))

    with migrated_engine.connect() as conn:
        plan = conn.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT * FROM telemetry "
                "WHERE device_id='device_001' AND sensor='motor_current' "
                "ORDER BY timestamp DESC LIMIT 5"
            )
        ).all()
    detail = " ".join(str(row[-1]) for row in plan)
    assert "USING INDEX idx_telemetry_device_sensor_ts" in detail, detail
```

- [ ] **Step 2: Test'i çalıştır, FAIL gör**

Run: `pytest tests/unit/test_storage_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'storage.repository'`

- [ ] **Step 3: `repository.py` yaz**

`src/storage/repository.py`:

```python
"""TelemetryRepository: telemetry tablosuna insert + minimal okuma (spec § 3 Iter 2.2).

insert_batch + geniş query API Iter 2.3'e ertelendi (YAGNI). count/fetch_recent
Iter 2.2 bitti kriteri 2 & 3 doğrulaması için minimal okuma yüzeyidir.
"""
from __future__ import annotations

from sqlalchemy import Engine, func, select

from ingestion.message_parser import IngestedReading
from storage.schema import telemetry


class TelemetryRepository:
    """telemetry tablosuna tek-tek insert + minimal sorgu. Engine DI ile enjekte edilir."""

    def __init__(self, engine: Engine) -> None:
        """Args: engine — SQLAlchemy Engine (migration zaten uygulanmış olmalı)."""
        self._engine = engine

    def insert(self, reading: IngestedReading) -> None:
        """Tek bir IngestedReading'i telemetry tablosuna yazar.

        Args:
            reading: Parse edilmiş telemetri okuması.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran handler yakalar).
        """
        with self._engine.begin() as conn:
            conn.execute(
                telemetry.insert().values(
                    device_id=reading.device_id,
                    sensor=reading.sensor,
                    timestamp=reading.timestamp,
                    state=reading.state,
                    value=reading.value,
                    unit=reading.unit,
                )
            )

    def count(self) -> int:
        """telemetry tablosundaki toplam satır sayısı (smoke/doğrulama için)."""
        with self._engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(telemetry)).scalar_one())

    def fetch_recent(self, device_id: str, sensor: str, limit: int) -> list[IngestedReading]:
        """Bir cihaz+sensör için en yeni `limit` okumayı timestamp DESC döndürür.

        Composite index (device_id, sensor, timestamp) bu sorgu şekli için optimaldir (spec § 7).

        Args:
            device_id: Cihaz kimliği.
            sensor: Sensör adı.
            limit: Maksimum satır sayısı.

        Returns:
            En yeniden eskiye sıralı IngestedReading listesi (id alanı dropped).
        """
        stmt = (
            select(telemetry)
            .where(telemetry.c.device_id == device_id, telemetry.c.sensor == sensor)
            .order_by(telemetry.c.timestamp.desc())
            .limit(limit)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [
            IngestedReading(
                device_id=row.device_id,
                sensor=row.sensor,
                timestamp=row.timestamp,
                state=row.state,
                value=row.value,
                unit=row.unit,
            )
            for row in rows
        ]
```

- [ ] **Step 4: Test'i çalıştır, PASS gör**

Run: `pytest tests/unit/test_storage_repository.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 152 passed, mypy Success, ruff clean

- [ ] **Step 6: Commit**

```bash
git add src/storage/repository.py tests/unit/test_storage_repository.py
git commit -m "feat(storage): TelemetryRepository insert/count/fetch_recent + index test (spec § 3, § 7)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Ingestion `__main__` wiring — repository.insert

**Files:**
- Modify: `src/ingestion/__main__.py`
- Modify: `tests/unit/test_ingestion_main.py`

`_make_message_handler` artık `repository` alır; per-mesaj `logger.info` → `repository.insert(reading)` + `OperationalError` → CRITICAL + skip (spec § 11). `run()` engine kurar → migration apply → repository kurar → handler'a verir; `finally` engine dispose. Mevcut 2 main testi yeni imzaya güncellenir.

- [ ] **Step 1: Mevcut main testlerini yeni davranışa güncelle (failing)**

`tests/unit/test_ingestion_main.py` — TAMAMEN değiştir:

```python
"""Ingestion __main__ handler testleri (Iter 2.2: repository.insert)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from sqlalchemy import Engine

from ingestion.message_parser import IngestedReading


def _payload() -> bytes:
    return json.dumps({
        "device_id": "device_001",
        "sensor": "motor_current",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")


def test_handle_message_inserts_into_repository(migrated_engine: Engine) -> None:
    """Geçerli mesaj → repository.insert çağrılır, satır DB'ye yazılır."""
    from ingestion.__main__ import _make_message_handler
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    handler = _make_message_handler(repo)

    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = _payload()

    handler(fake_msg)

    assert repo.count() == 1
    rows = repo.fetch_recent("device_001", "motor_current", limit=1)
    assert rows[0].value == 8.7


def test_handle_message_bad_json_skips_without_insert(migrated_engine: Engine) -> None:
    """Bozuk JSON → insert YOK, exception bastırılır (servis çökmez)."""
    from ingestion.__main__ import _make_message_handler
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    handler = _make_message_handler(repo)

    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = b"{not_valid_json"

    handler(fake_msg)  # raise etmemeli

    assert repo.count() == 0
```

- [ ] **Step 2: Test'i çalıştır, FAIL gör**

Run: `pytest tests/unit/test_ingestion_main.py -v`
Expected: FAIL — `_make_message_handler()` argümansız çağrılamaz / TypeError (henüz repository parametresi yok)

- [ ] **Step 3: `__main__.py` güncelle**

`src/ingestion/__main__.py` — import bloğuna ekle:

```python
from sqlalchemy.exc import OperationalError

from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository
```

Modül docstring'ini güncelle (artık SQLite var):

```python
"""Ingestion servisi entry: python -m ingestion (Iter 2.2: SQLite repository).

Faz 1 simulator MQTT yayınlarını subscribe eder, her mesajı parse edip
SQLite telemetry tablosuna tek-tek yazar (repository.insert). Migration
boot'ta apply edilir (idempotent). Bozuk JSON / eksik field → ERROR + skip;
SQLite IO hatası → CRITICAL + skip (tam retry resilience Iter 2.3'te).

SIGINT/SIGTERM ile graceful shutdown: subscriber loop_stop + disconnect + engine dispose.
"""
```

`_make_message_handler` fonksiyonunu değiştir:

```python
def _make_message_handler(
    repository: TelemetryRepository,
) -> Callable[[mqtt.MQTTMessage], None]:
    """Paho mesaj callback'i: parse + repository.insert. Hataları yutar (servis çökmemeli)."""

    def handle(msg: mqtt.MQTTMessage) -> None:
        try:
            reading = parse_message(msg.payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error(
                "Bozuk mesaj atlandı: topic={} hata={} payload={!r}",
                msg.topic,
                e,
                msg.payload[:200],
            )
            return
        try:
            repository.insert(reading)
        except OperationalError as e:
            logger.critical(
                "SQLite insert başarısız (mesaj atlandı): device={} sensor={} hata={}",
                reading.device_id,
                reading.sensor,
                e,
            )
            return
        logger.debug(
            "Yazıldı: device={} sensor={} state={} value={}",
            reading.device_id,
            reading.sensor,
            reading.state,
            reading.value,
        )

    return handle
```

`run()` içinde — config load'dan SONRA, subscriber kurmadan ÖNCE (sink-level fix bloğunun hemen ardına) ekle:

```python
    engine = create_sqlite_engine(ingestion_config.db_path)
    apply_migrations(engine, MIGRATIONS_DIR)
    repository = TelemetryRepository(engine)

    handler = _make_message_handler(repository)
```

(Mevcut `handler = _make_message_handler()` satırını yukarıdaki blokla değiştir — argümanlı çağrı.)

`finally` bloğunu güncelle (engine dispose ekle):

```python
    finally:
        subscriber.stop()
        engine.dispose()
        logger.info("Ingestion temiz kapandı")
```

- [ ] **Step 4: Test'i çalıştır, PASS gör**

Run: `pytest tests/unit/test_ingestion_main.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 152 passed, mypy Success, ruff clean

- [ ] **Step 6: Commit**

```bash
git add src/ingestion/__main__.py tests/unit/test_ingestion_main.py
git commit -m "feat(ingestion): wire SQLite repository into __main__ (spec § 3 Iter 2.2, § 11)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Integration test — end-to-end handler → SQLite

**Files:**
- Create: `tests/integration/test_ingestion_end_to_end.py`

Wired handler closure'ı + `tmp_path` dosya engine ile uçtan uca: N sahte mesaj → SQL'de N satır, sıra korunmuş (bitti kriteri 1, 2). Restart senaryosu: aynı db'ye ikinci kez migration apply no-op, eski + yeni veri korunur (bitti kriteri 4, 5).

> **Not:** Bu bir integration/characterization test — tüm bağımlılıklar (Task 1-5) zaten mevcut, dolayısıyla red-first TDD değil. Test yazılır, çalıştırılır, PASS beklenir (yeşil olmazsa entegrasyon hatası demektir).

- [ ] **Step 1: Integration test yaz**

`tests/integration/test_ingestion_end_to_end.py`:

```python
"""Ingestion uçtan uca: handler → SQLite (Iter 2.2, spec § 12 integration).

paho/run() loop'u değil; wired handler + gerçek tmp_path dosya engine. Bitti
kriteri 1, 2, 4, 5 doğrulanır.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from ingestion.__main__ import _make_message_handler
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository


def _msg(device: str, sensor: str, ts: str, value: float) -> MagicMock:
    fake = MagicMock()
    fake.topic = f"telemetry/{device}/{sensor}"
    fake.payload = json.dumps({
        "device_id": device,
        "sensor": sensor,
        "timestamp": ts,
        "state": "raising",
        "value": value,
        "unit": "A",
    }).encode("utf-8")
    return fake


def test_n_messages_persist_with_order(tmp_path: Path) -> None:
    """100 mesaj handler'a fire → SQL'de 100 satır, fetch_recent DESC sıralı."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    apply_migrations(engine, MIGRATIONS_DIR)
    repo = TelemetryRepository(engine)
    handler = _make_message_handler(repo)

    try:
        for i in range(100):
            handler(_msg("device_001", "motor_current", f"2026-05-29T00:{i // 60:02d}:{i % 60:02d}.000Z", float(i)))

        assert repo.count() == 100
        recent = repo.fetch_recent("device_001", "motor_current", limit=3)
        assert [r.value for r in recent] == [99.0, 98.0, 97.0]
    finally:
        engine.dispose()


def test_restart_reapplies_no_migration_and_appends(tmp_path: Path) -> None:
    """Servis restart: ikinci migration apply no-op, eski veri + yeni veri korunur (kriter 4, 5)."""
    from sqlalchemy import text

    db_path = tmp_path / "telemetry.db"

    # İlk "çalışma": 1 satır yaz.
    engine1 = create_sqlite_engine(db_path)
    apply_migrations(engine1, MIGRATIONS_DIR)
    handler1 = _make_message_handler(TelemetryRepository(engine1))
    handler1(_msg("device_001", "motor_current", "2026-05-29T00:00:00.000Z", 1.0))
    engine1.dispose()

    # İkinci "çalışma" (restart): aynı dosya, migration tekrar apply → no-op.
    engine2 = create_sqlite_engine(db_path)
    apply_migrations(engine2, MIGRATIONS_DIR)
    repo2 = TelemetryRepository(engine2)
    try:
        # Migration idempotent: schema_version hâlâ tek satır.
        with engine2.connect() as conn:
            sv = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar_one()
        assert sv == 1

        # Eski veri duruyor + yeni veri eklenir.
        assert repo2.count() == 1
        handler2 = _make_message_handler(repo2)
        handler2(_msg("device_001", "motor_current", "2026-05-29T00:00:01.000Z", 2.0))
        assert repo2.count() == 2
    finally:
        engine2.dispose()
```

- [ ] **Step 2: Test'i çalıştır, PASS gör**

Run: `pytest tests/integration/test_ingestion_end_to_end.py -v`
Expected: PASS (2 passed). Yeşil olmazsa entegrasyon hatası — düzelt.

- [ ] **Step 3: Tam suite + mypy + ruff + coverage**

```bash
pytest tests/ -q
pytest tests/ --cov=src/ingestion --cov=src/storage --cov-report=term-missing -q  # storage+ingestion ≥%85
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 154 passed, ingestion+storage ≥%85, mypy Success, ruff clean

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_ingestion_end_to_end.py
git commit -m "test(ingestion): end-to-end handler → SQLite integration (spec § 12)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Manuel uçtan uca smoke + CLAUDE.md/ROADMAP/memory güncelle

**Files:**
- Modify: `CLAUDE.md` (Mevcut Faz + Iter 2.2 closure bölümü)
- Modify: `docs/ROADMAP.md` (Faz 2 ilerleme)

- [ ] **Step 1: Manuel uçtan uca doğrulama (bitti kriteri 1, 2, 3)**

İki terminalde (Mosquitto broker çalışıyor olmalı):

```bash
# config dosyaları (yoksa .example'dan kopyala)
cp -n config/mqtt.yaml.example config/mqtt.yaml
cp -n config/ingestion.yaml.example config/ingestion.yaml

# Terminal 1: simulator
python -m simulator        # ImportError olursa: PYTHONPATH=src python -m simulator

# Terminal 2: ingestion (~10 sn çalıştır, Ctrl-C)
python -m ingestion        # ImportError olursa: PYTHONPATH=src python -m ingestion
```

Sonra doğrula (bitti kriteri 2, 3):

```bash
sqlite3 data/telemetry.db "SELECT COUNT(*) FROM telemetry"
sqlite3 data/telemetry.db "SELECT * FROM telemetry WHERE device_id='device_001' AND sensor='motor_current' ORDER BY timestamp DESC LIMIT 5"
sqlite3 data/telemetry.db "EXPLAIN QUERY PLAN SELECT * FROM telemetry WHERE device_id='device_001' AND sensor='motor_current' ORDER BY timestamp DESC LIMIT 5"
# Beklenen: COUNT > 0; son satırlarda EXPLAIN çıktısı 'USING INDEX idx_telemetry_device_sensor_ts'
```

Restart doğrula (bitti kriteri 4, 5): `python -m ingestion` tekrar başlat → migration "no-op" (log'da yeni "Migration uygulandı" YOK), `COUNT` artar.

- [ ] **Step 2: CLAUDE.md güncelle**

"Mevcut Faz" başlığını `Faz 2 — Iterasyon 2.3: Batch Writer + Resilience (sıradaki)` yap. "Faz 2" bölümüne Iter 2.2 closure paragrafı ekle (Iter 2.1 formatında): kapsam, dosyalar (storage paketi 4 modül + 001_initial.sql), test sayısı (141 → 154), coverage, manuel smoke sonucu. Tamamlanan iterasyonlar listesine bu planı ekle. "Çalıştırma" satırına `python -m ingestion` artık SQLite'a yazıyor notunu güncelle.

- [ ] **Step 3: ROADMAP.md güncelle**

`docs/ROADMAP.md` § Faz 2'de Iter 2.2'yi tamamlandı işaretle, Iter 2.3'ü sıradaki yap.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/ROADMAP.md
git commit -m "docs: Faz 2 Iter 2.2 (SQLite repository) closure

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notları (writing-plans gereği)

**Spec coverage (§ 3 Iter 2.2 bitti kriterleri):**
1. her mesaj SQLite'a yazılır → Task 5 (handler insert) + Task 7 manuel ✓
2. `COUNT` doğrulanabilir → Task 4 `count()` + Task 7 ✓
3. EXPLAIN index kullanır → Task 4 EXPLAIN testi + Task 7 manuel ✓
4. migration re-run no-op → Task 3 idempotent test + Task 6 restart test ✓
5. restart appends → Task 6 restart test + Task 7 manuel ✓
6. unit + integration ≥%85 → Task 1-6 tüm testler + Task 6 coverage step ✓

**Tip tutarlılığı:** `create_sqlite_engine(db_path: Path) -> Engine`, `apply_migrations(engine: Engine, migrations_dir: Path) -> None`, `MIGRATIONS_DIR`, `TelemetryRepository(engine)`/`.insert(reading)`/`.count()`/`.fetch_recent(device_id, sensor, limit)`, `_make_message_handler(repository)` — tüm task'larda aynı imzalar. ✓

**Placeholder taraması:** TODO/TBD/placeholder yok; her kod adımı tam içerik.

**Kapsam:** Tek iterasyon, tek implementasyon planı; batch/resilience/throughput Iter 2.3'e net ayrılmış.

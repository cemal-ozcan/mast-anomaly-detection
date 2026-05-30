# Faz 3 — Streamlit Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task's final verification step MUST run FULL pytest suite + mypy + ruff over src AND ALL tests dirs (incl. `src/dashboard`).

**Goal:** `streamlit run src/dashboard/app.py` ile çalışan, cihaz + zaman-aralığı seçtiren, 6 sensörün son X dakikasını line chart'larda gösteren ve `st.experimental_fragment` ile otomatik yenilenen basit gözlem dashboard'u.

**Architecture:** Yeni `src/dashboard/` paketi: `transform.py` (saf helper'lar — `window_to_since`, `readings_to_frame`, `WINDOW_OPTIONS`; tam test edilebilir) + `app.py` (ince Streamlit wiring). `TelemetryRepository` iki okuma metodu kazanır (`list_devices`, `fetch_window`). Dashboard ingestion'ın yazdığı aynı `data/telemetry.db`'yi WAL eşzamanlı okumayla sorgular; engine `@st.cache_resource` ile bir kez kurulur.

**Tech Stack:** Streamlit 1.36.0 (`st.experimental_fragment(run_every=...)` — 1.36 API; `st.cache_resource`; `st.line_chart`), pandas 2.2.2, SQLAlchemy 2.0 Core, mypy strict, ruff, pytest. Yeni runtime dependency YOK (streamlit + pandas zaten requirements.txt'te).

**Referans:** `docs/specs/2026-05-30-faz3-dashboard-design.md` (§ 4 storage API, § 5 transform, § 6 app, § 7 hata, § 8 test, § 9 kabul kriterleri). Telemetri timestamp formatı (girdi kontratı, Faz 1 § 7): `YYYY-MM-DDTHH:MM:SS.sssZ` — `src/simulator/publisher.py:_now_iso` (`datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00","Z")`).

---

## Önkoşul

`.venv` aktif, Faz 2 testleri (166 passed + 1 skipped) yeşil:
```bash
cd /Users/cemalozcan/Desktop/mast-anomaly-detection
source .venv/bin/activate
pytest tests/ -q                                                                      # 166 passed, 1 skipped
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios tests/smoke  # Success
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios tests/smoke  # All checks passed
```
Streamlit/pandas yüklü doğrula: `python -c "import streamlit, pandas; print(streamlit.__version__, pandas.__version__)"` → `1.36.0 2.2.2`. **`st.experimental_fragment` kullanılır (1.36'da `st.fragment` YOK).**

---

## Dosya Yapısı (Faz 3 sonunda)

```
src/storage/repository.py                # MODIFY: list_devices + fetch_window + _row_to_reading DRY helper
src/dashboard/                           # YENİ paket
├── __init__.py
├── transform.py                         # window_to_since + readings_to_frame + WINDOW_OPTIONS
└── app.py                               # streamlit run entry (ince wiring)

tests/unit/test_storage_repository.py    # MODIFY: list_devices + fetch_window testleri
tests/unit/test_dashboard_transform.py   # YENİ: window_to_since + readings_to_frame testleri

pyproject.toml                           # MODIFY: packages.find include "dashboard*"
```

**Beklenen test sayısı:** 166 → ~177 passed (+ 1 smoke skipped) — repository +5, transform +6. `app.py` unit test YOK (ince presentation, manuel smoke).
**Hedef coverage:** `transform.py` + yeni repository metodları ≥%85. `app.py` coverage hedefine dahil edilmez.

---

## Task 1: `TelemetryRepository` read metodları (`list_devices`, `fetch_window`)

**Files:**
- Modify: `src/storage/repository.py`
- Test: `tests/unit/test_storage_repository.py`

Dashboard'un ihtiyacı: distinct cihaz listesi + zaman-aralığı sorgusu. Ayrıca `fetch_recent` ile `fetch_window`'un IngestedReading reconstruction'ı duplike olduğundan `_row_to_reading` DRY helper'ı çıkarılır.

- [ ] **Step 1: Failing testleri ekle** — `tests/unit/test_storage_repository.py` SONUNA (mevcut testler + `_reading` helper'a dokunma):

```python
def test_list_devices_empty(migrated_engine: Engine) -> None:
    """Boş tablo → boş liste."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    assert repo.list_devices() == []


def test_list_devices_distinct_sorted(migrated_engine: Engine) -> None:
    """Distinct device_id'ler alfabetik sıralı döner (tekrarlar tekilleşir)."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("2026-05-30T00:00:00.000Z", 1.0, device="device_002"))
    repo.insert(_reading("2026-05-30T00:00:01.000Z", 2.0, device="device_001"))
    repo.insert(_reading("2026-05-30T00:00:02.000Z", 3.0, device="device_002"))
    assert repo.list_devices() == ["device_001", "device_002"]


def test_fetch_window_since_none_returns_all_asc(migrated_engine: Engine) -> None:
    """since=None → tüm satırlar timestamp ASC sıralı (insert sırasından bağımsız)."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("2026-05-30T00:00:02.000Z", 2.0))
    repo.insert(_reading("2026-05-30T00:00:00.000Z", 0.0))
    repo.insert(_reading("2026-05-30T00:00:01.000Z", 1.0))
    rows = repo.fetch_window("device_001", "motor_current", None)
    assert [r.value for r in rows] == [0.0, 1.0, 2.0]


def test_fetch_window_since_filters_inclusive(migrated_engine: Engine) -> None:
    """since cutoff'tan (dahil) itibaren satırlar döner."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    for i in range(4):
        repo.insert(_reading(f"2026-05-30T00:00:0{i}.000Z", float(i)))
    rows = repo.fetch_window("device_001", "motor_current", "2026-05-30T00:00:02.000Z")
    assert [r.value for r in rows] == [2.0, 3.0]


def test_fetch_window_filters_device_and_sensor(migrated_engine: Engine) -> None:
    """fetch_window yalnızca eşleşen device_id + sensor satırlarını döner."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("2026-05-30T00:00:00.000Z", 1.0, sensor="motor_current"))
    repo.insert(_reading("2026-05-30T00:00:01.000Z", 2.0, sensor="vibration"))
    repo.insert(_reading("2026-05-30T00:00:02.000Z", 3.0, device="device_002"))
    rows = repo.fetch_window("device_001", "motor_current", None)
    assert len(rows) == 1
    assert rows[0].value == 1.0
```

- [ ] **Step 2: Run, verify FAIL** — `pytest tests/unit/test_storage_repository.py -k "list_devices or fetch_window" -v` → FAIL (AttributeError: list_devices/fetch_window)

- [ ] **Step 3: Implement.** In `src/storage/repository.py`: (a) extract `_row_to_reading` static helper; (b) refactor `fetch_recent` to use it; (c) add `list_devices` + `fetch_window`.

Add static helper (after `_reading_to_dict`):
```python
    @staticmethod
    def _row_to_reading(row: object) -> IngestedReading:
        """SQLAlchemy Row'u IngestedReading'e çevirir (fetch_recent + fetch_window DRY)."""
        return IngestedReading(
            device_id=row.device_id,
            sensor=row.sensor,
            timestamp=row.timestamp,
            state=row.state,
            value=row.value,
            unit=row.unit,
        )
```
Refactor `fetch_recent`'in dönüşünü:
```python
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_reading(row) for row in rows]
```
Add the two read methods (after `fetch_recent`):
```python
    def list_devices(self) -> list[str]:
        """telemetry'deki distinct device_id'leri alfabetik sıralı döndürür (veri yoksa boş)."""
        stmt = select(telemetry.c.device_id).distinct().order_by(telemetry.c.device_id)
        with self._engine.connect() as conn:
            return [row[0] for row in conn.execute(stmt).all()]

    def fetch_window(
        self, device_id: str, sensor: str, since: str | None
    ) -> list[IngestedReading]:
        """Bir cihaz+sensör için `since`'ten itibaren okumaları timestamp ASC döndürür (spec § 4).

        Args:
            device_id: Cihaz kimliği.
            sensor: Sensör adı.
            since: ISO 8601 ms cutoff (YYYY-MM-DDTHH:MM:SS.sssZ) veya None (tümü).
                timestamp >= since olan satırlar döner.

        Returns:
            Eskiden yeniye (ASC) sıralı IngestedReading listesi.
        """
        stmt = select(telemetry).where(
            telemetry.c.device_id == device_id, telemetry.c.sensor == sensor
        )
        if since is not None:
            stmt = stmt.where(telemetry.c.timestamp >= since)
        stmt = stmt.order_by(telemetry.c.timestamp.asc())
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_reading(row) for row in rows]
```
> Not: `_row_to_reading(row: object)` — Row attribute access mypy strict'te `object` üzerinde hata verirse, `from typing import Any` ile `row: Any` kullan (mevcut kodun fetch_recent'teki `row.device_id` erişimi zaten Row'un Any-benzeri davranışına dayanıyor; `Any` en uyumlusu). `Any` tercih et.

- [ ] **Step 4: Run, verify PASS** — `pytest tests/unit/test_storage_repository.py -k "list_devices or fetch_window or fetch_recent" -v` → all pass (5 yeni + mevcut fetch_recent korunur)

- [ ] **Step 5: Full suite + mypy + ruff**
```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios tests/smoke
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios tests/smoke
```
Expected: 171 passed, 1 skipped, mypy Success, ruff clean.

- [ ] **Step 6: Commit**
```bash
git add src/storage/repository.py tests/unit/test_storage_repository.py
git commit -m "feat(storage): list_devices + fetch_window read API + _row_to_reading DRY (spec § 4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `src/dashboard/transform.py` — saf helper'lar

**Files:**
- Create: `src/dashboard/__init__.py`, `src/dashboard/transform.py`
- Test: `tests/unit/test_dashboard_transform.py`

Zaman-aralığı → cutoff string (publisher formatıyla eşleşir) + okumalar → DataFrame. Streamlit/DB import etmez.

- [ ] **Step 1: Boş package marker** — `src/dashboard/__init__.py`:
```python
"""Dashboard paketi: Streamlit gözlem dashboard'u + saf transform helper'ları (Faz 3)."""
```

- [ ] **Step 2: Failing testleri yaz** — `tests/unit/test_dashboard_transform.py`:
```python
"""dashboard.transform saf helper testleri (Faz 3, spec § 5)."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from dashboard.transform import readings_to_frame, window_to_since
from ingestion.message_parser import IngestedReading


def _reading(ts: str, value: float) -> IngestedReading:
    return IngestedReading(
        device_id="device_001", sensor="motor_current", timestamp=ts,
        state="idle", value=value, unit="A",
    )


def test_window_to_since_5min() -> None:
    now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
    assert window_to_since(now, "Son 5 dakika") == "2026-05-30T11:55:00.000Z"


def test_window_to_since_1hour() -> None:
    now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
    assert window_to_since(now, "Son 1 saat") == "2026-05-30T11:00:00.000Z"


def test_window_to_since_all_returns_none() -> None:
    assert window_to_since(datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC), "Tümü") is None


def test_window_to_since_unknown_returns_none() -> None:
    assert window_to_since(datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC), "bogus") is None


def test_window_to_since_format_matches_publisher() -> None:
    """Cutoff publisher formatında: YYYY-MM-DDTHH:MM:SS.sssZ (lexicographic karşılaştırılabilir)."""
    s = window_to_since(datetime(2026, 5, 30, 12, 0, 0, 123000, tzinfo=UTC), "Son 15 dakika")
    assert s is not None
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", s)


def test_readings_to_frame_empty() -> None:
    frame = readings_to_frame([])
    assert frame.index.name == "timestamp"
    assert list(frame.columns) == ["value"]
    assert len(frame) == 0


def test_readings_to_frame_populated_preserves_order() -> None:
    readings = [
        _reading("2026-05-30T12:00:00.000Z", 1.0),
        _reading("2026-05-30T12:00:01.000Z", 2.0),
    ]
    frame = readings_to_frame(readings)
    assert frame.index.name == "timestamp"
    assert list(frame["value"]) == [1.0, 2.0]
    assert len(frame) == 2
```

- [ ] **Step 3: Run, verify FAIL** — `pytest tests/unit/test_dashboard_transform.py -v` → FAIL (ModuleNotFoundError: dashboard.transform)

- [ ] **Step 4: Write `src/dashboard/transform.py`:**
```python
"""Dashboard saf transform helper'ları (Faz 3 spec § 5). Streamlit/DB import etmez."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from ingestion.message_parser import IngestedReading

WINDOW_OPTIONS: dict[str, timedelta | None] = {
    "Son 5 dakika": timedelta(minutes=5),
    "Son 15 dakika": timedelta(minutes=15),
    "Son 1 saat": timedelta(hours=1),
    "Tümü": None,
}


def window_to_since(now: datetime, window: str) -> str | None:
    """Seçili pencere etiketinden ISO 8601 ms cutoff string üretir (publisher formatı).

    Cutoff `YYYY-MM-DDTHH:MM:SS.sssZ` (ms, `+00:00`→`Z`) — telemetri timestamp'leriyle
    aynı format, lexicographic `timestamp >= since` karşılaştırması doğru çalışsın.

    Args:
        now: Şimdiki UTC-aware datetime (test için enjekte edilir).
        window: WINDOW_OPTIONS anahtarlarından biri.

    Returns:
        ISO ms cutoff string; "Tümü" veya bilinmeyen pencere → None.
    """
    delta = WINDOW_OPTIONS.get(window)
    if delta is None:
        return None
    cutoff = now - delta
    return cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def readings_to_frame(readings: list[IngestedReading]) -> pd.DataFrame:
    """IngestedReading listesini st.line_chart için DataFrame'e çevirir.

    Args:
        readings: timestamp ASC sıralı okumalar (boş olabilir).

    Returns:
        timestamp (datetime index) + value kolonlu DataFrame. Boş girdi → 0 satırlı
        ama doğru-şemalı DataFrame.
    """
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [r.timestamp for r in readings], format="ISO8601", utc=True
            ),
            "value": [r.value for r in readings],
        }
    )
    return frame.set_index("timestamp")
```
> Not (mypy/pandas): pandas 2.2 `py.typed` taşır; `pd.DataFrame(...).set_index(...)` dönüşü `DataFrame` tiplenir. mypy strict `pd.to_datetime` veya `set_index` üzerinde `Any` dönüş şikayeti verirse, fonksiyon dönüş anotasyonu (`-> pd.DataFrame`) yeterli olmalı; gerekirse tek satırlık gerekçeli `# type: ignore[...]`. ruff temiz olmalı.

- [ ] **Step 5: Run, verify PASS** — `pytest tests/unit/test_dashboard_transform.py -v` → 7 passed

- [ ] **Step 6: Full suite + mypy + ruff** (dashboard dahil)
```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage src/dashboard tests/unit tests/integration tests/scenarios tests/smoke
ruff check src/simulator src/ingestion src/storage src/dashboard tests/unit tests/integration tests/scenarios tests/smoke
```
Expected: 178 passed, 1 skipped, mypy Success, ruff clean.

- [ ] **Step 7: Commit**
```bash
git add src/dashboard/__init__.py src/dashboard/transform.py tests/unit/test_dashboard_transform.py
git commit -m "feat(dashboard): transform helpers (window_to_since, readings_to_frame, spec § 5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `src/dashboard/app.py` — Streamlit dashboard + pyproject

**Files:**
- Create: `src/dashboard/app.py`
- Modify: `pyproject.toml`

İnce wiring: config + cached engine/repository + sidebar selectbox'lar + auto-refresh fragment. Unit test YOK; headless boot smoke + (Task 4'te) görsel manuel smoke.

- [ ] **Step 1: pyproject.toml `packages.find` güncelle.** `include` listesine `"dashboard*"` ekle:
```toml
include = ["simulator*", "ingestion*", "storage*", "dashboard*"]
```

- [ ] **Step 2: Write `src/dashboard/app.py`:**
```python
"""Streamlit dashboard entry (Faz 3): streamlit run src/dashboard/app.py.

Cihaz + zaman-aralığı seçilir; 6 sensör line chart'ı st.experimental_fragment ile
2 saniyede bir otomatik yenilenir. SQLite'ı (ingestion'ın yazdığı data/telemetry.db)
read-only sorgular. Gözlem modu: hiçbir şey yazmaz.

db_path: DASHBOARD_DB_PATH env varsa o, yoksa config/ingestion.yaml db_path.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st
from sqlalchemy.exc import OperationalError

from dashboard.transform import WINDOW_OPTIONS, readings_to_frame, window_to_since
from ingestion.config import load_ingestion_config
from storage.engine import create_sqlite_engine
from storage.repository import TelemetryRepository

SIX_SENSORS = [
    "motor_current",
    "motor_voltage",
    "hydraulic_pressure",
    "motor_temperature",
    "mast_position",
    "vibration",
]


def _resolve_db_path() -> Path:
    """DASHBOARD_DB_PATH env override; yoksa ingestion.yaml db_path."""
    env = os.environ.get("DASHBOARD_DB_PATH")
    if env:
        return Path(env)
    return load_ingestion_config(Path("config/ingestion.yaml")).db_path


@st.cache_resource
def _get_repository() -> TelemetryRepository:
    """Engine + repository bir kez kurulur (her rerun'da yeniden açılmaz)."""
    engine = create_sqlite_engine(_resolve_db_path())
    return TelemetryRepository(engine)


@st.experimental_fragment(run_every="2s")
def _render_charts(repository: TelemetryRepository, device_id: str, window: str) -> None:
    """Seçili cihazın 6 sensörünü 2 kolonda çizer; her 2s otomatik yenilenir."""
    since = window_to_since(datetime.now(UTC), window)
    cols = st.columns(2)
    for i, sensor in enumerate(SIX_SENSORS):
        readings = repository.fetch_window(device_id, sensor, since)
        frame = readings_to_frame(readings)
        with cols[i % 2]:
            st.subheader(sensor)
            st.line_chart(frame, y="value")


def main() -> None:
    """Dashboard ana akışı."""
    st.set_page_config(page_title="Mast Telemetri Dashboard", layout="wide")
    st.title("Teleskopik Mast — Telemetri Dashboard")

    repository = _get_repository()
    try:
        devices = repository.list_devices()
    except OperationalError:
        st.info("Henüz veri yok — ingestion telemetry tablosunu oluşturmadı (simulator + ingestion çalışıyor mu?)")
        return

    if not devices:
        st.info("Henüz veri yok — simulator + ingestion çalışıyor mu?")
        return

    device_id = st.sidebar.selectbox("Cihaz", devices)
    window = st.sidebar.selectbox("Zaman aralığı", list(WINDOW_OPTIONS.keys()), index=1)
    _render_charts(repository, device_id, window)


main()
```
> Not (mypy): `@st.cache_resource` ve `@st.experimental_fragment` decorator'ları streamlit tiplerinde `Any` dönebilir → dekorlu fonksiyon tipi `Any` olabilir; mypy strict `warn_return_any` ile `_get_repository()` çağrısı `Any` uyarısı verebilir. Gerekirse `repository = _get_repository()` satırına gerekçeli `# type: ignore[...]` ekle, veya `assert isinstance(repository, TelemetryRepository)`. ruff temiz olmalı (kullanılmayan import yok). Minimumda tut.

- [ ] **Step 3: Statik doğrulama + mypy + ruff**
```bash
python -c "import ast; ast.parse(open('src/dashboard/app.py').read()); print('syntax OK')"
mypy src/simulator src/ingestion src/storage src/dashboard tests/unit tests/integration tests/scenarios tests/smoke
ruff check src/simulator src/ingestion src/storage src/dashboard tests/unit tests/integration tests/scenarios tests/smoke
pytest tests/ -q
```
Expected: syntax OK, mypy Success, ruff clean, 178 passed + 1 skipped (app.py test eklemez).

- [ ] **Step 4: Headless boot smoke** (seeded tmp DB ile, app exception'sız ayağa kalkar):
```bash
# 1) Seed a tmp DB with a few rows
python - <<'PY'
from pathlib import Path
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository
from ingestion.message_parser import IngestedReading
p = Path("/tmp/dash_smoke.db")
for s in (p, Path(str(p)+"-wal"), Path(str(p)+"-shm")):
    s.unlink(missing_ok=True)
eng = create_sqlite_engine(p)
apply_migrations(eng, MIGRATIONS_DIR)
repo = TelemetryRepository(eng)
repo.insert_batch([IngestedReading("device_001","motor_current",f"2026-05-30T12:00:0{i}.000Z","idle",float(i),"A") for i in range(5)])
print("seeded", repo.count(), "rows; devices:", repo.list_devices())
eng.dispose()
PY
# 2) Boot streamlit headless ~6s, capture log, ensure no traceback
DASHBOARD_DB_PATH=/tmp/dash_smoke.db streamlit run src/dashboard/app.py --server.headless true --server.port 8599 > /tmp/dash_boot.log 2>&1 &
SPID=$!
sleep 6
kill $SPID 2>/dev/null
echo "=== boot log (Traceback/Error olmamalı) ==="; grep -iE "traceback|error|exception" /tmp/dash_boot.log || echo "no errors in boot log"
grep -iE "You can now view|Local URL" /tmp/dash_boot.log && echo "STREAMLIT BOOTED OK"
```
Expected: "no errors in boot log" + "STREAMLIT BOOTED OK". Eğer `experimental_fragment` DeprecationWarning çıkarsa (1.36'da beklenebilir) sorun değil — sadece Traceback/Exception olmamalı. Boot başarısızsa logu incele + raporla (assertion'ı atlama).

- [ ] **Step 5: Commit**
```bash
git add src/dashboard/app.py pyproject.toml
git commit -m "feat(dashboard): Streamlit app — device/window selectbox + 6-sensor charts + auto-refresh (spec § 6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Manuel görsel smoke + CLAUDE.md/ROADMAP/memory closure

**Files:**
- Modify: `CLAUDE.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Manuel görsel smoke (kabul kriterleri 1-5, 7).** Mosquitto çalışıyorken iki+bir terminal:
```bash
# config (yoksa kopyala)
cp -n config/mqtt.yaml.example config/mqtt.yaml 2>/dev/null; cp -n config/ingestion.yaml.example config/ingestion.yaml 2>/dev/null
# T1: simulator   T2: ingestion   T3: dashboard
python -m simulator                                  # ImportError → PYTHONPATH=src python -m simulator
python -m ingestion                                  # ImportError → PYTHONPATH=src python -m ingestion
streamlit run src/dashboard/app.py                   # tarayıcı açılır (localhost:8501)
```
Tarayıcıda doğrula: cihaz selectbox dolu, zaman-aralığı seçici çalışıyor, 6 sensör grafiği canlı veri gösteriyor + ~2s'de otomatik yenileniyor, "Tümü" tüm veriyi gösteriyor, grafikler <2s yükleniyor, layout temiz. (Bu adım kullanıcı/operatör görsel onayıdır.)

- [ ] **Step 2: Boş-DB davranışı doğrula.** Boş bir DB'ye işaret edip dostça mesaj göründüğünü gör:
```bash
rm -f /tmp/empty.db*; DASHBOARD_DB_PATH=/tmp/empty.db streamlit run src/dashboard/app.py --server.headless true --server.port 8599 &
sleep 5; curl -s localhost:8599 >/dev/null && echo "boots without crash"; kill %1 2>/dev/null
```
Beklenen: çökme yok (UI'da "Henüz veri yok" mesajı; OperationalError yakalandı).

- [ ] **Step 3: CLAUDE.md güncelle.** "Mevcut Faz"ı `Faz 4 — Kural Tabanlı Dedektör (sıradaki)` yap; Faz 3 closure paragrafı ekle (dosyalar: dashboard paketi, repository read API; test sayısı 166→178; manuel smoke sonucu); tamamlanan iterasyonlar listesine bu planı + Faz 3 spec'ini ekle; "Çalıştırma" satırına `streamlit run src/dashboard/app.py` ekle; "Faz 3 Closure" paragrafı.

- [ ] **Step 4: ROADMAP.md güncelle.** § Faz 3'ü tamamlandı işaretle (kabul kriterleri ✅), Faz 4'ü sıradaki yap.

- [ ] **Step 5: Commit**
```bash
git add CLAUDE.md docs/ROADMAP.md
git commit -m "docs: Faz 3 (Streamlit dashboard) closure

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notları (writing-plans gereği)

**Spec coverage (§ 9 kabul kriterleri):**
1. `streamlit run src/dashboard/app.py` açılır → Task 3 app + headless boot smoke + Task 4 manuel ✓
2. Canlı veri görselleşir → Task 3 _render_charts + Task 4 manuel ✓
3. Otomatik yenilenme (`st.experimental_fragment run_every`), grafik <2s → Task 3 fragment + Task 4 manuel ✓
4. Zaman-aralığı selectbox + "Tümü" → Task 2 window_to_since + Task 3 sidebar + Task 4 manuel ✓
5. Boş db/cihaz dostça mesaj → Task 3 OperationalError + empty guard + Task 4 Step 2 ✓
6. transform+repository ≥%85 coverage, önceki testler yeşil, mypy+ruff → her task verification + Task 1/2 testler ✓
7. Sunulabilir kalite (layout=wide, subheader'lar) → Task 3 + Task 4 manuel ✓

**Spec § 4 (storage API):** Task 1 (`list_devices`, `fetch_window`). **§ 5 (transform):** Task 2. **§ 6 (app):** Task 3. **§ 7 (hata):** Task 3 (OperationalError + empty guards). **§ 8 (test):** Task 1/2 unit + Task 3/4 manuel smoke.

**Tip tutarlılığı:** `list_devices() -> list[str]`; `fetch_window(device_id, sensor, since: str | None) -> list[IngestedReading]`; `_row_to_reading(row) -> IngestedReading`; `window_to_since(now: datetime, window: str) -> str | None`; `readings_to_frame(readings: list[IngestedReading]) -> pd.DataFrame`; `WINDOW_OPTIONS`; `SIX_SENSORS`; `_resolve_db_path() -> Path`; `_get_repository() -> TelemetryRepository`; `_render_charts(repository, device_id, window)` — tüm task'larda tutarlı.

**Placeholder taraması:** TODO/TBD yok. mypy/pandas/streamlit "Not"ları placeholder değil — bilinen tip riskleri için gerekçeli yönlendirme (kod tam yazılı). Tüm kod blokları eksiksiz.

**Kapsam:** Tek plan, 4 task. plotly/multi-page/AppTest/downsampling açıkça kapsam dışı (spec § 1, § 10).

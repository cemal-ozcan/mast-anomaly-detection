# Faz 2 — Iterasyon 2.3: Batch Writer + Resilience + Performance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task's final verification step MUST run FULL pytest suite + mypy + ruff over src AND ALL tests dirs.

**Goal:** `python -m ingestion` artık mesajları thread-safe kuyruğa alıp ayrı drainer thread ile batch (`insert_batch`) yazar; graceful shutdown'da kuyrukta kalan her şey son flush'la yazılır (veri kaybı yok); paho broker kopmasında otomatik reconnect eder; gerçek-broker throughput smoke testi 1000 msg/sec'i doğrular.

**Architecture:** Yeni `src/ingestion/batch_writer.py` (`BatchWriter` sınıfı: thread-safe `queue.Queue` buffer + ayrı drainer thread; flush koşulu saf `_should_flush` helper'ıyla boyut/süre; shutdown'da kuyruğu boşaltıp son flush; SQLite yazma hatasında bounded retry + kalıcı fail'de shutdown sinyali). `repository.py` `insert_batch` (Core executemany) kazanır. `subscriber.py` paho `reconnect_delay_set` ekler. `__main__` handler artık `repository.insert` yerine `batch_writer.enqueue` çağırır; orchestration `__main__`'de kalır (engine extraction ertelendi). Smoke testleri `tests/smoke/` altında `RUN_SMOKE=1` env + broker erişilebilirlik çift-kapısıyla opt-in (default `pytest tests/` hızlı+yeşil kalır).

**Tech Stack:** Python 3.11+ stdlib `threading` + `queue` (asyncio DEĞİL — paho callback'leri background thread'den gelir, thread-safe queue gerek), SQLAlchemy 2.0.30 Core executemany, paho-mqtt 2.1.0, loguru, pytest, mypy strict, ruff. Yeni runtime dependency YOK.

**Referans:** `docs/specs/2026-05-29-faz2-ingestion-storage-design.md` § 3 Iter 2.3 (kapsam + 5 bitti kriteri), § 8 batch yazma mantığı (drainer pseudocode), § 11 hata yönetimi, § 12 test stratejisi (smoke), § 13 performance hedefi (1000 msg/sec, Yaklaşım A yapay publisher).

**Brainstorming kararları (bu oturum, spec'e uyumlu — Task 0'da inline işlenir):**
1. **Tek plan** (2.3 bölünmedi); smoke pragmatik tutuldu.
2. **Minimal + bounded retry** DB resilience: `insert_batch` `OperationalError` → CRITICAL + 3x bounded retry (`sleep` enjekte); kalıcı fail → `failed=True` + `shutdown_event.set()` (main graceful kapanır). Tam § 11 "retry-5s-then-exit-3 + drainer→SIGTERM" Faz 9+ production'a ertelendi.
3. **Smoke pragmatik + çift-kapı skip:** `RUN_SMOKE=1` env opt-in + broker erişilebilirlik; hızlı default süre (`SMOKE_DURATION_S`, default 5s), spec'in 60s/60k full run'ı dokümante manuel.
4. **Final flush kuyruğu boşaltır** (spec § 8 pseudocode yalnız buffer'ı flush ediyordu — veri kaybı; düzeltildi).
5. **`_should_flush` saf helper** (deterministik test). **Orchestration `__main__`'de** (engine extraction ertelendi — storage/engine.py isim çakışması + YAGNI). **Kalıcı-fail'de sys.exit YOK** (deferral'la tutarlı).

---

## Önkoşul

`.venv` aktif, Iter 2.2 testleri (155 PASS) yeşil olmalı:

```bash
cd ~/mast-anomaly-detection
source .venv/bin/activate
pytest tests/ -q                                                                      # 155 passed
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios  # Success
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios  # All checks passed
```

`IngestionConfig.batch_max_size` + `batch_flush_interval_s` Iter 2.1'de forward-compat eklenmiş (`config/ingestion.yaml.example`'da `batch.max_size: 100`, `batch.flush_interval_s: 1.0`). **Config değişikliği gerekmez.**

---

## Dosya Yapısı (Iter 2.3 sonunda)

```
src/ingestion/
├── batch_writer.py              # YENİ: BatchWriter sınıfı + _should_flush helper
├── subscriber.py                # MODIFY: reconnect_delay_set(1, 30)
└── __main__.py                  # MODIFY: handler enqueue; batch_writer lifecycle

src/storage/
└── repository.py                # MODIFY: insert_batch(readings) ekle

tests/unit/
├── test_ingestion_batch_writer.py    # YENİ: _should_flush + drain/shutdown/retry
├── test_ingestion_subscriber.py      # MODIFY: reconnect_delay_set assertion
├── test_storage_repository.py        # MODIFY: insert_batch testleri ekle
└── test_ingestion_main.py            # MODIFY: handler artık enqueue eder

tests/integration/
└── test_ingestion_end_to_end.py      # MODIFY: batch_writer üzerinden end-to-end

tests/smoke/                          # YENİ kategori
├── __init__.py                       # YENİ: boş marker
├── conftest.py                       # YENİ: RUN_SMOKE env + broker skip + yapay publisher
└── test_ingestion_throughput.py      # YENİ: 1000 msg/sec, gerçek Mosquitto

pyproject.toml                        # MODIFY: [tool.pytest.ini_options] markers += smoke
```

**Beklenen test sayısı:** 155 → ~167 (batch_writer ~6 + repository insert_batch 2 + subscriber 1 + main rework + integration rework + smoke 1-2 skipped default). Smoke testleri default run'da SKIPPED görünür.
**Hedef coverage:** ingestion + storage ≥%85 (batch_writer ≥%85).

---

## Task 0: Spec inline netleştirmeleri (3 nokta) + commit

**Files:**
- Modify: `docs/specs/2026-05-29-faz2-ingestion-storage-design.md`

- [ ] **Step 1: § 8 final-flush kuyruk boşaltma düzeltmesi**

§ 8 "Pseudocode" bloğunun hemen ALTINA ekle:

```markdown
**Final flush kuyruğu da boşaltır (düzeltme):** Yukarıdaki pseudocode shutdown'da yalnız
`buffer`'ı flush eder — ama kuyrukta `queue.get()` edilmemiş mesajlar kalabilir. Veri kaybını
önlemek için drainer, while döngüsünden çıkınca önce kuyruğu tamamen `get_nowait()` ile
`buffer`'a boşaltır, sonra flush eder. Bu bitti kriteri 3'ün (SIGTERM → kalan mesajlar yazılır)
gereğidir.
```

- [ ] **Step 2: § 11 Iter 2.3 resilience kapsamı netleştirmesi**

§ 11 tablosunun ALTINA (tablodan sonra, `---`'den önce) ekle:

```markdown
**Iter 2.3 resilience kapsamı (minimal):** Batch drainer'da `insert_batch` `OperationalError`
fırlatırsa: CRITICAL log + bounded retry (varsayılan 3 deneme, aralarında `retry_backoff_s`
bekleme). Tüm denemeler başarısızsa: CRITICAL log + `BatchWriter.failed = True` +
`shutdown_event.set()` → ana servis graceful kapanır (kalıcı disk-full/locked durumunda
buffer kaybı kaçınılmaz; loglanır). Tablodaki tam "5 sn bekle + 3x retry + sonra exit 3" ve
"drainer crash → ana servise SIGTERM" process-orchestration'ı Faz 9+ production sertleştirmesine
ertelendi (prototip için bounded-retry + graceful-shutdown sinyali yeterli).
```

- [ ] **Step 3: § 12/§ 13 smoke test opt-in + kriter 1/2 netleştirmesi**

§ 12 "Smoke Test (CI dışı)" alt başlığındaki maddelerin ALTINA ekle:

```markdown
**Opt-in çift kapı:** Smoke testleri default `pytest tests/` run'ında SKIPPED'tir. Çalışması için
hem `RUN_SMOKE=1` env değişkeni set olmalı HEM de broker `localhost:1883`'te erişilebilir olmalı
(aksi halde skip). Süre `SMOKE_DURATION_S` env ile ayarlanır (default 5s hızlı doğrulama); spec § 13'ün
tam 60s/60.000-mesaj kabul run'ı `SMOKE_DURATION_S=60 RUN_SMOKE=1 pytest tests/smoke/` ile manuel
çalıştırılır. `smoke` pytest marker'ı kayıtlıdır (`--strict-markers`).

**Kriter 1 (kayıpsız yük) yapay publisher ile:** spec § 13 Yaklaşım A — 60-cihazlı simulator yerine
test fixture'ında yapay 1000 msg/sec publisher kullanılır (simulator'ı ölçeklemek YAGNI). Kriter 4 ile
aynı mekanizma; ikisi tek throughput testiyle karşılanır.

**Kriter 2 (broker restart → reconnect) doğrulaması:** otomatik kill/restart testi kırılgan olduğu için
mekanizma (paho `reconnect_delay_set(1, 30)`) unit testle, gerçek broker-restart davranışı dokümante
manuel adımla doğrulanır (plan Task 7).
```

- [ ] **Step 4: Commit**

```bash
git add docs/specs/2026-05-29-faz2-ingestion-storage-design.md
git commit -m "docs(spec): Iter 2.3 inline netleştirmeler (final-flush queue drain, minimal resilience, smoke opt-in)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: `repository.insert_batch` — Core executemany

**Files:**
- Modify: `src/storage/repository.py`
- Test: `tests/unit/test_storage_repository.py`

`TelemetryRepository`'ye `insert_batch(readings)` ekle — tek transaction'da çok satır (SQLAlchemy Core executemany). Boş liste → no-op.

- [ ] **Step 1: Failing testleri ekle** — `tests/unit/test_storage_repository.py` dosyasının SONUNA ekle (mevcut testlere dokunma; `_reading` helper'ı zaten dosyada var):

```python
def test_insert_batch_writes_all_rows(migrated_engine: Engine) -> None:
    """insert_batch tüm satırları tek transaction'da yazar."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    batch = [_reading(f"2026-05-29T00:00:{i:02d}.000Z", float(i)) for i in range(5)]
    repo.insert_batch(batch)

    assert repo.count() == 5
    rows = repo.fetch_recent("device_001", "motor_current", limit=2)
    assert [r.value for r in rows] == [4.0, 3.0]


def test_insert_batch_empty_is_noop(migrated_engine: Engine) -> None:
    """Boş liste → hiçbir şey yazılmaz, hata fırlamaz."""
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    repo.insert_batch([])
    assert repo.count() == 0
```

- [ ] **Step 2: Run test, verify FAIL** — `pytest tests/unit/test_storage_repository.py -k insert_batch -v` → FAIL (AttributeError: insert_batch)

- [ ] **Step 3: `insert_batch` ekle** — `src/storage/repository.py` `TelemetryRepository` sınıfına, `insert` metodundan SONRA ekle:

```python
    def insert_batch(self, readings: list[IngestedReading]) -> None:
        """Birden çok okumayı tek transaction'da yazar (Core executemany, spec § 8).

        Args:
            readings: Yazılacak okumalar. Boş liste → no-op.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (drainer yakalar + bounded retry).
        """
        if not readings:
            return
        with self._engine.begin() as conn:
            conn.execute(
                telemetry.insert(),
                [
                    {
                        "device_id": r.device_id,
                        "sensor": r.sensor,
                        "timestamp": r.timestamp,
                        "state": r.state,
                        "value": r.value,
                        "unit": r.unit,
                    }
                    for r in readings
                ],
            )
```

Ayrıca module docstring'deki "insert_batch ... Iter 2.3'e ertelendi" ifadesini güncelle (artık var): docstring'in ilk satırını koru, "insert_batch + geniş query API Iter 2.3'e ertelendi (YAGNI)" cümlesini "insert_batch eklendi (Iter 2.3); geniş query API Faz 4+ detector ihtiyacına ertelendi" yap.

- [ ] **Step 4: Run test, verify PASS** — `pytest tests/unit/test_storage_repository.py -k insert_batch -v` → 2 passed

- [ ] **Step 5: Full suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 157 passed, mypy Success, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/storage/repository.py tests/unit/test_storage_repository.py
git commit -m "feat(storage): TelemetryRepository.insert_batch (Core executemany, spec § 8)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `src/ingestion/batch_writer.py` — BatchWriter + drainer thread

**Files:**
- Create: `src/ingestion/batch_writer.py`
- Test: `tests/unit/test_ingestion_batch_writer.py`

Thread-safe queue + ayrı drainer thread. `_should_flush` saf helper (deterministik test). SQLite hata bounded retry. Final flush kuyruğu boşaltır (veri kaybı yok).

- [ ] **Step 1: Failing testleri yaz** — `tests/unit/test_ingestion_batch_writer.py`:

```python
"""BatchWriter + _should_flush testleri (Iter 2.3, spec § 8, § 11)."""
from __future__ import annotations

import threading
import time
from typing import cast
from unittest.mock import MagicMock

from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from ingestion.batch_writer import BatchWriter, _should_flush
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository


def _reading(value: float) -> IngestedReading:
    return IngestedReading(
        device_id="device_001",
        sensor="motor_current",
        timestamp=f"2026-05-29T00:00:{int(value) % 60:02d}.000Z",
        state="idle",
        value=value,
        unit="A",
    )


# ---- _should_flush saf logic ----

def test_should_flush_empty_buffer_never() -> None:
    assert _should_flush(0, now=100.0, last_flush=0.0, max_size=10, flush_interval_s=1.0) is False


def test_should_flush_size_threshold() -> None:
    assert _should_flush(10, now=0.0, last_flush=0.0, max_size=10, flush_interval_s=1000.0) is True


def test_should_flush_time_threshold() -> None:
    assert _should_flush(1, now=2.0, last_flush=0.0, max_size=1000, flush_interval_s=1.0) is True


def test_should_flush_neither() -> None:
    assert _should_flush(3, now=0.5, last_flush=0.0, max_size=10, flush_interval_s=1.0) is False


# ---- drainer: shutdown final flush drains queue (kriter 3) ----

def test_stop_flushes_all_queued_messages(migrated_engine: Engine) -> None:
    """50 mesaj enqueue + stop → final flush kuyruğu boşaltır, hepsi yazılır (kriter 3)."""
    repo = TelemetryRepository(migrated_engine)
    shutdown = threading.Event()
    writer = BatchWriter(repo, shutdown, max_size=1000, flush_interval_s=1000.0)
    writer.start()
    for i in range(50):
        writer.enqueue(_reading(float(i)))
    writer.stop()

    assert repo.count() == 50


def test_size_threshold_flushes_while_running(migrated_engine: Engine) -> None:
    """max_size dolunca çalışırken flush eder (final flush beklemeden)."""
    repo = TelemetryRepository(migrated_engine)
    shutdown = threading.Event()
    writer = BatchWriter(repo, shutdown, max_size=10, flush_interval_s=1000.0)
    writer.start()
    for i in range(10):
        writer.enqueue(_reading(float(i)))

    deadline = time.monotonic() + 3.0
    while repo.count() < 10 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert repo.count() == 10
    writer.stop()


# ---- _flush_with_retry: bounded retry + persistent fail ----

def test_flush_retries_then_succeeds() -> None:
    """İlk deneme OperationalError, ikinci başarılı → True, sleep bir kez çağrılır."""
    repo = cast(TelemetryRepository, MagicMock(spec=TelemetryRepository))
    repo.insert_batch.side_effect = [OperationalError("stmt", {}, Exception("locked")), None]
    sleeps: list[float] = []
    shutdown = threading.Event()
    writer = BatchWriter(
        repo, shutdown, max_size=10, flush_interval_s=1.0,
        max_retries=3, retry_backoff_s=5.0, sleep=sleeps.append,
    )
    ok = writer._flush_with_retry([_reading(1.0)])
    assert ok is True
    assert len(sleeps) == 1
    assert writer.failed is False
    assert not shutdown.is_set()


def test_flush_persistent_failure_signals_shutdown() -> None:
    """Tüm denemeler başarısız → False, failed=True, shutdown set, sleep max_retries-1 kez."""
    repo = cast(TelemetryRepository, MagicMock(spec=TelemetryRepository))
    repo.insert_batch.side_effect = OperationalError("stmt", {}, Exception("disk full"))
    sleeps: list[float] = []
    shutdown = threading.Event()
    writer = BatchWriter(
        repo, shutdown, max_size=10, flush_interval_s=1.0,
        max_retries=3, retry_backoff_s=5.0, sleep=sleeps.append,
    )
    ok = writer._flush_with_retry([_reading(1.0)])
    assert ok is False
    assert writer.failed is True
    assert shutdown.is_set()
    assert len(sleeps) == 2  # denemeler arası: 3 deneme → 2 bekleme
```

- [ ] **Step 2: Run test, verify FAIL** — `pytest tests/unit/test_ingestion_batch_writer.py -v` → FAIL (ModuleNotFoundError: ingestion.batch_writer)

- [ ] **Step 3: Write `src/ingestion/batch_writer.py`:**

```python
"""Batch writer: thread-safe queue buffer + ayrı drainer thread (spec § 8, Iter 2.3).

paho callback'leri background thread'den `enqueue` eder; drainer thread buffer'ı flush
koşullarına göre (boyut / süre / shutdown) `repository.insert_batch` ile yazar. asyncio
DEĞİL — paho callback'leri thread'den gelir, thread-safe `queue.Queue` gerekir.

SQLite yazma hatasında bounded retry; tüm denemeler başarısızsa CRITICAL log +
`shutdown_event` set (ana servis graceful kapanır). Tam retry-then-exit resilience
Faz 9+ production'a ertelendi (spec § 11 Iter 2.3 kapsamı).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from queue import Empty, Queue

from loguru import logger
from sqlalchemy.exc import OperationalError

from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository


def _should_flush(
    buffer_len: int, now: float, last_flush: float, max_size: int, flush_interval_s: float
) -> bool:
    """Buffer flush edilmeli mi? Boş buffer asla; boyut eşiği VEYA süre eşiği.

    Args:
        buffer_len: Buffer'daki mesaj sayısı.
        now: Şimdiki monotonic zaman.
        last_flush: Son flush'ın monotonic zamanı.
        max_size: Flush tetikleyen buffer boyutu.
        flush_interval_s: Flush tetikleyen süre (saniye).

    Returns:
        Flush gerekiyorsa True.
    """
    if buffer_len == 0:
        return False
    return buffer_len >= max_size or (now - last_flush) >= flush_interval_s


class BatchWriter:
    """Mesajları kuyruğa alıp ayrı drainer thread ile batch yazar (spec § 8).

    Tek sorumluluk: buffer yönetimi + batch flush. MQTT/parse bilmez (enqueue ile beslenir).
    """

    def __init__(
        self,
        repository: TelemetryRepository,
        shutdown_event: threading.Event,
        max_size: int,
        flush_interval_s: float,
        max_retries: int = 3,
        retry_backoff_s: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        queue_poll_timeout_s: float = 0.1,
    ) -> None:
        """BatchWriter'ı kur (henüz başlatmaz).

        Args:
            repository: insert_batch sağlayan repository.
            shutdown_event: Paylaşılan kapanma sinyali (signal handler veya kalıcı DB hatası set eder).
            max_size: Buffer bu boyuta ulaşınca flush.
            flush_interval_s: Son flush'tan bu süre geçince flush.
            max_retries: insert_batch için maksimum deneme sayısı.
            retry_backoff_s: Denemeler arası bekleme (saniye).
            clock: Monotonic zaman kaynağı (test için enjekte edilebilir).
            sleep: Bekleme fonksiyonu (test için enjekte edilebilir).
            queue_poll_timeout_s: Drainer'ın kuyruk get() timeout'u.
        """
        self._repository = repository
        self._shutdown_event = shutdown_event
        self._max_size = max_size
        self._flush_interval_s = flush_interval_s
        self._max_retries = max_retries
        self._retry_backoff_s = retry_backoff_s
        self._clock = clock
        self._sleep = sleep
        self._poll_timeout_s = queue_poll_timeout_s
        self._queue: Queue[IngestedReading] = Queue()
        self._thread: threading.Thread | None = None
        self.failed = False

    def enqueue(self, reading: IngestedReading) -> None:
        """Okumayı kuyruğa ekler (paho callback thread'inden, non-blocking)."""
        self._queue.put(reading)

    def start(self) -> None:
        """Drainer thread'i başlatır."""
        self._thread = threading.Thread(
            target=self._drain_loop, name="batch-drainer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Shutdown sinyali + drainer thread join (kuyrukta kalanlar son flush ile yazılır)."""
        self._shutdown_event.set()
        if self._thread is not None:
            self._thread.join()

    def _drain_loop(self) -> None:
        """Drainer thread gövdesi: get → buffer → koşullu flush; shutdown'da final flush."""
        buffer: list[IngestedReading] = []
        last_flush = self._clock()
        while not self._shutdown_event.is_set():
            try:
                buffer.append(self._queue.get(timeout=self._poll_timeout_s))
            except Empty:
                pass
            now = self._clock()
            if _should_flush(
                len(buffer), now, last_flush, self._max_size, self._flush_interval_s
            ):
                if self._flush_with_retry(buffer):
                    buffer.clear()
                    last_flush = now
                else:
                    return  # kalıcı başarısızlık: shutdown sinyali verildi
        # Final flush: kuyrukta kalanları da boşalt + yaz (veri kaybı yok)
        self._drain_queue_into(buffer)
        if buffer:
            self._flush_with_retry(buffer)

    def _drain_queue_into(self, buffer: list[IngestedReading]) -> None:
        """Kuyruktaki tüm bekleyen mesajları buffer'a aktarır (final flush öncesi)."""
        while True:
            try:
                buffer.append(self._queue.get_nowait())
            except Empty:
                break

    def _flush_with_retry(self, buffer: list[IngestedReading]) -> bool:
        """insert_batch dener; OperationalError'da bounded retry.

        Returns:
            Başarılıysa True; tüm denemeler başarısızsa False (failed + shutdown set edilir).
        """
        for attempt in range(1, self._max_retries + 1):
            try:
                self._repository.insert_batch(buffer)
                return True
            except OperationalError as e:
                logger.critical(
                    "SQLite batch insert başarısız (deneme {}/{}): {} satır, hata={}",
                    attempt,
                    self._max_retries,
                    len(buffer),
                    e,
                )
                if attempt < self._max_retries:
                    self._sleep(self._retry_backoff_s)
        logger.critical(
            "Batch insert kalıcı başarısız: {} satır kaybı, servis kapanıyor", len(buffer)
        )
        self.failed = True
        self._shutdown_event.set()
        return False
```

- [ ] **Step 4: Run test, verify PASS** — `pytest tests/unit/test_ingestion_batch_writer.py -v` → 8 passed

- [ ] **Step 5: Full suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 165 passed, mypy Success, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/ingestion/batch_writer.py tests/unit/test_ingestion_batch_writer.py
git commit -m "feat(ingestion): BatchWriter drainer thread + bounded retry (spec § 8, § 11)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `subscriber.py` — paho reconnect backoff

**Files:**
- Modify: `src/ingestion/subscriber.py`
- Test: `tests/unit/test_ingestion_subscriber.py`

paho `reconnect_delay_set(min_delay=1, max_delay=30)` — broker kopunca exponential backoff ile otomatik reconnect (spec § 6, kriter 2).

- [ ] **Step 1: Failing test ekle** — `tests/unit/test_ingestion_subscriber.py` dosyasının SONUNA ekle (mevcut testlere dokunma; dosyadaki mevcut mock/fixture pattern'ini izle — `MagicMock` client `MQTTSubscriber(..., client=mock)` ile enjekte ediliyor):

```python
def test_connect_sets_reconnect_backoff() -> None:
    """connect_and_start paho reconnect_delay_set(1, 30) çağırır (kriter 2)."""
    from unittest.mock import MagicMock

    from ingestion.subscriber import MQTTSubscriber
    from simulator.config import MQTTConfig

    mock_client = MagicMock()
    config = MQTTConfig(
        host="localhost", port=1883, client_id_prefix="test", keepalive=60, qos=1
    )
    sub = MQTTSubscriber(
        config=config,
        topic_pattern="telemetry/+/+",
        message_handler=lambda _msg: None,
        client=mock_client,
    )
    sub.connect_and_start()
    mock_client.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=30)
```

> **Not implementer'a:** `MQTTConfig` constructor alanlarını mevcut `tests/unit/test_ingestion_subscriber.py` veya `simulator/config.py`'den doğrula; yukarıdaki alan adları (`host/port/client_id_prefix/keepalive/qos`) memory'den; farklıysa mevcut test dosyasındaki kuruluma uydur.

- [ ] **Step 2: Run test, verify FAIL** — `pytest tests/unit/test_ingestion_subscriber.py -k reconnect -v` → FAIL (reconnect_delay_set not called / AssertionError)

- [ ] **Step 3: `connect_and_start`'a ekle** — `src/ingestion/subscriber.py`, `connect_and_start` içinde `self._client.connect(...)` çağrısından ÖNCE ekle:

```python
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
```

Yani sıra: `on_message` setter → `reconnect_delay_set(...)` → `connect(...)` → `subscribe(...)` → `loop_start()`. Docstring'e bir satır ekle: `reconnect_delay_set` ile broker kopmasında otomatik exponential backoff reconnect (spec § 6).

- [ ] **Step 4: Run test, verify PASS** — `pytest tests/unit/test_ingestion_subscriber.py -k reconnect -v` → 1 passed

- [ ] **Step 5: Full suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 166 passed, mypy Success, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/ingestion/subscriber.py tests/unit/test_ingestion_subscriber.py
git commit -m "feat(ingestion): paho reconnect_delay_set(1,30) exponential backoff (spec § 6, kriter 2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `__main__` rewire — handler enqueue + BatchWriter lifecycle

**Files:**
- Modify: `src/ingestion/__main__.py`
- Modify: `tests/unit/test_ingestion_main.py`

handler artık `batch_writer.enqueue(reading)` çağırır (DB yazma drainer'a taşındı; `OperationalError` handler'dan KALKAR). `run()` BatchWriter kurar/başlatır/durdurur.

- [ ] **Step 1: Mevcut main testlerini yeni davranışa güncelle (failing)** — `tests/unit/test_ingestion_main.py`'ı TAMAMEN değiştir:

```python
"""Ingestion __main__ handler testleri (Iter 2.3: batch_writer.enqueue)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock


def _payload() -> bytes:
    return json.dumps({
        "device_id": "device_001",
        "sensor": "motor_current",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")


def test_handle_message_enqueues_parsed_reading() -> None:
    """Geçerli mesaj → batch_writer.enqueue parse edilmiş IngestedReading ile çağrılır."""
    from ingestion.__main__ import _make_message_handler

    batch_writer = MagicMock()
    handler = _make_message_handler(batch_writer)

    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = _payload()

    handler(fake_msg)

    batch_writer.enqueue.assert_called_once()
    reading = batch_writer.enqueue.call_args.args[0]
    assert reading.device_id == "device_001"
    assert reading.value == 8.7


def test_handle_message_bad_json_does_not_enqueue() -> None:
    """Bozuk JSON → enqueue YOK, exception bastırılır (servis çökmez)."""
    from ingestion.__main__ import _make_message_handler

    batch_writer = MagicMock()
    handler = _make_message_handler(batch_writer)

    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = b"{not_valid_json"

    handler(fake_msg)  # raise etmemeli

    batch_writer.enqueue.assert_not_called()
```

- [ ] **Step 2: Run test, verify FAIL** — `pytest tests/unit/test_ingestion_main.py -v` → FAIL (TypeError signature / handler hâlâ repository bekliyor)

- [ ] **Step 3: `__main__.py` güncelle:**

(a) Import bloğunu güncelle — `from sqlalchemy.exc import OperationalError` satırını SİL (artık handler'da kullanılmıyor); `from ingestion.batch_writer import BatchWriter` ekle. Mevcut `from storage.repository import TelemetryRepository`, `create_sqlite_engine`, `apply_migrations`, `MIGRATIONS_DIR` importları kalır.

(b) Module docstring'i güncelle:

```python
"""Ingestion servisi entry: python -m ingestion (Iter 2.3: batch writer + resilience).

Faz 1 simulator MQTT yayınlarını subscribe eder, her mesajı parse edip BatchWriter
kuyruğuna alır; ayrı drainer thread batch (insert_batch) ile SQLite'a yazar. Migration
boot'ta apply edilir (idempotent). Bozuk JSON / eksik field → ERROR + skip. SQLite
yazma hatası drainer'da bounded retry; kalıcı fail → CRITICAL + graceful shutdown.
paho reconnect_delay_set ile broker kopmasında otomatik reconnect.

SIGINT/SIGTERM ile graceful shutdown: subscriber durur, batch_writer kalan mesajları
son flush ile yazar, engine dispose.
"""
```

(c) `_make_message_handler`'ı değiştir (artık BatchWriter alır, enqueue eder, OperationalError catch KALKAR):

```python
def _make_message_handler(
    batch_writer: BatchWriter,
) -> Callable[[mqtt.MQTTMessage], None]:
    """Paho mesaj callback'i: parse + batch_writer.enqueue. Parse hatalarını yutar."""

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
        batch_writer.enqueue(reading)

    return handle
```

(d) `run()` içinde — `repository = TelemetryRepository(engine)` satırından SONRA, `handler = ...` satırını değiştir. Mevcut yapı:
```python
    engine = create_sqlite_engine(ingestion_config.db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repository = TelemetryRepository(engine)

        handler = _make_message_handler(repository)
        subscriber = MQTTSubscriber(...)

        shutdown = threading.Event()
        ...
        subscriber.connect_and_start()
        try:
            shutdown.wait()
        finally:
            subscriber.stop()
    finally:
        engine.dispose()
        logger.info("Ingestion temiz kapandı")
```
Şuna dönüştür (shutdown event'i batch_writer'dan ÖNCE oluştur; batch_writer start; handler enqueue; finally'de subscriber.stop sonra batch_writer.stop):

```python
    engine = create_sqlite_engine(ingestion_config.db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repository = TelemetryRepository(engine)

        shutdown = threading.Event()
        batch_writer = BatchWriter(
            repository=repository,
            shutdown_event=shutdown,
            max_size=ingestion_config.batch_max_size,
            flush_interval_s=ingestion_config.batch_flush_interval_s,
        )
        batch_writer.start()

        handler = _make_message_handler(batch_writer)
        subscriber = MQTTSubscriber(
            config=mqtt_config,
            topic_pattern=ingestion_config.subscribe_topic_pattern,
            message_handler=handler,
        )

        def _on_signal(signum: int, _frame: FrameType | None) -> None:
            logger.info("Shutdown sinyali alındı: {}", signum)
            shutdown.set()

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        subscriber.connect_and_start()
        try:
            shutdown.wait()
        finally:
            subscriber.stop()
            batch_writer.stop()
    finally:
        engine.dispose()
        logger.info("Ingestion temiz kapandı")
```

(Not: `shutdown = threading.Event()` artık batch_writer'dan önce; mevcut kodda shutdown subscriber'dan sonra oluşturuluyordu — yukarıdaki sıraya taşı. `_on_signal` tanımı `shutdown` oluşturulduktan sonra kalmalı.)

- [ ] **Step 4: Run test, verify PASS** — `pytest tests/unit/test_ingestion_main.py -v` → 2 passed

- [ ] **Step 5: Full suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 166 passed (main 2 yeniden yazıldı, sayı değişmez), mypy Success, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/ingestion/__main__.py tests/unit/test_ingestion_main.py
git commit -m "feat(ingestion): wire BatchWriter into __main__ (handler enqueue, lifecycle, spec § 3 Iter 2.3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Integration test — end-to-end batch path

**Files:**
- Modify: `tests/integration/test_ingestion_end_to_end.py`

Mevcut end-to-end test handler'a doğrudan `repository` veriyordu; artık handler `batch_writer` alıyor. Testi batch path'e güncelle: wired handler → batch_writer.enqueue → drainer → SQLite. Restart senaryosu korunur.

- [ ] **Step 1: `tests/integration/test_ingestion_end_to_end.py`'ı güncelle.** Mevcut iki test fonksiyonunun gövdesini BatchWriter kullanacak şekilde değiştir. `_msg` helper'ı aynen korunur. Yeni içerik (dosyanın tamamı):

```python
"""Ingestion uçtan uca: handler → BatchWriter → SQLite (Iter 2.3, spec § 12 integration).

paho/run() loop'u değil; wired handler + BatchWriter + gerçek tmp_path dosya engine.
Bitti kriteri 1 (kayıpsız), 3 (shutdown flush), 4 (idempotent restart), 5 (append).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

from ingestion.__main__ import _make_message_handler
from ingestion.batch_writer import BatchWriter
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


def test_n_messages_persist_via_batch_writer(tmp_path: Path) -> None:
    """100 mesaj handler→enqueue→drainer→SQLite; stop sonrası 100 satır, DESC sıralı (kriter 1, 3)."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    apply_migrations(engine, MIGRATIONS_DIR)
    repo = TelemetryRepository(engine)
    shutdown = threading.Event()
    writer = BatchWriter(repo, shutdown, max_size=100, flush_interval_s=0.2)
    writer.start()
    handler = _make_message_handler(writer)

    try:
        for i in range(100):
            handler(_msg("device_001", "motor_current", f"2026-05-29T00:{i // 60:02d}:{i % 60:02d}.000Z", float(i)))
        writer.stop()  # final flush kuyrukta kalanları yazar

        assert repo.count() == 100
        recent = repo.fetch_recent("device_001", "motor_current", limit=3)
        assert [r.value for r in recent] == [99.0, 98.0, 97.0]
    finally:
        engine.dispose()


def test_restart_reapplies_no_migration_and_appends(tmp_path: Path) -> None:
    """Servis restart: ikinci migration apply no-op, eski veri + yeni veri korunur (kriter 4, 5)."""
    from sqlalchemy import text

    db_path = tmp_path / "telemetry.db"

    # İlk "çalışma": 1 mesaj batch writer üzerinden yaz.
    engine1 = create_sqlite_engine(db_path)
    apply_migrations(engine1, MIGRATIONS_DIR)
    shutdown1 = threading.Event()
    writer1 = BatchWriter(TelemetryRepository(engine1), shutdown1, max_size=10, flush_interval_s=0.2)
    writer1.start()
    handler1 = _make_message_handler(writer1)
    handler1(_msg("device_001", "motor_current", "2026-05-29T00:00:00.000Z", 1.0))
    writer1.stop()
    engine1.dispose()

    # İkinci "çalışma" (restart): aynı dosya, migration tekrar apply → no-op.
    engine2 = create_sqlite_engine(db_path)
    apply_migrations(engine2, MIGRATIONS_DIR)
    repo2 = TelemetryRepository(engine2)
    try:
        with engine2.connect() as conn:
            sv = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar_one()
        assert sv == 1
        assert repo2.count() == 1

        shutdown2 = threading.Event()
        writer2 = BatchWriter(repo2, shutdown2, max_size=10, flush_interval_s=0.2)
        writer2.start()
        handler2 = _make_message_handler(writer2)
        handler2(_msg("device_001", "motor_current", "2026-05-29T00:00:01.000Z", 2.0))
        writer2.stop()
        assert repo2.count() == 2
    finally:
        engine2.dispose()
```

- [ ] **Step 2: Run test, verify PASS** — `pytest tests/integration/test_ingestion_end_to_end.py -v` → 2 passed. Yeşil olmazsa entegrasyon hatası (sıralama/flush) — düzelt, assertion zayıflatma.

- [ ] **Step 3: Full suite + mypy + ruff + coverage**

```bash
pytest tests/ -q
pytest tests/ --cov=src/ingestion --cov=src/storage --cov-report=term-missing -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios
```
Expected: 166 passed (integration sayısı sabit), ingestion+storage ≥%85, mypy Success, ruff clean. ingestion + storage birleşik coverage yüzdesini raporla.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_ingestion_end_to_end.py
git commit -m "test(ingestion): end-to-end batch writer → SQLite integration (spec § 12)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `tests/smoke/` — throughput smoke (opt-in, gerçek broker)

**Files:**
- Create: `tests/smoke/__init__.py`, `tests/smoke/conftest.py`, `tests/smoke/test_ingestion_throughput.py`
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]` markers)

Gerçek Mosquitto + yapay 1000 msg/sec publisher; ingestion in-process (subscriber + batch_writer). `RUN_SMOKE=1` env + broker erişilebilirlik çift-kapı; default run'da SKIPPED.

- [ ] **Step 1: pyproject.toml'a `smoke` marker ekle.** `[tool.pytest.ini_options]` bloğunda `asyncio_mode = "auto"` satırından SONRA ekle:

```toml
markers = [
    "smoke: gerçek broker throughput/resilience testleri; RUN_SMOKE=1 + broker gerekir (CI dışı)",
]
```

- [ ] **Step 2: `tests/smoke/__init__.py` oluştur** (boş):

```python
```

- [ ] **Step 3: `tests/smoke/conftest.py` oluştur:**

```python
"""Smoke test çift-kapı: RUN_SMOKE=1 env + broker erişilebilirlik (spec § 12, § 13).

Default `pytest tests/` run'ında smoke testleri SKIPPED'tir (env yok). Çalışması için:
    RUN_SMOKE=1 pytest tests/smoke/ -v
Süre: SMOKE_DURATION_S env (default 5s). Tam 60s kabul: SMOKE_DURATION_S=60 RUN_SMOKE=1 ...
"""
from __future__ import annotations

import os
import socket

import pytest

BROKER_HOST = "localhost"
BROKER_PORT = 1883


def _broker_reachable() -> bool:
    try:
        with socket.create_connection((BROKER_HOST, BROKER_PORT), timeout=1.0):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _smoke_gate() -> None:
    """Her smoke testinden önce çift kapı: env opt-in + broker erişilebilir."""
    if os.environ.get("RUN_SMOKE") != "1":
        pytest.skip("Smoke testleri opt-in: RUN_SMOKE=1 ile çalıştır")
    if not _broker_reachable():
        pytest.skip(f"Broker erişilemez: {BROKER_HOST}:{BROKER_PORT}")


@pytest.fixture
def smoke_duration_s() -> float:
    """Smoke yük süresi (saniye). SMOKE_DURATION_S env ile ayarlanır, default 5.0."""
    return float(os.environ.get("SMOKE_DURATION_S", "5.0"))
```

- [ ] **Step 4: `tests/smoke/test_ingestion_throughput.py` oluştur:**

```python
"""1000 msg/sec throughput smoke (spec § 13, kriter 1 + 4).

Yapay publisher (gerçek paho) broker'a hedef hızda yayın yapar; in-process ingestion
(subscriber + batch_writer) tmp SQLite'a yazar. Süre sonunda SQL satır sayısı yayınlanan
mesaj sayısına ±%1 yaklaşır (kayıpsız).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

from ingestion.__main__ import _make_message_handler
from ingestion.batch_writer import BatchWriter
from ingestion.subscriber import MQTTSubscriber
from simulator.config import MQTTConfig
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository

pytestmark = pytest.mark.smoke

TARGET_RATE_HZ = 1000


def _publish_load(stop_event: threading.Event, published: list[int]) -> None:
    """Hedef hızda telemetri yayını yapar; durana kadar. published[0]'a sayar."""
    client = mqtt.Client(client_id="smoke-publisher")
    client.connect("localhost", 1883, 60)
    client.loop_start()
    count = 0
    interval = 1.0 / TARGET_RATE_HZ
    next_at = time.monotonic()
    while not stop_event.is_set():
        payload = json.dumps({
            "device_id": f"device_{count % 60:03d}",
            "sensor": "motor_current",
            "timestamp": "2026-05-29T00:00:00.000Z",
            "state": "raising",
            "value": float(count % 100),
            "unit": "A",
        })
        client.publish(f"telemetry/device_{count % 60:03d}/motor_current", payload, qos=1)
        count += 1
        next_at += interval
        sleep_for = next_at - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)
    client.loop_stop()
    client.disconnect()
    published[0] = count


def test_throughput_no_loss(tmp_path: Path, smoke_duration_s: float) -> None:
    """smoke_duration_s boyunca ~1000 msg/sec yük → SQL satır sayısı yayın sayısına ±%1."""
    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    apply_migrations(engine, MIGRATIONS_DIR)
    repo = TelemetryRepository(engine)
    shutdown = threading.Event()
    writer = BatchWriter(repo, shutdown, max_size=100, flush_interval_s=1.0)
    writer.start()

    config = MQTTConfig(
        host="localhost", port=1883, client_id_prefix="smoke", keepalive=60, qos=1
    )
    subscriber = MQTTSubscriber(
        config=config,
        topic_pattern="telemetry/+/+",
        message_handler=_make_message_handler(writer),
    )
    subscriber.connect_and_start()

    published: list[int] = [0]
    stop_pub = threading.Event()
    pub_thread = threading.Thread(target=_publish_load, args=(stop_pub, published))

    try:
        pub_thread.start()
        time.sleep(smoke_duration_s)
        stop_pub.set()
        pub_thread.join(timeout=10)
        time.sleep(2.0)  # in-flight mesajların drain olması için
    finally:
        subscriber.stop()
        writer.stop()

    written = repo.count()
    engine.dispose()

    sent = published[0]
    assert sent > 0, "publisher hiç mesaj yayınlamadı"
    loss_ratio = (sent - written) / sent
    assert loss_ratio <= 0.01, f"kayıp %{loss_ratio*100:.2f} (>%1): sent={sent} written={written}"
```

> **Not implementer'a:** `MQTTConfig` alan adlarını `simulator/config.py`'den doğrula (host/port/client_id_prefix/keepalive/qos). Farklıysa uydur. paho `mqtt.Client(client_id=...)` 2.1.0 API'siyle uyumlu olmalı (Faz 1 publisher aynı sürümü kullanıyor — `src/simulator/publisher.py`'deki Client kuruluşuna bak, gerekirse `CallbackAPIVersion` parametresini eşle).

- [ ] **Step 5: Default run'da SKIPPED doğrula** — `pytest tests/smoke/ -v` → 1 skipped (RUN_SMOKE yok). Sonra `pytest tests/ -q` → tüm önceki testler pass + smoke skipped (hızlı kalır).

- [ ] **Step 6: Opt-in çalıştır (broker açıkken) — gerçek doğrulama:**

```bash
RUN_SMOKE=1 SMOKE_DURATION_S=5 pytest tests/smoke/ -v
```
Expected: 1 passed (broker `localhost:1883` açık olmalı; mosquitto). Kayıp ≤%1. Broker yoksa skipped.

> Eğer 5s'de drain yetişmiyor / kayıp >%1 ise: `flush_interval_s` veya `time.sleep(2.0)` drain payını artır; assertion'ı zayıflatma. Sorun devam ederse DONE_WITH_CONCERNS ile raporla.

- [ ] **Step 7: Full suite + mypy + ruff** (smoke dahil dizinleri ekle)

```bash
pytest tests/ -q
mypy src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios tests/smoke
ruff check src/simulator src/ingestion src/storage tests/unit tests/integration tests/scenarios tests/smoke
```
Expected: önceki testler passed + 1 skipped, mypy Success, ruff clean.

- [ ] **Step 8: Commit**

```bash
git add tests/smoke/ pyproject.toml
git commit -m "test(smoke): 1000 msg/sec throughput smoke + opt-in gate (spec § 13)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Manuel smoke (gerçek broker) + CLAUDE.md/ROADMAP/memory closure

**Files:**
- Modify: `CLAUDE.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Manuel throughput doğrulama (kriter 1, 4)** — Mosquitto çalışıyorken:

```bash
source .venv/bin/activate
RUN_SMOKE=1 SMOKE_DURATION_S=10 pytest tests/smoke/ -v
# Beklenen: 1 passed, kayıp ≤%1
```

- [ ] **Step 2: Manuel reconnect doğrulama (kriter 2)** — iki terminal:

```bash
# Terminal 1: simulator
python -m simulator         # ImportError → PYTHONPATH=src python -m simulator
# Terminal 2: ingestion
python -m ingestion         # ImportError → PYTHONPATH=src python -m ingestion
```
Sonra broker'ı yeniden başlat (`brew services restart mosquitto` veya mosquitto process'ini kill+restart). ingestion log'unda paho'nun yeniden bağlandığını gözle; broker döndükten sonra `sqlite3 data/telemetry.db "SELECT COUNT(*) FROM telemetry"` sayısının artmaya devam ettiğini doğrula. SIGINT → "Ingestion temiz kapandı" + kalan buffer flush.

- [ ] **Step 3: Manuel graceful-shutdown flush doğrulama (kriter 3)** — ingestion çalışırken birkaç saniye veri biriksin, SIGINT (Ctrl-C) gönder; log'da temiz kapanma + son flush; `COUNT` shutdown öncesi son saniyeyi de içermeli (kayıp yok).

- [ ] **Step 4: CLAUDE.md güncelle** — "Mevcut Faz"ı `Faz 2 tamamlandı → Faz 3: Streamlit Dashboard (sıradaki)` yap (Faz 2'nin son iterasyonu). "Faz 2" bölümüne Iter 2.3 closure paragrafı ekle (Iter 2.2 formatında: batch_writer + insert_batch + reconnect + smoke; test sayısı; coverage; manuel smoke sonuçları). Tamamlanan iterasyonlar listesine bu planı ekle. "Çalıştırma" satırını batch yazma ile güncelle. Bir "Faz 2 Closure" paragrafı ekle.

- [ ] **Step 5: ROADMAP.md güncelle** — § Faz 2 "İlerleme"de Iter 2.3'ü tamamlandı işaretle, Faz 2'yi kapalı işaretle, Faz 3'ü sıradaki yap.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/ROADMAP.md
git commit -m "docs: Faz 2 Iter 2.3 (batch writer + resilience) + Faz 2 closure

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notları (writing-plans gereği)

**Spec coverage (§ 3 Iter 2.3 bitti kriterleri):**
1. Kayıpsız yük (60 cihaz / yapay publisher) → Task 6 throughput smoke (kriter 1+4 yapay publisher) + Task 7 manuel ✓
2. Broker restart → reconnect → Task 3 `reconnect_delay_set` unit + Task 7 manuel broker-restart ✓
3. SIGTERM → buffer flush → Task 2 `test_stop_flushes_all_queued_messages` + Task 5 integration + Task 7 manuel ✓
4. 1000 msg/sec gecikme<1s drop 0 → Task 6 throughput smoke ✓
5. Tüm önceki testler + yeni testler → her task full suite step + Task 5 coverage ✓

**Spec § 8 (batch mantığı):** Task 2 (`_drain_loop` + `_should_flush` + final-flush queue drain) ✓
**Spec § 11 (resilience, minimal):** Task 2 `_flush_with_retry` bounded retry + shutdown sinyali; Task 0 inline kapsam netleştirmesi ✓
**Spec § 13 (performance):** Task 6 throughput smoke (Yaklaşım A yapay publisher) ✓

**Tip tutarlılığı:** `insert_batch(readings: list[IngestedReading]) -> None`; `BatchWriter(repository, shutdown_event, max_size, flush_interval_s, max_retries=3, retry_backoff_s=5.0, clock, sleep, queue_poll_timeout_s)` + `.enqueue(reading)` / `.start()` / `.stop()` / `.failed` / `._flush_with_retry(buffer) -> bool` / `._should_flush(...)`; `_make_message_handler(batch_writer)` — tüm task'larda aynı imzalar. ✓

**Placeholder taraması:** TODO/TBD yok. İki "Not implementer'a" var (Task 3 + Task 6) — bunlar placeholder değil, mevcut koddan doğrulama talimatı (MQTTConfig alan adları + paho Client API sürümü); gerçek kod tam yazılı. ✓

**Kapsam:** Tek iterasyon. Batch + resilience + smoke tek planda; queue backpressure / engine extraction / config'e retry params / tam exit-3 orchestration açıkça kapsam dışı. ✓

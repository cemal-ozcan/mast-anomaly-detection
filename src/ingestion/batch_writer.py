"""Batch writer: thread-safe queue buffer + ayrı drainer thread (spec § 8, Iter 2.3).

paho callback'leri background thread'den `enqueue` eder; drainer thread buffer'ı flush
koşullarına göre (boyut / süre / shutdown) `repository.insert_batch` ile yazar. asyncio
DEĞİL — paho callback'leri thread'den gelir, thread-safe `queue.Queue` gerekir.

SQLite yazma hatasında bounded retry; tüm denemeler başarısızsa CRITICAL log +
`shutdown_event` set (ana servis graceful kapanır). Tam retry-then-exit resilience
Faz 9+ production'a ertelendi (spec § 11 Iter 2.3 kapsamı).
"""
from __future__ import annotations

import contextlib
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
        """Drainer thread gövdesi: get → buffer → koşullu flush; shutdown'da final flush.

        En az bir mesaj blocking get ile alındıktan sonra kuyruktaki tüm mevcut mesajlar
        get_nowait ile birden alınır; bu sayede toplu enqueue max_size eşiğini tek turda
        yakalar (coverage gibi yük altında da tutarlı).
        """
        buffer: list[IngestedReading] = []
        last_flush = self._clock()
        while not self._shutdown_event.is_set():
            with contextlib.suppress(Empty):
                # Blocking: en az bir mesaj bekle
                buffer.append(self._queue.get(timeout=self._poll_timeout_s))
                # Non-blocking: kuyrukta şu an hazır olanları da al
                self._drain_queue_into(buffer)
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

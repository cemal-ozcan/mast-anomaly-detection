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

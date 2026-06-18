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
from detectors.config import build_detectors, build_statistical_detectors, load_detector_config
from detectors.fusion import fuse_anomalies
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
    detector_groups: list[tuple[list[Detector], int]],
    now: datetime,
) -> None:
    """Tek poll turu: her cihaz × her dedektör-grubu → fusion → DB-tek-hakikat reconciliation (Iter 8.5).

    `detector_groups`: (dedektörler, window_s) çiftleri — kural grubu kısa pencere (120s),
    istatistik grubu uzun pencere (3600s); cihaz başına window_cache. Tüm anomaliler birleştirilir
    → fuse_anomalies. **In-memory durum YOK:** açık-uyarı fingerprint'leri her poll DB'den okunur
    (`fetch_open_fingerprints`) ve level-triggered uzlaşılır: cihaz temiz + açık uyarı → auto-resolve;
    firing + fingerprint açık (ack dahil) → debounce; firing + açık değil → yeni uyarı. Restart = bu
    yolun ilk koşumu (orphan/duplikat yok). Faz 6 ML grubu yeni bir çift olarak eklenebilir.
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

        # Fingerprint = KATKIDA BULUNAN dedektörlerin rule_name'leri (fused(N) DEĞİL).
        # Yazım `",".join(sorted(rule_set))` (insert_anomaly) ↔ okuma `frozenset(s.split(","))`
        # (fetch_open_fingerprints) SİMETRİK olmalı; kural adlarında virgül yok (delimiter güvenli).
        rule_set = frozenset(a.rule_name for a in device_anomalies)
        open_fps = open_fingerprints.get(device_id, set())

        if not rule_set:  # cihaz temiz
            if open_fps:  # açık uyarısı varsa auto-resolve (restart'ta da DB'den okunur → orphan yok)
                try:
                    closed = repository.resolve_open_alerts(device_id, created_at)
                    if closed:
                        logger.info(
                            "Auto-resolve: device={} kapatılan uyarı={}", device_id, closed
                        )
                except OperationalError as e:
                    logger.error("Auto-resolve yazılamadı (atlandı): {}", e)
            continue
        # NOT: list_devices() append-only telemetry'den DISTINCT okur → cihaz asla "düşmez".
        if rule_set in open_fps:
            continue  # aynı fingerprint açık (active veya acknowledged) → debounce
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


def run(
    ingestion_config_path: Path = Path("config/ingestion.yaml"),
    detectors_config_path: Path = Path("config/detectors.yaml"),
) -> None:  # pragma: no cover
    """Detector servisini başlat. SIGINT/SIGTERM gelene kadar bloklar.

    db_path ingestion.yaml'dan (paylaşılan telemetry.db); poll_interval_s, window_s ve
    kural seti detectors.yaml'dan (config-driven, Iter 4.2). Gözlem modu: yalnız telemetry
    okur, yalnız anomalies yazar.

    Args:
        ingestion_config_path: db_path için ingestion.yaml yolu.
        detectors_config_path: kural seti + poll/window için detectors.yaml yolu.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: Config geçersizse.
    """
    ingestion_config = load_ingestion_config(ingestion_config_path)
    detector_config = load_detector_config(detectors_config_path)
    logger.remove()
    logger.add(sys.stderr, level=ingestion_config.log_level)

    engine = create_sqlite_engine(ingestion_config.db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repository = TelemetryRepository(engine)
        rule_detectors: list[Detector] = build_detectors(detector_config)
        statistical_detectors: list[Detector] = build_statistical_detectors(detector_config.statistical)
        detector_groups: list[tuple[list[Detector], int]] = [
            (rule_detectors, detector_config.window_s)
        ]
        if statistical_detectors and detector_config.statistical is not None:
            detector_groups.append(
                (statistical_detectors, detector_config.statistical.baseline_window_s)
            )
        shutdown = threading.Event()

        def _on_signal(signum: int, _frame: FrameType | None) -> None:
            logger.info("Shutdown sinyali alındı: {}", signum)
            shutdown.set()

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        logger.info(
            "Detector servisi başladı: poll={}s kurallar={} istatistik={}",
            detector_config.poll_interval_s,
            [d.name for d in rule_detectors],
            [d.name for d in statistical_detectors],
        )
        while not shutdown.is_set():
            try:
                _detect_once(repository, detector_groups, datetime.now(UTC))
            except OperationalError as e:
                logger.error("Poll turu DB hatası (devam): {}", e)
            shutdown.wait(detector_config.poll_interval_s)
    finally:
        engine.dispose()
        logger.info("Detector servisi temiz kapandı")

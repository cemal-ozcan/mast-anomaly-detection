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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import FrameType

import pandas as pd
from loguru import logger
from sqlalchemy.exc import OperationalError

from alerts.lifecycle import ACKNOWLEDGED
from alerts.models import Alert
from detectors.base import Anomaly, Detector
from detectors.config import (
    SeverityBands,
    build_detectors,
    build_statistical_detectors,
    load_detector_config,
)
from detectors.fusion import SEVERITY_RANK, fuse_anomalies
from detectors.scoring import severity_from_band
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


# Sensör-sağlığı (veri-kalitesi) kuralları: skoru ikili validity bayrağı (1.0), band konumu DEĞİL
# → severity banttan türetilmez, config severity'leri korunur (spec § 6; ayrı eksen Iter 8.7).
VALIDITY_RULES: frozenset[str] = frozenset({"sensor_out_of_range", "sensor_frozen"})

# _detect_once default'u için module-level singleton (frozen → paylaşımı güvenli; ruff B008).
_DEFAULT_SEVERITY_BANDS = SeverityBands()


def apply_band_severity(anomaly: Anomaly, severity_bands: SeverityBands) -> Anomaly:
    """Band-skorlu bir anomaliye severity'sini band'dan türeterek atar (Iter 8.6 (4)).

    Validity-rule (`VALIDITY_RULES`) anomalileri değişmeden döner (config severity korunur).
    `Anomaly` frozen → türetme gerektiğinde `replace` ile YENİ nesne döner.

    Args:
        anomaly: Bir dedektörün ürettiği anomali.
        severity_bands: high/critical eşikleri.

    Returns:
        Severity'si türetilmiş yeni Anomaly; validity-rule ise aynı nesne.
    """
    if anomaly.rule_name in VALIDITY_RULES:
        return anomaly
    new_sev = severity_from_band(
        anomaly.score, severity_bands.high_cutoff, severity_bands.critical_cutoff
    )
    return replace(anomaly, severity=new_sev)


def _should_reactivate(primary: Alert, new_severity: str) -> bool:
    """Ack'lenmiş bir uyarı bu poll'da re-activate edilmeli mi? (Iter 8.6).

    Yalnız acknowledged bir uyarı severity bir ÜST banda geçince True (taze dikkat ister); active uyarı
    veya aynı/düşük band → False. Karar `primary` snapshot'ına dayanır; gerçek çevirme `reactivate_alert`
    içinde `status='acknowledged'` guard'ıyla atomik (eşzamanlı durum değişiminde yarış yok).

    Args:
        primary: Cihazın mevcut açık uyarısı (birincil, poll başı snapshot).
        new_severity: Bu poll'da türetilen fused severity.

    Returns:
        Re-activate (acknowledged→active) denenmeli mi.
    """
    return primary.status == ACKNOWLEDGED and SEVERITY_RANK.get(new_severity, 0) > SEVERITY_RANK.get(
        primary.severity, 0
    )


def _detect_once(
    repository: TelemetryRepository,
    detector_groups: list[tuple[list[Detector], int]],
    now: datetime,
    severity_bands: SeverityBands = _DEFAULT_SEVERITY_BANDS,
    deadband_clean_polls: int = 3,
) -> None:
    """Tek poll turu: her cihaz × dedektör-grubu → severity türet → fusion → cihaz-seviyesi reconciliation.

    Kimlik CİHAZ seviyesidir (Iter 8.6): bir cihazın açık en fazla TEK uyarısı olur ("olay"). Diff:
    cihaz temiz + açık → deadband (Iter 8.7: clean_streak++ → `deadband_clean_polls`'da resolve, anti-flap);
    firing + açık VAR → o satırı in-place UPDATE (skor/severity refresh + eskalasyon birleşik; ack→band-yukarı
    ise re-activate; `update_alert` clean_streak'i 0'a sıfırlar); firing + açık YOK → yeni uyarı. Severity
    fusion'dan ÖNCE band'dan türetilir (validity-rule muaf, `apply_band_severity`). DB tek hakikat
    (in-memory yok); restart = normal yol. Legacy çoklu-açık → en yeni güncellenir, fazlalık resolve
    (yakınsama). `detector_groups`: (dedektörler, window_s) çiftleri; cihaz başına window_cache.
    """
    created_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    open_alerts = repository.fetch_open_alerts()

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

        # (4) severity'yi band'dan türet (validity-rule muaf) — fusion'dan ÖNCE.
        device_anomalies = [apply_band_severity(a, severity_bands) for a in device_anomalies]
        rule_set = frozenset(a.rule_name for a in device_anomalies)
        open_list = open_alerts.get(device_id, [])

        if not rule_set:  # cihaz temiz
            if open_list:
                # Deadband (Iter 8.7): hemen resolve etme; N ardışık temiz poll'dan sonra kapat (anti-flap).
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

        fused = fuse_anomalies(device_anomalies)
        if fused is None:  # pragma: no cover - rule_set boş değilse fused None olamaz
            continue
        rule_set_str = ",".join(sorted(rule_set))

        if not open_list:  # firing + açık yok → ilk tespit
            try:
                repository.insert_anomaly(fused, created_at, rule_set_str)
            except OperationalError as e:
                logger.error("Anomali yazılamadı (atlandı): {}", e)
                continue
            logger.info(
                "Alert (yeni): device={} rules={} sev={}", device_id, sorted(rule_set), fused.severity
            )
            continue

        # firing + açık VAR → in-place UPDATE (skor refresh + eskalasyon + re-activate)
        # tiebreak (a.created_at, a.id): eşit created_at'te bile deterministik birincil seçimi.
        primary = max(open_list, key=lambda a: (a.created_at, a.id))
        try:
            for extra in open_list:  # legacy çoklu-açık → fazlalıkları kapat (yakınsama)
                if extra.id != primary.id:
                    repository.resolve_alert_by_id(extra.id, created_at)
            # Ölçüm alanlarını her zaman tazele (detector-sahipli; operatör ack'ini EZMEZ).
            repository.update_alert(
                primary.id,
                rule_name=fused.rule_name,
                sensor=fused.sensor,
                severity=fused.severity,
                score=fused.score,
                value=fused.value,
                window_end=fused.window_end,
                rule_set=rule_set_str,
                description=fused.description,
            )
            # Eskalasyon (band-yukarı) → ack'lenmiş uyarıyı guard'lı re-activate et.
            if _should_reactivate(primary, fused.severity) and repository.reactivate_alert(primary.id):
                logger.info("Re-activate: device={} sev={} (eskalasyon)", device_id, fused.severity)
        except OperationalError as e:
            logger.error("Uyarı güncellenemedi (atlandı): {}", e)
            continue


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
                _detect_once(
                    repository,
                    detector_groups,
                    datetime.now(UTC),
                    detector_config.severity_bands,
                    detector_config.deadband_clean_polls,
                )
            except OperationalError as e:
                logger.error("Poll turu DB hatası (devam): {}", e)
            shutdown.wait(detector_config.poll_interval_s)
    finally:
        engine.dispose()
        logger.info("Detector servisi temiz kapandı")

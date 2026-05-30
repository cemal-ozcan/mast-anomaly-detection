"""TelemetryRepository: telemetry tablosuna insert + okuma yüzeyi (spec § 3 Iter 2.2).

insert_batch eklendi (Iter 2.3). Okuma yüzeyi: count, fetch_recent (Iter 2.2) + list_devices,
fetch_window (Faz 3 dashboard). Geniş query API Faz 4+ detector ihtiyacına ertelendi.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.engine import Row

from detectors.base import Anomaly
from ingestion.message_parser import IngestedReading
from storage.schema import anomalies, telemetry


class TelemetryRepository:
    """telemetry tablosuna tek-tek insert + minimal sorgu. Engine DI ile enjekte edilir."""

    def __init__(self, engine: Engine) -> None:
        """Args: engine — SQLAlchemy Engine (migration zaten uygulanmış olmalı)."""
        self._engine = engine

    @staticmethod
    def _reading_to_dict(reading: IngestedReading) -> dict[str, object]:
        """IngestedReading'i telemetry kolon dict'ine çevirir (insert + insert_batch DRY)."""
        return {
            "device_id": reading.device_id,
            "sensor": reading.sensor,
            "timestamp": reading.timestamp,
            "state": reading.state,
            "value": reading.value,
            "unit": reading.unit,
        }

    @staticmethod
    def _row_to_reading(row: Row[Any]) -> IngestedReading:
        """SQLAlchemy Row'u IngestedReading'e çevirir (fetch_recent + fetch_window DRY)."""
        return IngestedReading(
            device_id=row.device_id,
            sensor=row.sensor,
            timestamp=row.timestamp,
            state=row.state,
            value=row.value,
            unit=row.unit,
        )

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

    def insert(self, reading: IngestedReading) -> None:
        """Tek bir IngestedReading'i telemetry tablosuna yazar.

        Args:
            reading: Parse edilmiş telemetri okuması.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran handler yakalar).
        """
        with self._engine.begin() as conn:
            conn.execute(telemetry.insert().values(**self._reading_to_dict(reading)))

    def insert_batch(self, readings: list[IngestedReading]) -> None:
        """Birden çok okumayı tek transaction'da yazar (Core executemany, spec § 8).

        Args:
            readings: Yazılacak okumalar. Boş liste → no-op.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar + gerekirse yeniden dener).
        """
        if not readings:
            return
        with self._engine.begin() as conn:
            conn.execute(
                telemetry.insert(),
                [self._reading_to_dict(r) for r in readings],
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
        return [self._row_to_reading(row) for row in rows]

    def list_devices(self) -> list[str]:
        """telemetry'deki distinct device_id'leri alfabetik sıralı döndürür.

        Returns:
            Alfabetik sıralı device_id listesi; tabloda veri yoksa boş liste.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        stmt = select(telemetry.c.device_id).distinct().order_by(telemetry.c.device_id)
        with self._engine.connect() as conn:
            return [row.device_id for row in conn.execute(stmt).all()]

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

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
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

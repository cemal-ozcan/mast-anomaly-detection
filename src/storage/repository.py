"""TelemetryRepository: telemetry tablosuna insert + minimal okuma (spec § 3 Iter 2.2).

insert_batch eklendi (Iter 2.3); geniş query API Faz 4+ detector ihtiyacına ertelendi. count/fetch_recent
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

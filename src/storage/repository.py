"""TelemetryRepository: telemetry tablosuna insert + okuma yüzeyi (spec § 3 Iter 2.2).

insert_batch eklendi (Iter 2.3). Okuma yüzeyi: count, fetch_recent (Iter 2.2) + list_devices,
fetch_window (Faz 3 dashboard). Geniş query API Faz 4+ detector ihtiyacına ertelendi.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.engine import Row

from alerts.lifecycle import ACKNOWLEDGED, ACTIVE, RESOLVED
from alerts.models import Alert
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
    def _anomaly_to_dict(anomaly: Anomaly, created_at: str, rule_set: str) -> dict[str, object]:
        """Anomaly + created_at + rule_set'i anomalies kolon dict'ine çevirir."""
        # NOT: status/acknowledged_at/resolved_at kasıtlı dışarıda — SQLite DEFAULT 'active' uygular (Faz 7 yaşam döngüsü).
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
            "rule_set": rule_set,
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

    @staticmethod
    def _row_to_alert(row: Row[Any]) -> Alert:
        """SQLAlchemy Row'u Alert'e çevirir (id + status + lifecycle zaman damgaları dahil)."""
        return Alert(
            id=row.id,
            device_id=row.device_id,
            rule_name=row.rule_name,
            sensor=row.sensor,
            severity=row.severity,
            score=row.score,
            window_start=row.window_start,
            window_end=row.window_end,
            value=row.value,
            description=row.description,
            created_at=row.created_at,
            status=row.status,
            acknowledged_at=row.acknowledged_at,
            resolved_at=row.resolved_at,
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

    def fetch_latest_readings(self) -> list[IngestedReading]:
        """Her (device_id, sensor) çifti için en güncel okumayı döndürür (Faz 8 Iter 8.2 spec § 6).

        SQLite window function (ROW_NUMBER ... PARTITION BY) ile tek sorgu — filo kartlarının
        anlık state + son değer + unit kaynağı. Read-only (gözlem modu korunur).

        Returns:
            (device_id, sensor) sıralı IngestedReading listesi; boş tablo → boş liste.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        row_number = (
            func.row_number()
            .over(
                partition_by=(telemetry.c.device_id, telemetry.c.sensor),
                order_by=telemetry.c.timestamp.desc(),
            )
            .label("rn")
        )
        sub = select(telemetry, row_number).subquery()
        stmt = select(sub).where(sub.c.rn == 1).order_by(sub.c.device_id, sub.c.sensor)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_reading(row) for row in rows]

    def insert_anomaly(self, anomaly: Anomaly, created_at: str, rule_set: str) -> None:
        """Tek bir Anomaly'i anomalies tablosuna yazar.

        Args:
            anomaly: Bir kuralın tetiklediği anomali.
            created_at: Kalıcılık zamanı ISO 8601 ms (çağıran kendi saatinden verir —
                test edilebilirlik için DI; telemetry insert deseniyle tutarlı).
            rule_set: Uyarının fingerprint'i — sıralı virgül-bağlı kural adları (reconciliation
                kimliği, Iter 8.5).

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        with self._engine.begin() as conn:
            conn.execute(
                anomalies.insert().values(**self._anomaly_to_dict(anomaly, created_at, rule_set))
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

    def acknowledge_alert(self, alert_id: int, acknowledged_at: str) -> bool:
        """active bir uyarıyı acknowledged yapar (spec § 7). Geçiş SQL WHERE ile atomik zorlanır.

        Args:
            alert_id: Güncellenecek anomalies satırının id'si.
            acknowledged_at: ISO 8601 ms zaman damgası.

        Returns:
            Satır güncellendiyse True (geçiş geçerliydi); 0 satır → False (zaten ack/resolved).
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update()
                .where(anomalies.c.id == alert_id, anomalies.c.status == ACTIVE)
                .values(status=ACKNOWLEDGED, acknowledged_at=acknowledged_at)
            )
        return result.rowcount > 0

    def resolve_alert(self, alert_id: int, resolved_at: str) -> bool:
        """active|acknowledged bir uyarıyı resolved yapar (spec § 7).

        Args:
            alert_id: Güncellenecek anomalies satırının id'si.
            resolved_at: ISO 8601 ms zaman damgası.

        Returns:
            Satır güncellendiyse True; 0 satır → False (zaten resolved).
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update()
                .where(
                    anomalies.c.id == alert_id,
                    anomalies.c.status.in_((ACTIVE, ACKNOWLEDGED)),
                )
                .values(status=RESOLVED, resolved_at=resolved_at)
            )
        return result.rowcount > 0

    def resolve_open_alerts(self, device_id: str, resolved_at: str) -> int:
        """Bir cihazın TÜM açık (resolved olmayan) uyarılarını resolved yapar (detector auto-resolve, spec § 6).

        Args:
            device_id: Cihaz kimliği.
            resolved_at: ISO 8601 ms zaman damgası.

        Returns:
            Kapatılan satır sayısı.
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update()
                .where(anomalies.c.device_id == device_id, anomalies.c.status != RESOLVED)
                .values(status=RESOLVED, resolved_at=resolved_at)
            )
        return int(result.rowcount)

    def fetch_open_fingerprints(self) -> dict[str, set[frozenset[str]]]:
        """Açık (active|acknowledged) uyarıların rule_set fingerprint'lerini cihaz başına döndürür.

        Reconciliation kaynağı (Iter 8.5): detector her poll bunu okuyup level-triggered uzlaşır
        (DB tek hakikat). NULL rule_set (legacy satır) → boş frozenset.

        Returns:
            device_id → o cihazın açık uyarılarının rule_set frozenset'leri kümesi.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        result: dict[str, set[frozenset[str]]] = {}
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(anomalies.c.device_id, anomalies.c.rule_set).where(
                    anomalies.c.status.in_((ACTIVE, ACKNOWLEDGED))
                )
            )
            for device_id, rule_set_str in rows:
                fingerprint = frozenset(rule_set_str.split(",")) if rule_set_str else frozenset()
                result.setdefault(str(device_id), set()).add(fingerprint)
        return result

    def fetch_alerts(self, statuses: tuple[str, ...] | None, limit: int) -> list[Alert]:
        """Uyarıları (opsiyonel status filtresiyle) created_at DESC döndürür (dashboard, spec § 7/§ 8).

        Args:
            statuses: Filtre durum tuple'ı (status IN ...); None → tümü.
            limit: Maksimum satır sayısı.

        Returns:
            created_at DESC sıralı Alert listesi.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        stmt = select(anomalies)
        if statuses is not None:
            stmt = stmt.where(anomalies.c.status.in_(statuses))
        stmt = stmt.order_by(anomalies.c.created_at.desc()).limit(limit)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_alert(row) for row in rows]

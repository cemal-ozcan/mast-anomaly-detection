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

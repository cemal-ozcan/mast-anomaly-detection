"""Yalın script-based migration: schema_version + sıralı NNN_*.sql apply (spec § 9)."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import Engine, text

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _now_iso() -> str:
    """Migration zaman damgası: ISO 8601 ms UTC."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _split_sql_statements(sql: str) -> list[str]:
    """SQL dosyasını ';' ile statement'lara böler (boşları atar).

    pysqlite driver tek execute'ta tek statement çalıştırır; çok-statement DDL
    dosyaları (CREATE TABLE + CREATE INDEX) için her statement ayrı çalıştırılmalı.
    DDL'de string-literal ';' yok, basit split güvenli.
    """
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


def apply_migrations(engine: Engine, migrations_dir: Path) -> None:
    """schema_version tablosunu kontrol eder, eksik migration'ları sırayla uygular.

    İdempotent: zaten uygulanmış versiyonlar atlanır (servis restart'ta no-op).

    Args:
        engine: SQLAlchemy Engine (SQLite).
        migrations_dir: NNN_*.sql dosyalarının bulunduğu dizin.

    Raises:
        sqlalchemy.exc.OperationalError: SQL hatalıysa (bozuk şema — çağıran erken çıkmalı).
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
        )
        applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_version")).all()}

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version in applied:
            continue
        statements = _split_sql_statements(sql_file.read_text(encoding="utf-8"))
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :t)"),
                {"v": version, "t": _now_iso()},
            )
        logger.info("Migration uygulandı: {} (version={})", sql_file.name, version)

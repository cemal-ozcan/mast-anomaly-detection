"""storage.engine factory testleri (Iter 2.2, spec § 7)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text


def test_create_engine_makes_parent_dir(tmp_path: Path) -> None:
    """db_path parent dizini yoksa factory oluşturur (data/ gitignore senaryosu)."""
    from storage.engine import create_sqlite_engine

    db_path = tmp_path / "nested" / "telemetry.db"
    assert not db_path.parent.exists()

    engine = create_sqlite_engine(db_path)
    try:
        assert db_path.parent.exists()
    finally:
        engine.dispose()


def test_engine_sets_wal_and_foreign_keys_pragmas(tmp_path: Path) -> None:
    """Connect event WAL journal_mode + foreign_keys=ON set eder."""
    from storage.engine import create_sqlite_engine

    engine = create_sqlite_engine(tmp_path / "telemetry.db")
    try:
        with engine.connect() as conn:
            journal = conn.execute(text("PRAGMA journal_mode")).scalar_one()
            fk = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
        assert str(journal).lower() == "wal"
        assert int(fk) == 1
    finally:
        engine.dispose()

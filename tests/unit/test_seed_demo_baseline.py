"""seed_demo_baseline: temiz baseline DB'ye yazılır, (sensor,state) başına ≥min_baseline (Faz 8 Iter 8.1)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import text

from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations

_SCRIPT = Path("scripts/seed_demo_baseline.py")


def _load_seed_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("seed_demo_baseline", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_writes_clean_baseline(tmp_path: Path) -> None:
    """seed_baseline temiz telemetri yazar; motor_current RAISING ≥30 örnek (statistical min_baseline)."""
    db = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db)
    apply_migrations(engine, MIGRATIONS_DIR)
    mod = _load_seed_module()  # type: ignore[no-untyped-call]
    mod.seed_baseline(db_path=db, device_ids=["device_002"], window_s=300, samples_per_state=40)
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM telemetry WHERE device_id='device_002' "
            "AND sensor='motor_current' AND state='raising'"
        )).scalar_one()
    assert n >= 30
    engine.dispose()

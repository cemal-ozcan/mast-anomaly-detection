"""Integration: detectors.yaml → build_detectors → _detect_once → anomalies (Faz 4 Iter 4.2).

run() (poll loop + signal) pragma-no-cover; config→dedektör→tespit→persist yolu run()
olmadan doğrulanır. Ayrı bir imza testi run()'ın config-driven imzaya geçtiğini garanti eder.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

from detectors.config import build_detectors, load_detector_config
from detectors.service import _detect_once, run
from ingestion.message_parser import IngestedReading
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository


def test_run_signature_is_config_driven() -> None:
    """run() config-driven imzaya geçti: yalnız iki config yolu parametresi (Iter 4.2).

    Step 3'ten ÖNCE FAIL eder (eski imza poll_interval_s/window_s/motor_temp_threshold_c
    içerir) — bu testi yeşile çeviren tek şey run() refactor'udur.
    """
    params = set(inspect.signature(run).parameters)
    assert params == {"ingestion_config_path", "detectors_config_path"}


_CONFIG = """
detectors:
  poll_interval_s: 5.0
  window_s: 1000000000
  rules:
    - name: motor_temperature_high
      enabled: true
      severity: critical
      params:
        critical_threshold_c: 80.0
        trip_c: 130.0
    - name: motor_voltage_erratic
      enabled: true
      severity: warning
      params:
        std_threshold_v: 1.0
        min_samples: 10
"""


def _reading(sensor: str, ts: str, value: float, state: str = "holding") -> IngestedReading:
    return IngestedReading(
        device_id="device_001", sensor=sensor, timestamp=ts, state=state, value=value, unit="x"
    )


def test_config_driven_detectors_persist_anomalies(tmp_path: Path) -> None:
    cfg_path = tmp_path / "detectors.yaml"
    cfg_path.write_text(_CONFIG, encoding="utf-8")
    db_path = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        # Eşik-üstü sıcaklık (temp_high) + erratik voltaj (voltage_erratic) — aynı cihaz, aynı tur.
        repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
        for i, v in enumerate([24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]):
            repo.insert(_reading("motor_voltage", f"2026-05-30T00:01:{i:02d}.000Z", v))

        config = load_detector_config(cfg_path)
        detectors = build_detectors(config)
        active: dict[str, frozenset[str]] = {}
        _detect_once(repo, [(detectors, config.window_s)], active, datetime(2026, 5, 30, 1, 0, 0, tzinfo=UTC))

        stored = repo.fetch_recent_anomalies(limit=10)
        # İki kural aynı cihazda → TEK fused satır (write-side fusion, Iter 4.3).
        assert len(stored) == 1
        assert stored[0].rule_name == "fused(2)"
        assert "motor_temperature_high" in stored[0].description
        assert "motor_voltage_erratic" in stored[0].description
    finally:
        engine.dispose()

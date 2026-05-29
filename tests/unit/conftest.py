"""Shared test fixtures for unit tests (Iter 3.5 cleanup)."""
from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from simulator.config import (
    DeviceConfig,
    DeviceState,
    ScenarioWindow,
    SensorConfig,
    StateDurations,
)
from simulator.runtime import DeviceRuntimeState
from storage.migrator import MIGRATIONS_DIR, apply_migrations

# Shared fixtures path (used by test_engine_*.py and test_validation.py)
FIXTURES = Path(__file__).parent.parent / "fixtures"


# The canonical 6-sensor set (spec § 6). Use in fixtures + ad-hoc tests.
SIX_SENSOR_CONFIGS: list[SensorConfig] = [
    SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1),
    SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2),
    SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0),
    SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5),
    SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0),
    SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01),
]


def make_device(
    device_id: str = "d1",
    seed: int | None = 42,
    target_height_mm: float = 5000.0,
    sensors: list[SensorConfig] | None = None,
    state_durations: StateDurations | None = None,
    scenarios: list[ScenarioWindow] | None = None,
) -> DeviceConfig:
    """Test'lerde DeviceConfig hızlı kurulumu için factory.

    Defaults: tam 6-sensör seti, fixed state_durations (her aralık min==max),
    seed=42, target_height=5000mm, scenarios=[]. Override gerekirse kwarg ile.
    """
    return DeviceConfig(
        id=device_id,
        type="telescopic_mast_v1",
        sensors=list(sensors if sensors is not None else SIX_SENSOR_CONFIGS),
        state_durations=state_durations or StateDurations(
            idle=(5.0, 5.0),
            raising=(10.0, 10.0),
            holding=(60.0, 60.0),
            lowering=(10.0, 10.0),
        ),
        target_height_mm=target_height_mm,
        seed=seed,
        scenarios=list(scenarios) if scenarios is not None else [],
    )


def make_runtime(
    device: DeviceConfig,
    clock: Callable[[], float],
    started_at: float = 0.0,
) -> DeviceRuntimeState:
    """Test'lerde DeviceRuntimeState kurulumu. RNG device.seed'den türetilir.

    `state_entered_at_monotonic` ve `started_at_monotonic` ortak `started_at`'a
    set edilir (spec § 5 Iter 3 invariant: engine_boot_at her cihaz için ortak).
    """
    rng = random.Random(device.seed)
    initial_duration = rng.uniform(*device.state_durations.idle)
    return DeviceRuntimeState(
        state=DeviceState.IDLE,
        state_entered_at_monotonic=started_at,
        current_state_duration_s=initial_duration,
        position_mm=0.0,
        cycle_count=0,
        rng=rng,
        started_at_monotonic=started_at,
        clock=clock,
    )


@pytest.fixture
def six_sensor_configs() -> list[SensorConfig]:
    """Pytest fixture wrapping the constant; use if you want injection rather than import."""
    return list(SIX_SENSOR_CONFIGS)


@pytest.fixture
def in_memory_engine() -> Iterator[Engine]:
    """Tek-connection in-memory SQLite engine (StaticPool).

    :memory: connection-başına ayrı DB'dir; StaticPool tüm begin()/connect()
    blokları için TEK connection paylaşır ki tablo testler boyunca yaşasın.
    """
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def migrated_engine(in_memory_engine: Engine) -> Engine:
    """in_memory_engine + apply_migrations → telemetry tablosu hazır.

    Gerçek 001_initial.sql DDL'ini çalıştırır; repository testleri böylece
    schema.py Table ile SQL DDL tutarlılığını implicit doğrular.
    """
    apply_migrations(in_memory_engine, MIGRATIONS_DIR)
    return in_memory_engine

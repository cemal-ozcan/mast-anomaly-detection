"""_validate_devices testleri (Iter 3 — N cihaz desteği)."""
from __future__ import annotations

import logging

import pytest

from simulator.config import DeviceConfig, SensorConfig, StateDurations
from simulator.engine import _validate_devices

_SIX_SENSORS = [
    SensorConfig(name="motor_current", unit="A", baseline=0.5, noise_std=0.1),
    SensorConfig(name="motor_voltage", unit="V", baseline=24.0, noise_std=0.2),
    SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0),
    SensorConfig(name="motor_temperature", unit="celsius", baseline=25.0, noise_std=0.5),
    SensorConfig(name="mast_position", unit="mm", baseline=0.0, noise_std=1.0),
    SensorConfig(name="vibration", unit="g", baseline=0.05, noise_std=0.01),
]


def _make_device(device_id: str, seed: int | None = 42) -> DeviceConfig:
    return DeviceConfig(
        id=device_id,
        type="telescopic_mast_v1",
        sensors=list(_SIX_SENSORS),
        state_durations=StateDurations(
            idle=(5.0, 5.0),
            raising=(10.0, 10.0),
            holding=(60.0, 60.0),
            lowering=(10.0, 10.0),
        ),
        target_height_mm=5000.0,
        seed=seed,
    )


def test_validate_accepts_single_device() -> None:
    """Tek cihaz + 6 sensör geçerli (Iter 2b geri uyumluluğu)."""
    _validate_devices([_make_device("d1")])  # raise etmez


def test_validate_accepts_multiple_devices_with_unique_ids() -> None:
    """N cihaz, her biri 6 sensör, unique ID — geçerli."""
    _validate_devices([_make_device("d1"), _make_device("d2", seed=7)])


def test_validate_rejects_empty_device_list() -> None:
    """En az 1 cihaz olmalı."""
    with pytest.raises(ValueError, match="en az 1 cihaz"):
        _validate_devices([])


def test_validate_rejects_duplicate_device_ids() -> None:
    """Aynı device.id iki kez → topic collision riski → hata."""
    with pytest.raises(ValueError, match="unique"):
        _validate_devices([_make_device("d1"), _make_device("d1", seed=7)])


def test_validate_rejects_missing_sensor() -> None:
    """Bir cihazda 6 sensörden biri eksikse hata."""
    bad = _make_device("d1")
    bad_sensors = [s for s in _SIX_SENSORS if s.name != "vibration"]
    bad = DeviceConfig(
        id=bad.id,
        type=bad.type,
        sensors=bad_sensors,
        state_durations=bad.state_durations,
        target_height_mm=bad.target_height_mm,
        seed=bad.seed,
    )
    with pytest.raises(ValueError, match="vibration"):
        _validate_devices([bad])


def test_validate_warns_when_two_devices_share_seed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Aynı seed'li iki cihaz WARN log basar (hata değil — regresyon testi kullanım örneği)."""
    # loguru pytest caplog ile çalışması için propagate gerekiyor — engine import
    # edildiğinde loguru zaten yapılandırılıyor. Test'te caplog seviyesini WARNING'a alıyoruz.
    from loguru import logger as loguru_logger

    handler_id = loguru_logger.add(caplog.handler, level="WARNING", format="{message}")
    try:
        with caplog.at_level(logging.WARNING):
            _validate_devices([_make_device("d1", seed=42), _make_device("d2", seed=42)])
    finally:
        loguru_logger.remove(handler_id)

    # Hata raise edilmemiş; ama WARN mesajı atılmış olmalı
    assert any("aynı seed" in record.message.lower() or "same seed" in record.message.lower()
               for record in caplog.records)

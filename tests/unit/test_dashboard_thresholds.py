"""dashboard.thresholds — config'ten seviye-eşiği okuma birim testleri."""
from __future__ import annotations

from typing import Any

from detectors.config import DetectorConfig, RuleConfig


def _cfg(*rules: RuleConfig) -> DetectorConfig:
    return DetectorConfig(poll_interval_s=5.0, window_s=120, rules=tuple(rules))


def _rule(name: str, params: dict[str, Any], enabled: bool = True) -> RuleConfig:
    return RuleConfig(name=name, severity="warning", enabled=enabled, params=params)


def test_level_band_temperature() -> None:
    from dashboard.thresholds import LevelBand, level_band

    cfg = _cfg(_rule("motor_temperature_high",
                     {"critical_threshold_c": 95.0, "trip_c": 130.0}))
    assert level_band(cfg, "motor_temperature") == LevelBand(warn=95.0, trip=130.0)


def test_level_band_current_and_vibration() -> None:
    from dashboard.thresholds import LevelBand, level_band

    cfg = _cfg(
        _rule("motor_current_high", {"threshold_a": 9.0, "trip_a": 11.0}),
        _rule("vibration_elevated", {"threshold_g": 0.37, "trip_g": 0.50}),
    )
    assert level_band(cfg, "motor_current") == LevelBand(warn=9.0, trip=11.0)
    assert level_band(cfg, "vibration") == LevelBand(warn=0.37, trip=0.50)


def test_level_band_none_for_non_level_sensors() -> None:
    from dashboard.thresholds import level_band

    cfg = _cfg(_rule("motor_temperature_high",
                     {"critical_threshold_c": 95.0, "trip_c": 130.0}))
    # slope/varyans/kuralsız sensörler seviye-bandı taşımaz
    assert level_band(cfg, "hydraulic_pressure") is None
    assert level_band(cfg, "motor_voltage") is None
    assert level_band(cfg, "mast_position") is None


def test_level_band_none_when_rule_disabled_or_missing() -> None:
    from dashboard.thresholds import level_band

    disabled = _cfg(_rule("motor_temperature_high",
                          {"critical_threshold_c": 95.0, "trip_c": 130.0}, enabled=False))
    assert level_band(disabled, "motor_temperature") is None
    assert level_band(_cfg(), "motor_temperature") is None  # kural yok
    assert level_band(None, "motor_temperature") is None    # config yok


def test_level_band_none_when_trip_not_above_warn() -> None:
    from dashboard.thresholds import level_band

    bad = _cfg(_rule("motor_current_high", {"threshold_a": 11.0, "trip_a": 9.0}))
    assert level_band(bad, "motor_current") is None  # trip <= warn → çizilemez


def test_level_band_none_on_missing_param() -> None:
    from dashboard.thresholds import level_band

    cfg = _cfg(_rule("motor_current_high", {"threshold_a": 9.0}))  # trip_a yok
    assert level_band(cfg, "motor_current") is None

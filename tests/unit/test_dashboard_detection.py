"""dashboard.detection — tespit katmanı türetimi (config'ten + rule_name'den)."""
from __future__ import annotations

from typing import Any

from detectors.config import DetectorConfig, RuleConfig, StatisticalConfig


def _rule(name: str, params: dict[str, Any] | None = None, enabled: bool = True) -> RuleConfig:
    return RuleConfig(name=name, severity="warning", enabled=enabled, params=params or {})


def _cfg(rules: list[RuleConfig], stat_sensors: list[str] | None = None) -> DetectorConfig:
    stat = None
    if stat_sensors is not None:
        stat = StatisticalConfig(
            baseline_window_s=300, current_window_s=60,
            detectors=(RuleConfig("three_sigma", "warning", True, {"sensors": stat_sensors}),),
        )
    return DetectorConfig(poll_interval_s=5.0, window_s=120, rules=tuple(rules), statistical=stat)


def test_watching_layers_rule_and_stat() -> None:
    from dashboard.detection import watching_layers
    cfg = _cfg([_rule("motor_current_high", {"threshold_a": 9.0, "trip_a": 11.0})],
               stat_sensors=["motor_current", "vibration"])
    assert watching_layers(cfg, "motor_current") == ["Kural", "İstatistik"]


def test_watching_layers_rule_only() -> None:
    from dashboard.detection import watching_layers
    cfg = _cfg([_rule("motor_voltage_erratic", {"std_threshold_v": 1.0, "trip_std_v": 5.0})],
               stat_sensors=["motor_current"])
    assert watching_layers(cfg, "motor_voltage") == ["Kural"]


def test_watching_layers_out_of_range_covers_all() -> None:
    from dashboard.detection import watching_layers
    cfg = _cfg([_rule("sensor_out_of_range", {"bounds": {"mast_position": [-50, 12000]}})])
    assert "Kural" in watching_layers(cfg, "mast_position")


def test_watching_layers_disabled_and_none() -> None:
    from dashboard.detection import watching_layers
    cfg = _cfg([_rule("motor_current_high", {"threshold_a": 9.0, "trip_a": 11.0}, enabled=False)])
    assert watching_layers(cfg, "motor_current") == []
    assert watching_layers(None, "motor_current") == []


def test_watching_layers_stat_no_sensors_param_covers_all() -> None:
    from dashboard.detection import watching_layers
    cfg = DetectorConfig(
        poll_interval_s=5.0, window_s=120, rules=(),
        statistical=StatisticalConfig(300, 60, (RuleConfig("three_sigma", "warning", True, {}),)),
    )
    assert watching_layers(cfg, "motor_temperature") == ["İstatistik"]


def test_catching_layer() -> None:
    from dashboard.detection import catching_layer
    assert catching_layer("motor_temperature_high") == "Kural"
    assert catching_layer("three_sigma:motor_current") == "İstatistik"
    assert catching_layer("iqr:vibration") == "İstatistik"
    assert catching_layer("fused(3)") == "Çoklu katman"


def test_caught_layers_from_rule_set() -> None:
    from dashboard.detection import caught_layers
    # kural + istatistik birlikte (füzyon) → sıralı, tekilleştirilmiş
    assert caught_layers("motor_current_high,three_sigma:motor_current,iqr:motor_current") == [
        "Kural", "İstatistik",
    ]
    assert caught_layers("motor_current_high,vibration_elevated") == ["Kural"]
    assert caught_layers("three_sigma:motor_current") == ["İstatistik"]
    assert caught_layers(None) == [] and caught_layers("") == []

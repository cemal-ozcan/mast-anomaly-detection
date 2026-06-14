"""detectors.config: YAML loader + build_detectors (Faz 4 Iter 4.2, spec § 3/§ 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from detectors.config import (
    DetectorConfig,
    RuleConfig,
    StatisticalConfig,
    build_detectors,
    build_statistical_detectors,
    load_detector_config,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


_VALID = """
detectors:
  poll_interval_s: 5.0
  window_s: 60
  rules:
    - name: motor_temperature_high
      enabled: true
      severity: critical
      params:
        critical_threshold_c: 80.0
    - name: motor_current_high
      enabled: false
      severity: high
      params:
        state: raising
        threshold_a: 9.0
        min_samples: 10
"""


def test_load_parses_detectors_block(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID))
    assert isinstance(cfg, DetectorConfig)
    assert cfg.poll_interval_s == 5.0
    assert cfg.window_s == 60
    assert len(cfg.rules) == 2
    assert cfg.rules[0] == RuleConfig(
        name="motor_temperature_high", severity="critical", enabled=True,
        params={"critical_threshold_c": 80.0},
    )
    assert cfg.rules[1].enabled is False


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_detector_config(tmp_path / "yok.yaml")


def test_load_missing_key_raises_valueerror(tmp_path: Path) -> None:
    bad = "detectors:\n  window_s: 60\n  rules: []\n"  # poll_interval_s yok
    with pytest.raises(ValueError):
        load_detector_config(_write(tmp_path / "bad.yaml", bad))


def test_build_detectors_skips_disabled(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID))
    detectors = build_detectors(cfg)
    # motor_current_high enabled:false → sadece motor_temperature_high kurulur.
    assert [d.name for d in detectors] == ["motor_temperature_high"]


def test_build_detectors_constructs_with_params_and_severity(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID.replace("enabled: false", "enabled: true")))
    detectors = build_detectors(cfg)
    names = {d.name for d in detectors}
    assert names == {"motor_temperature_high", "motor_current_high"}


def test_build_detectors_unknown_rule_raises(tmp_path: Path) -> None:
    bad = (
        "detectors:\n  poll_interval_s: 5.0\n  window_s: 60\n  rules:\n"
        "    - name: nonexistent_rule\n      enabled: true\n      severity: warning\n      params: {}\n"
    )
    cfg = load_detector_config(_write(tmp_path / "bad.yaml", bad))
    with pytest.raises(ValueError, match="bilinmeyen kural"):
        build_detectors(cfg)


def test_build_detectors_bad_params_raises(tmp_path: Path) -> None:
    bad = (
        "detectors:\n  poll_interval_s: 5.0\n  window_s: 60\n  rules:\n"
        "    - name: motor_current_high\n      enabled: true\n      severity: high\n"
        "      params:\n        wrong_param: 1\n"
    )
    cfg = load_detector_config(_write(tmp_path / "bad.yaml", bad))
    with pytest.raises(ValueError, match="parametre"):
        build_detectors(cfg)


def test_example_file_loads_and_builds_all_six() -> None:
    """config/detectors.yaml.example geçerli ve 7 kuralı kurar (kalibrasyon dosyası canlı)."""
    cfg = load_detector_config(Path("config/detectors.yaml.example"))
    detectors = build_detectors(cfg)
    assert {d.name for d in detectors} == {
        "motor_temperature_high",
        "motor_current_high",
        "vibration_elevated",
        "hydraulic_pressure_decline",
        "motor_voltage_erratic",
        "sensor_frozen",
        "sensor_out_of_range",
    }


_VALID_WITH_STATISTICAL = """
detectors:
  poll_interval_s: 5.0
  window_s: 120
  rules:
    - name: motor_temperature_high
      enabled: true
      severity: critical
      params: {critical_threshold_c: 80.0}
statistical:
  baseline_window_s: 3600
  current_window_s: 60
  detectors:
    - name: three_sigma
      enabled: true
      severity: warning
      params: {sigma_k: 3.0, min_baseline: 30, min_current: 5}
"""


def test_load_parses_statistical_block(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID_WITH_STATISTICAL))
    assert isinstance(cfg.statistical, StatisticalConfig)
    assert cfg.statistical.baseline_window_s == 3600
    assert cfg.statistical.current_window_s == 60
    assert len(cfg.statistical.detectors) == 1
    assert cfg.statistical.detectors[0].name == "three_sigma"


def test_load_no_statistical_block_is_none(tmp_path: Path) -> None:
    """statistical bloğu yoksa cfg.statistical None (geriye uyumlu — Faz 4 config'leri)."""
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID))
    assert cfg.statistical is None


def test_build_statistical_detectors_constructs_three_sigma(tmp_path: Path) -> None:
    cfg = load_detector_config(_write(tmp_path / "d.yaml", _VALID_WITH_STATISTICAL))
    detectors = build_statistical_detectors(cfg.statistical)
    assert [d.name for d in detectors] == ["three_sigma"]


def test_build_statistical_detectors_none_returns_empty() -> None:
    assert build_statistical_detectors(None) == []


def test_build_statistical_unknown_raises(tmp_path: Path) -> None:
    bad = _VALID_WITH_STATISTICAL.replace("three_sigma", "nonexistent_stat")
    cfg = load_detector_config(_write(tmp_path / "d.yaml", bad))
    with pytest.raises(ValueError, match="bilinmeyen istatistiksel"):
        build_statistical_detectors(cfg.statistical)


def test_example_file_statistical_builds() -> None:
    """config/detectors.yaml.example statistical bloğu geçerli + three_sigma + iqr kurar."""
    cfg = load_detector_config(Path("config/detectors.yaml.example"))
    assert cfg.statistical is not None
    assert [d.name for d in build_statistical_detectors(cfg.statistical)] == ["three_sigma", "iqr"]


def test_build_statistical_detectors_includes_iqr() -> None:
    """statistical bloğunda iqr varsa build_statistical_detectors bir IQR kurar."""
    from detectors.config import RuleConfig, StatisticalConfig, build_statistical_detectors

    config = StatisticalConfig(
        baseline_window_s=3600,
        current_window_s=60,
        detectors=(
            RuleConfig(name="three_sigma", severity="warning", enabled=True, params={"sigma_k": 3.0}),
            RuleConfig(name="iqr", severity="warning", enabled=True,
                       params={"iqr_multiplier": 1.5, "min_baseline": 30, "min_current": 5}),
        ),
    )
    detectors = build_statistical_detectors(config)
    assert [d.name for d in detectors] == ["three_sigma", "iqr"]

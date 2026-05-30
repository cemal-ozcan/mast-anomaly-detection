"""detectors.config: YAML loader + build_detectors (Faz 4 Iter 4.2, spec § 3/§ 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from detectors.config import (
    DetectorConfig,
    RuleConfig,
    build_detectors,
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
    """config/detectors.yaml.example geçerli ve 6 kuralı kurar (kalibrasyon dosyası canlı)."""
    cfg = load_detector_config(Path("config/detectors.yaml.example"))
    detectors = build_detectors(cfg)
    assert {d.name for d in detectors} == {
        "motor_temperature_high",
        "motor_current_high",
        "vibration_elevated",
        "hydraulic_pressure_decline",
        "motor_voltage_erratic",
        "sensor_frozen",
    }

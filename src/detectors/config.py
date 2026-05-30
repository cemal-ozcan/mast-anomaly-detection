"""detectors.yaml loader + config-driven dedektör kurulumu (Faz 4 Iter 4.2, spec § 3/§ 4).

ingestion.config deseni: dataclass'lar + YAML loader (FileNotFoundError/ValueError).
build_detectors RULE_REGISTRY'den her aktif kuralı `severity` + `params` ile kurar.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from detectors.base import Detector
from detectors.rules import RULE_REGISTRY


@dataclass(frozen=True)
class RuleConfig:
    """detectors.yaml'daki tek kural girişi."""

    name: str
    severity: str
    enabled: bool
    params: dict[str, Any]


@dataclass(frozen=True)
class DetectorConfig:
    """detectors.yaml `detectors` bloğu."""

    poll_interval_s: float
    window_s: int
    rules: tuple[RuleConfig, ...]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"detectors.yaml dosyası bulunamadı: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"detectors config geçersiz ({path}): YAML parse hatası: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(
            f"detectors config geçersiz ({path}): kök sözlük olmalı, "
            f"alınan {type(data).__name__}"
        )
    return data


def load_detector_config(path: Path) -> DetectorConfig:
    """detectors.yaml dosyasından DetectorConfig döndürür.

    Args:
        path: detectors.yaml yolu.

    Returns:
        DetectorConfig.

    Raises:
        FileNotFoundError: Dosya yoksa.
        ValueError: YAML bozuksa veya şema geçersizse.
    """
    data = _read_yaml(path)
    try:
        det = data["detectors"]
        rules = tuple(
            RuleConfig(
                name=str(r["name"]),
                severity=str(r.get("severity", "warning")),
                enabled=bool(r.get("enabled", True)),
                params=dict(r.get("params") or {}),
            )
            for r in det["rules"]
        )
        return DetectorConfig(
            poll_interval_s=float(det["poll_interval_s"]),
            window_s=int(det["window_s"]),
            rules=rules,
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"detectors config geçersiz ({path}): {e}") from e


def build_detectors(config: DetectorConfig) -> list[Detector]:
    """Config'ten aktif (enabled) kuralları RULE_REGISTRY üzerinden kurar.

    Her kural `RULE_REGISTRY[name](severity=..., **params)` ile inşa edilir.

    Args:
        config: DetectorConfig.

    Returns:
        Kurulu Detector listesi (config sırasını korur, disabled atlanır).

    Raises:
        ValueError: Bilinmeyen kural adı veya geçersiz params.
    """
    detectors: list[Detector] = []
    for rc in config.rules:
        if not rc.enabled:
            continue
        factory = RULE_REGISTRY.get(rc.name)
        if factory is None:
            raise ValueError(f"detectors config: bilinmeyen kural '{rc.name}' (registry'de yok)")
        try:
            detectors.append(factory(severity=rc.severity, **rc.params))
        except TypeError as e:
            raise ValueError(
                f"detectors config: kural '{rc.name}' parametre hatası: {e}"
            ) from e
    return detectors

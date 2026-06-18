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
from detectors.statistical import STATISTICAL_REGISTRY


@dataclass(frozen=True)
class SeverityBands:
    """Band-pozisyon skorunu severity'ye eşleyen global eşikler (Faz 8 Iter 8.6 (4), spec § 6).

    Defaults ISO 20816 zone mantığı + sim kalibrasyonu için başlangıç; canlı smoke'ta doğrulanır.
    """

    high_cutoff: float = 0.40
    critical_cutoff: float = 0.75


@dataclass(frozen=True)
class RuleConfig:
    """detectors.yaml'daki tek kural girişi."""

    name: str
    severity: str
    enabled: bool
    params: dict[str, Any]


@dataclass(frozen=True)
class StatisticalConfig:
    """detectors.yaml `statistical` bloğu (Faz 5)."""

    baseline_window_s: int
    current_window_s: int
    detectors: tuple[RuleConfig, ...]


@dataclass(frozen=True)
class DetectorConfig:
    """detectors.yaml `detectors` bloğu (+ opsiyonel `statistical`, Faz 5)."""

    poll_interval_s: float
    window_s: int
    rules: tuple[RuleConfig, ...]
    statistical: StatisticalConfig | None = None
    severity_bands: SeverityBands = SeverityBands()


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


def _parse_statistical(block: Any) -> StatisticalConfig | None:
    """`statistical` bloğunu (varsa) StatisticalConfig'e çevirir; yoksa None."""
    if block is None:
        return None
    detectors = tuple(
        RuleConfig(
            name=str(d["name"]),
            severity=str(d.get("severity", "warning")),
            enabled=bool(d.get("enabled", True)),
            params=dict(d.get("params") or {}),
        )
        for d in block["detectors"]
    )
    return StatisticalConfig(
        baseline_window_s=int(block["baseline_window_s"]),
        current_window_s=int(block["current_window_s"]),
        detectors=detectors,
    )


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
        statistical = _parse_statistical(data.get("statistical"))
        sb = data.get("severity_bands") or {}
        severity_bands = SeverityBands(
            high_cutoff=float(sb.get("high_cutoff", 0.40)),
            critical_cutoff=float(sb.get("critical_cutoff", 0.75)),
        )
        return DetectorConfig(
            poll_interval_s=float(det["poll_interval_s"]),
            window_s=int(det["window_s"]),
            rules=rules,
            statistical=statistical,
            severity_bands=severity_bands,
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


def build_statistical_detectors(config: StatisticalConfig | None) -> list[Detector]:
    """Config'ten aktif istatistiksel dedektörleri STATISTICAL_REGISTRY üzerinden kurar.

    Her dedektör `STATISTICAL_REGISTRY[name](severity=..., current_window_s=..., **params)` ile
    inşa edilir (current_window_s blok seviyesinden geçer).

    Args:
        config: StatisticalConfig veya None (statistical bloğu yoksa).

    Returns:
        Kurulu Detector listesi (None → boş; disabled atlanır).

    Raises:
        ValueError: Bilinmeyen dedektör adı veya geçersiz params.
    """
    if config is None:
        return []
    detectors: list[Detector] = []
    for rc in config.detectors:
        if not rc.enabled:
            continue
        factory = STATISTICAL_REGISTRY.get(rc.name)
        if factory is None:
            raise ValueError(
                f"detectors config: bilinmeyen istatistiksel dedektör '{rc.name}' (registry'de yok)"
            )
        try:
            detectors.append(
                factory(severity=rc.severity, current_window_s=config.current_window_s, **rc.params)
            )
        except TypeError as e:
            raise ValueError(
                f"detectors config: istatistiksel dedektör '{rc.name}' parametre hatası: {e}"
            ) from e
    return detectors

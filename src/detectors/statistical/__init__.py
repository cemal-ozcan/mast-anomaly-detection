"""İstatistiksel dedektör registry (Faz 5). build_statistical_detectors config-driven kurar."""
from __future__ import annotations

from collections.abc import Callable

from detectors.base import Detector
from detectors.statistical.three_sigma import ThreeSigma

STATISTICAL_REGISTRY: dict[str, Callable[..., Detector]] = {
    "three_sigma": ThreeSigma,
}

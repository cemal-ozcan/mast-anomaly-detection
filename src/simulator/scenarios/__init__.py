"""Scenarios package: SCENARIO_REGISTRY + active_scenarios_at helper (spec § 4 + § 8)."""
from __future__ import annotations

from simulator.config import ScenarioWindow
from simulator.scenarios.base import FaultScenario
from simulator.scenarios.mechanical_wear import MechanicalWear

# Registry: YAML'deki ad-string'i sınıfa eşler. Yeni senaryo eklemek
# yeni dosya yazıp bu dict'e bir satır eklemekten ibaret (spec § 4).
SCENARIO_REGISTRY: dict[str, type[FaultScenario]] = {
    "mechanical_wear": MechanicalWear,
}


def active_scenarios_at(
    windows: list[ScenarioWindow],
    device_elapsed_s: float,
) -> list[tuple[FaultScenario, ScenarioWindow]]:
    """`device_elapsed_s` anında aktif olan senaryo + pencere çiftlerini döndür.

    Aktiflik penceresi: `start_after_s ≤ device_elapsed_s < start_after_s + duration_s`
    (lower inclusive, upper exclusive). Senaryo class'ı her çağrıda registry'den
    yeni instance olarak inşa edilir (params YAML window'undan).

    Args:
        windows: Cihazın `DeviceConfig.scenarios` listesi.
        device_elapsed_s: Cihazın engine_boot_at'ten beri geçen süresi
            (`runtime.device_elapsed_s` property).

    Returns:
        Aktif olan (scenario_instance, window) çiftleri. Sırası `windows` listesinin
        sırasını korur — engine bu sırayla `modify` zincirler.

    Raises:
        KeyError: SCENARIO_REGISTRY'de bilinmeyen window.name.
    """
    active: list[tuple[FaultScenario, ScenarioWindow]] = []
    for window in windows:
        if not (window.start_after_s <= device_elapsed_s < window.start_after_s + window.duration_s):
            continue
        scenario_cls = SCENARIO_REGISTRY[window.name]
        scenario = scenario_cls(params=window.params)
        active.append((scenario, window))
    return active


__all__ = ["SCENARIO_REGISTRY", "active_scenarios_at", "FaultScenario"]

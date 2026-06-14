"""SensorFault arıza senaryosu (Faz 8 Iter 8.3 E, DOMAIN.md § E imkânsız-değer varyantı)."""
from __future__ import annotations

from typing import ClassVar

from simulator.scenarios.base import FaultScenario, ScenarioContext


class SensorFault(FaultScenario):
    """Sensör arızası: bir sensör (mast_position) aralıklı olarak FİZİKSEL İMKÂNSIZ değer üretir.

    Diğer sensörler normal kalır (sensör kendisi bozuk, makine sağlam → sağlamlık özelliği,
    spec § 2/§ 3b). State filtering YOK (sensör arızası harekete bağlı değil). Per-tick RNG
    (electrical_fault deseni): saf modify, sensör sırasından bağımsız.

    Params:
        spike_prob: float ∈ [0, 1] — her mast_position çağrısında imkânsız değer olasılığı. Tipik 0.3.
        impossible_value: float — fiziksel olarak imkânsız değer (örn. -500.0 mm; mast yer altında olamaz).
    """

    name: ClassVar[str] = "sensor_fault"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset({"spike_prob", "impossible_value"})

    def modify(self, sensor_name: str, clean_value: float, ctx: ScenarioContext) -> float:
        if sensor_name != "mast_position":
            return clean_value
        if ctx.runtime.rng.random() < self.params["spike_prob"]:
            return self.params["impossible_value"]
        return clean_value

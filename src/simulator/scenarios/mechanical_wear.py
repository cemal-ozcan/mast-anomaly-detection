"""MechanicalWear arıza senaryosu (spec § 9 A, DOMAIN.md sat. 78-83)."""
from __future__ import annotations

from typing import ClassVar

from simulator.config import DeviceState
from simulator.scenarios.base import FaultScenario, ScenarioContext


class MechanicalWear(FaultScenario):
    """Mekanik aşınma: motor enerjili durumlarda artan sürtünme ve titreşim.

    Aktif state'ler: RAISING + HOLDING. IDLE'da motor dönmez, LOWERING'de
    aşınma hareket yönüne bağlı değil → spec § 9 A bu state'leri kapsam dışı
    tutuyor.

    Params:
        severity: float ∈ (0, 1] — peak aşınma faktörü. Tipik 0.2 (%20).
        ramp_up_s: float > 0 — saniye, lineer ramp süresi
            (factor = elapsed/ramp_up * severity, capped at severity).
    """

    name: ClassVar[str] = "mechanical_wear"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset({"severity", "ramp_up_s"})

    _ACTIVE_STATES: ClassVar[frozenset[DeviceState]] = frozenset(
        {DeviceState.RAISING, DeviceState.HOLDING}
    )

    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        """Spec § 9 A formülünü uygula, aktif olmayan state'lerde identity döndür."""
        if ctx.runtime.state not in self._ACTIVE_STATES:
            return clean_value

        severity = self.params["severity"]
        ramp_up_s = self.params["ramp_up_s"]
        factor = min(1.0, ctx.scenario_elapsed_s / ramp_up_s) * severity

        if sensor_name == "motor_current":
            return clean_value * (1 + factor)
        if sensor_name == "mast_position":
            return clean_value / (1 + factor * 0.7)
        if sensor_name == "vibration":
            return clean_value * (1 + factor * 2)
        if sensor_name == "motor_temperature":
            return clean_value + factor * 8.0
        return clean_value

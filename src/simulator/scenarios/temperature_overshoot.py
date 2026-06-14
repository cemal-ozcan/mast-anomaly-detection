"""TemperatureOvershoot arıza senaryosu (Faz 8 Iter 8.3 F, DOMAIN.md § F)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from simulator.config import DeviceState
from simulator.scenarios.base import FaultScenario, ScenarioContext


class TemperatureOvershoot(FaultScenario):
    """Sıcaklık aşımı: motor enerjili durumlarda sıcaklık kritik eşiğin üstüne tırmanır.

    Sürekli yük / yetersiz soğutma. `modify` TOPLAMSAL: sensörün (tavanlı) temiz değerinin
    üstüne `min(max_overshoot_c, rate * scenario_elapsed_s)` ekler → sensör saf kalır, tavan
    kaldırılmaz (spec § 4). Aktif: RAISING + HOLDING (motor enerjili).

    Params:
        overshoot_rate_c_per_s: float > 0 — saniyede aşım artış hızı (°C/s). Tipik 0.8.
        max_overshoot_c: float > 0 — toplam aşım tavanı (°C). Tipik 60.
    """

    name: ClassVar[str] = "temperature_overshoot"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset(
        {"overshoot_rate_c_per_s", "max_overshoot_c"}
    )
    _ACTIVE_STATES: ClassVar[frozenset[DeviceState]] = frozenset(
        {DeviceState.RAISING, DeviceState.HOLDING}
    )

    def __init__(self, params: Mapping[str, float]) -> None:
        super().__init__(params)  # presence kontrolü (base)
        if self.params["overshoot_rate_c_per_s"] <= 0 or self.params["max_overshoot_c"] <= 0:
            raise ValueError(
                "TemperatureOvershoot: overshoot_rate_c_per_s ve max_overshoot_c > 0 olmalı "
                f"(alınan: rate={self.params['overshoot_rate_c_per_s']}, "
                f"max={self.params['max_overshoot_c']})"
            )

    def modify(self, sensor_name: str, clean_value: float, ctx: ScenarioContext) -> float:
        if ctx.runtime.state not in self._ACTIVE_STATES:
            return clean_value
        if sensor_name != "motor_temperature":
            return clean_value
        rate = self.params["overshoot_rate_c_per_s"]
        max_over = self.params["max_overshoot_c"]
        overshoot = min(max_over, rate * ctx.scenario_elapsed_s)
        return clean_value + overshoot

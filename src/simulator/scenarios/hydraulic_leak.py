"""HydraulicLeak arıza senaryosu (spec § 9 B, DOMAIN.md sat. 90-93)."""
from __future__ import annotations

from typing import ClassVar

from simulator.config import DeviceState
from simulator.scenarios.base import FaultScenario, ScenarioContext


class HydraulicLeak(FaultScenario):
    """Hidrolik kaçak: HOLDING'de basınç lineer düşer + mast pozisyonu yavaşça sarkar.

    Aktif state: SADECE HOLDING. RAISING'de pompa basıncı kaçağı maskeler;
    LOWERING'de basınç zaten düşüyor → modifiye yok (spec § 9 B notu).

    `runtime.elapsed_in_state_s` HOLDING filtresi altında "HOLDING'e girişten
    beri geçen süre" anlamına gelir; held_minutes = elapsed_in_state_s / 60.

    Params:
        leak_rate_bar_per_min: float > 0 — dakika başına basınç düşüş hızı.
            Tipik 5.0 (yavaş kaçak); 50.0 (hızlı kaçak).
        position_sag_mm: float > 0 — dakika başına pozisyon kayıp (mm).
            Tipik 2.0.
    """

    name: ClassVar[str] = "hydraulic_leak"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset(
        {"leak_rate_bar_per_min", "position_sag_mm"}
    )

    _PRESSURE_FLOOR_BAR: ClassVar[float] = 5.0

    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        """Spec § 9 B formülünü uygula; HOLDING dışında identity döndür."""
        if ctx.runtime.state != DeviceState.HOLDING:
            return clean_value

        held_minutes = ctx.runtime.elapsed_in_state_s / 60.0
        leak_rate = self.params["leak_rate_bar_per_min"]
        sag_rate = self.params["position_sag_mm"]

        if sensor_name == "hydraulic_pressure":
            pressure_drop = leak_rate * held_minutes
            return max(self._PRESSURE_FLOOR_BAR, clean_value - pressure_drop)
        if sensor_name == "mast_position":
            return clean_value - sag_rate * held_minutes
        return clean_value

"""ElectricalFault arıza senaryosu (spec § 9 C, DOMAIN.md sat. 102-106)."""
from __future__ import annotations

from typing import ClassVar

from simulator.scenarios.base import FaultScenario, ScenarioContext


class ElectricalFault(FaultScenario):
    """Elektriksel bağlantı sorunu: rastgele spike'lar + sürekli voltaj jitter.

    State filtering YOK — tüm DeviceState'lerde aktif (spec § 9 C: elektriksel
    sorun mekanik harekete bağlı değil). Pratikte RAISING/HOLDING'de daha gözle
    görülür çünkü motor enerjili.

    Per-sensor independent RNG: her `modify` çağrısı `runtime.rng.random()` ile
    spike kararı verir. Bu, modify pure (no scenario instance state) tutar ve
    sensor sırasından bağımsız çalışır. modify çağrı sırasında runtime.rng
    advance eder; engine'in noise stream'i ile interleave olur (per-device seed
    determinizmi korunur — same-seed regression test geçer).

    Params:
        spike_prob: float ∈ [0, 1] — her sensor modify çağrısı başına spike olasılığı.
            Tipik 0.05 (%5).
        voltage_jitter_std: float > 0 — non-spike durumda motor_voltage gauss jitter
            standart sapması. Tipik 0.6 (baseline noise 0.2'nin 3 katı).
    """

    name: ClassVar[str] = "electrical_fault"
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset(
        {"spike_prob", "voltage_jitter_std"}
    )

    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        """Spec § 9 C formülünü uygula; tüm state'lerde aktif."""
        rng = ctx.runtime.rng
        spike_prob = self.params["spike_prob"]
        voltage_jitter_std = self.params["voltage_jitter_std"]

        if rng.random() < spike_prob:
            if sensor_name == "motor_current":
                return clean_value + rng.uniform(-2.0, 4.0)
            if sensor_name == "motor_voltage":
                return clean_value + rng.uniform(-30.0, 30.0)
            return clean_value
        else:
            if sensor_name == "motor_voltage":
                return clean_value + rng.gauss(0.0, voltage_jitter_std)
            return clean_value

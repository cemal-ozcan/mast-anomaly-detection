"""FaultScenario ABC + ScenarioContext (Iter 4 senaryo altyapısı, spec § 9)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from simulator.runtime import DeviceRuntimeState


@dataclass(frozen=True)
class ScenarioContext:
    """Bir senaryo `modify` çağrısı için immutable bağlam.

    `scenario_elapsed_s` her senaryonun KENDİ `start_after_s`'inden ölçülür
    (spec § 8 — birden fazla senaryo aynı anda aktifse her birinin kendi
    geçen süresi vardır, tek paylaşılan değer değil).
    """

    runtime: DeviceRuntimeState
    scenario_elapsed_s: float


class FaultScenario(ABC):
    """Arıza senaryosu kontratı: sensor değerini state + elapsed'e göre modifiye eder.

    Alt sınıflar `_REQUIRED_PARAMS` frozenset'ini override ederek YAML'de
    beklenen anahtarları deklare eder; base `__init__` eksik anahtarı boot-time
    `ValueError` ile bildirir (spec § 11 early-exit).

    Per-senaryo state filtering: alt sınıfın `modify` metodu BAŞINDA inline
    `if ctx.runtime.state not in active_states: return clean_value` (spec § 9
    formülleri zaten bu pattern).
    """

    name: ClassVar[str]
    _REQUIRED_PARAMS: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, params: Mapping[str, float]):
        missing = self._REQUIRED_PARAMS - set(params)
        if missing:
            raise ValueError(
                f"{type(self).__name__}: eksik params: {sorted(missing)} "
                f"(beklenen: {sorted(self._REQUIRED_PARAMS)})"
            )
        self.params: Mapping[str, float] = params

    @abstractmethod
    def modify(
        self,
        sensor_name: str,
        clean_value: float,
        ctx: ScenarioContext,
    ) -> float:
        """Temiz fiziksel değeri (sensör formülü çıktısı) bu senaryoya göre modifiye et.

        Senaryo bu state'te aktif değilse `clean_value` aynen döndürülür.
        Senaryo bu sensörle ilgilenmiyorsa da `clean_value` aynen döndürülür.
        """

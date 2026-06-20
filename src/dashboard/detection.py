"""Tespit katmanı türetimi (saf — streamlit/DB import etmez).

Bir sensörü hangi katmanların izlediğini config'ten, bir uyarıyı hangi katmanın yakaladığını
rule_name'den türetir. Amaç: arkadaki çok-katmanlı analizi (kural + istatistik + füzyon) arayüzde
görünür kılmak. Uydurma yok — yalnız config + gerçek kural adları.
"""
from __future__ import annotations

from typing import Any

from detectors.config import DetectorConfig

LAYER_RULE = "Kural"
LAYER_STAT = "İstatistik"

# Kural adı → hedef sensör. None: sensör param'dan (frozen) ya da tüm bounds (out_of_range).
RULE_SENSOR: dict[str, str | None] = {
    "motor_temperature_high": "motor_temperature",
    "motor_current_high": "motor_current",
    "vibration_elevated": "vibration",
    "hydraulic_pressure_decline": "hydraulic_pressure",
    "motor_voltage_erratic": "motor_voltage",
    "sensor_frozen": None,
    "sensor_out_of_range": None,
}


def _rule_targets_sensor(rule_name: str, params: dict[str, Any], sensor: str) -> bool:
    """Bir kuralın (params'ıyla) verilen sensörü hedefleyip hedeflemediği."""
    if rule_name not in RULE_SENSOR:
        return False
    target = RULE_SENSOR[rule_name]
    if target is not None:
        return target == sensor
    if rule_name == "sensor_frozen":
        return bool(params.get("sensor") == sensor)
    if rule_name == "sensor_out_of_range":
        return sensor in (params.get("bounds") or {})
    return False


def watching_layers(config: DetectorConfig | None, sensor: str) -> list[str]:
    """Sensörü izleyen tespit katmanları (sıra: Kural, İstatistik); config yoksa boş.

    Kural: aktif bir kural sensörü hedefliyorsa. İstatistik: aktif bir statistical dedektörün
    `sensors` param'ı sensörü içeriyorsa (param yok/boş → tüm sensörler).
    """
    if config is None:
        return []
    layers: list[str] = []
    if any(r.enabled and _rule_targets_sensor(r.name, r.params, sensor) for r in config.rules):
        layers.append(LAYER_RULE)
    stat = config.statistical
    if stat is not None:
        for d in stat.detectors:
            if not d.enabled:
                continue
            sensors = d.params.get("sensors")
            if not sensors or sensor in sensors:
                layers.append(LAYER_STAT)
                break
    return layers


def catching_layer(rule_name: str) -> str:
    """Uyarıyı yakalayan katman: fused→Çoklu katman; three_sigma/iqr→İstatistik; aksi→Kural."""
    if rule_name.startswith("fused("):
        return "Çoklu katman"
    if rule_name.startswith(("three_sigma:", "iqr:")):
        return LAYER_STAT
    return LAYER_RULE

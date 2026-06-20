"""Seviye-eşikli sensörlerin radar bölgelerini config'ten okur (saf — streamlit/DB import etmez).

Dürüstlük: yalnız detector'ın SEVİYE eşiği kullandığı sensörlere (sıcaklık/akım/titreşim) band
üretir; slope (hidrolik), varyans (voltaj) ve kuralsız (mast_position) sensörlerde None döner —
sahte yatay bant uydurulmaz. Eşikler config = tek hakikat (hard-code yok).
"""
from __future__ import annotations

from dataclasses import dataclass

from detectors.config import DetectorConfig

# sensör → (kural adı, uyarı-param, kritik-param). Yalnız seviye-eşikli sensörler.
SENSOR_LEVEL_RULES: dict[str, tuple[str, str, str]] = {
    "motor_temperature": ("motor_temperature_high", "critical_threshold_c", "trip_c"),
    "motor_current": ("motor_current_high", "threshold_a", "trip_a"),
    "vibration": ("vibration_elevated", "threshold_g", "trip_g"),
}


@dataclass(frozen=True)
class LevelBand:
    """Bir sensörün seviye-eşiği: uyarı (warn) ve kritik (trip) sınırı."""

    warn: float
    trip: float


def level_band(config: DetectorConfig | None, sensor: str) -> LevelBand | None:
    """Sensörün seviye-bandını config'ten üretir; seviye-eşikli değilse/kural yoksa None.

    Args:
        config: Yüklenmiş DetectorConfig veya None (config okunamadıysa).
        sensor: Sensör adı.

    Returns:
        LevelBand(warn, trip) — sensör seviye-eşikli + kural enabled + iki param mevcut +
        trip > warn ise; aksi halde None.
    """
    if config is None or sensor not in SENSOR_LEVEL_RULES:
        return None
    rule_name, warn_key, trip_key = SENSOR_LEVEL_RULES[sensor]
    rule = next((r for r in config.rules if r.name == rule_name and r.enabled), None)
    if rule is None:
        return None
    try:
        warn = float(rule.params[warn_key])
        trip = float(rule.params[trip_key])
    except (KeyError, TypeError, ValueError):
        return None
    if trip <= warn:
        return None
    return LevelBand(warn=warn, trip=trip)

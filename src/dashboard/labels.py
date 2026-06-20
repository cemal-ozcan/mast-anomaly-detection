"""İnsan-okur Türkçe etiketler: sensör/state/kural/cihaz adlarını ekranda düz Türkçeye çevirir.

SAF — yalnız stdlib. Amaç: yönetici/firma sunumunda kod kimlikleri (motor_current, raising,
hydraulic_pressure_decline) yerine anlaşılır Türkçe ("Motor Akımı", "Yükseliyor", "Hidrolik basınç
düşüyor") göstermek — "bilmeyen biri bile ekrana bakınca anlasın". Bilinmeyen anahtar → güvenli
fallback (ham ad), böylece yeni kural/sensör eklenince çökme olmaz.
"""
from __future__ import annotations

SENSOR_LABELS: dict[str, str] = {
    "motor_current": "Motor Akımı",
    "motor_voltage": "Motor Voltajı",
    "hydraulic_pressure": "Hidrolik Basınç",
    "motor_temperature": "Motor Sıcaklığı",
    "mast_position": "Mast Konumu",
    "vibration": "Titreşim",
}

STATE_LABELS: dict[str, str] = {
    "raising": "Yükseliyor",
    "lowering": "İniyor",
    "holding": "Sabit",
    "idle": "Beklemede",
}

# Kural adı → düz Türkçe "ne oluyor" (kestirimci + sensör-sağlığı).
RULE_LABELS: dict[str, str] = {
    "motor_temperature_high": "Motor aşırı ısındı",
    "motor_current_high": "Motor akımı yüksek",
    "vibration_elevated": "Titreşim arttı",
    "hydraulic_pressure_decline": "Hidrolik basınç düşüyor",
    "motor_voltage_erratic": "Motor voltajı dengesiz",
    "sensor_out_of_range": "Sensör geçersiz veri veriyor",
    "sensor_frozen": "Sensör donmuş",
}

BADGE_LABELS: dict[str, str] = {
    "ok": "SAĞLIKLI", "warning": "DİKKAT", "high": "YÜKSEK", "critical": "KRİTİK"
}

# Sensör OKUMASI durumu (mast "SAĞLIKLI", sensör "NORMAL" daha doğal). DİKKAT/KRİTİK ortak.
SENSOR_STATUS_LABELS: dict[str, str] = {"ok": "NORMAL", "warning": "DİKKAT", "critical": "KRİTİK"}


def sensor_label(sensor: str) -> str:
    """Sensör kod adını Türkçeye çevirir (bilinmeyen → ham ad)."""
    return SENSOR_LABELS.get(sensor, sensor)


def state_label(state: str) -> str:
    """Cihaz state kodunu Türkçeye çevirir (bilinmeyen → ham ad)."""
    return STATE_LABELS.get(state, state)


def device_label(device_id: str) -> str:
    """`device_001` → `Cihaz 1` (baştaki sıfırlar atılır; eşleşmezse ham id)."""
    prefix = "device_"
    if device_id.startswith(prefix):
        suffix = device_id[len(prefix):]
        return f"Cihaz {int(suffix)}" if suffix.isdigit() else f"Cihaz {suffix}"
    return device_id


def badge_label(badge: str) -> str:
    """ok/warning/critical → SAĞLIKLI/DİKKAT/KRİTİK (bilinmeyen → ham)."""
    return BADGE_LABELS.get(badge, badge)


def sensor_status_label(badge: str) -> str:
    """Sensör rozetini (ok/warning/critical) okuma-durumuna çevirir (bilinmeyen → ham)."""
    return SENSOR_STATUS_LABELS.get(badge, badge)


# Kural adı → düz Türkçe "ne anlama geliyor" (yöneticiye/teknisyene açıklama).
RULE_EXPLANATION: dict[str, str] = {
    "motor_temperature_high": "Motor aşırı ısınıyor; soğutma yetersiz ya da aşırı yük olabilir.",
    "motor_current_high": "Motor normalden fazla akım çekiyor; mekanik direnç/aşınma işareti olabilir.",
    "vibration_elevated": "Titreşim normalin üstünde; gevşeklik, dengesizlik ya da rulman aşınması olabilir.",
    "hydraulic_pressure_decline": "Hidrolik basınç düşüyor; sızıntı ya da pompa zayıflığı olabilir.",
    "motor_voltage_erratic": "Motor voltajı dengesiz; besleme ya da bağlantı sorunu olabilir.",
    "sensor_out_of_range": "Sensör imkânsız bir değer veriyor; sensör ya da kablo arızası.",
    "sensor_frozen": "Sensör değeri hiç değişmiyor; sensör donmuş/arızalı olabilir.",
}


def rule_explanation(rule_name: str) -> str:
    """Kural adını düz Türkçe açıklamaya çevirir (ne anlama geliyor); bilinmeyen → boş."""
    if rule_name in RULE_EXPLANATION:
        return RULE_EXPLANATION[rule_name]
    if rule_name.startswith("fused("):
        return "Birden çok belirti birlikte görülüyor; cihazı incelemek gerekir."
    if rule_name.startswith(("three_sigma:", "iqr:")):
        return "Değer, öğrenilen normal davranışından belirgin saptı."
    return ""


def rule_label(rule_name: str) -> str:
    """Kural adını düz Türkçe arıza ifadesine çevirir.

    Doğrudan eşleşme; `fused(N)` → "Çoklu anormallik"; `three_sigma:X`/`iqr:X` → "<Sensör> olağandışı";
    bilinmeyen → ham ad (fallback).
    """
    if rule_name in RULE_LABELS:
        return RULE_LABELS[rule_name]
    if rule_name.startswith("fused("):
        return "Çoklu anormallik"
    for prefix in ("three_sigma:", "iqr:"):
        if rule_name.startswith(prefix):
            return f"{sensor_label(rule_name[len(prefix):])} olağandışı"
    return rule_name

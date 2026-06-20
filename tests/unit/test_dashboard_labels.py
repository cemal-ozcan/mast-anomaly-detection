"""dashboard.labels — kod kimliği → düz Türkçe etiket testleri (yönetici-dostu görünüm)."""
from __future__ import annotations

from dashboard.labels import (
    badge_label,
    device_label,
    rule_label,
    sensor_label,
    state_label,
)


def test_sensor_label_known_and_fallback() -> None:
    assert sensor_label("motor_temperature") == "Motor Sıcaklığı"
    assert sensor_label("hydraulic_pressure") == "Hidrolik Basınç"
    assert sensor_label("bilinmeyen") == "bilinmeyen"  # fallback ham ad


def test_state_label() -> None:
    assert state_label("raising") == "Yükseliyor"
    assert state_label("idle") == "Beklemede"
    assert state_label("xyz") == "xyz"


def test_device_label() -> None:
    assert device_label("device_001") == "Cihaz 001"
    assert device_label("device_006") == "Cihaz 006"
    assert device_label("baska") == "baska"


def test_badge_label() -> None:
    assert badge_label("ok") == "SAĞLIKLI"
    assert badge_label("warning") == "DİKKAT"
    assert badge_label("critical") == "KRİTİK"


def test_rule_label_direct() -> None:
    assert rule_label("hydraulic_pressure_decline") == "Hidrolik basınç düşüyor"
    assert rule_label("motor_voltage_erratic") == "Motor voltajı dengesiz"
    assert rule_label("sensor_out_of_range") == "Sensör geçersiz veri veriyor"


def test_rule_label_fused_and_statistical() -> None:
    assert rule_label("fused(2)") == "Çoklu anormallik"
    assert rule_label("three_sigma:motor_current") == "Motor Akımı olağandışı"
    assert rule_label("iqr:hydraulic_pressure") == "Hidrolik Basınç olağandışı"
    assert rule_label("bilinmeyen_kural") == "bilinmeyen_kural"  # fallback


def test_sensor_status_label() -> None:
    from dashboard.labels import sensor_status_label

    assert sensor_status_label("ok") == "NORMAL"
    assert sensor_status_label("warning") == "DİKKAT"
    assert sensor_status_label("critical") == "KRİTİK"
    assert sensor_status_label("bilinmeyen") == "bilinmeyen"  # fallback

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
    assert device_label("device_001") == "Cihaz 1"
    assert device_label("device_006") == "Cihaz 6"
    assert device_label("device_012") == "Cihaz 12"
    assert device_label("baska") == "baska"


def test_badge_label() -> None:
    assert badge_label("ok") == "SAĞLIKLI"
    assert badge_label("warning") == "DİKKAT"
    assert badge_label("critical") == "KRİTİK"


def test_rule_label_direct() -> None:
    assert rule_label("hydraulic_pressure_decline") == "Hidrolik basınç düşüyor"
    assert rule_label("motor_voltage_erratic") == "Motor voltajı dengesiz"
    assert rule_label("sensor_out_of_range") == "Sensör geçersiz veri veriyor"


def test_alert_metric_phrase() -> None:
    from dashboard.labels import alert_metric_phrase

    assert alert_metric_phrase("motor_temperature_high", 150.0, "celsius").startswith("ölçülen 150")
    v = alert_metric_phrase("motor_voltage_erratic", 3.59, "V")
    assert "dalgalanma" in v and "3.59" in v and "ölçülen" not in v  # std, seviye değil
    h = alert_metric_phrase("hydraulic_pressure_decline", -6.73, "bar")
    assert "düşüş hızı" in h and "bar/dk" in h and "6.73" in h
    assert alert_metric_phrase("fused(3)", 10.0, "A").startswith("ölçülen 10")


def test_rule_explanation() -> None:
    from dashboard.labels import rule_explanation

    assert "voltaj" in rule_explanation("motor_voltage_erratic").lower()
    assert rule_explanation("fused(2)") != ""
    assert "saptı" in rule_explanation("three_sigma:motor_current")
    assert rule_explanation("bilinmeyen") == ""


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

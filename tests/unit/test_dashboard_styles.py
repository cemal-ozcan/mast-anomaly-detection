"""dashboard.styles saf CSS + HTML-builder testleri (Clean Corporate yeniden tasarım)."""
from __future__ import annotations

from alerts.models import Alert
from dashboard.fleet import DeviceHealth
from dashboard.styles import APP_CSS, header_html


def test_app_css_nonempty_and_hides_chrome() -> None:
    assert isinstance(APP_CSS, str) and len(APP_CSS) > 100
    # Streamlit chrome gizleme + açık zemin zorlama selektörleri.
    assert "#MainMenu" in APP_CSS
    assert 'data-testid="stToolbar"' in APP_CSS or "stToolbar" in APP_CSS
    assert "footer" in APP_CSS
    assert "#ffffff" in APP_CSS or "#f8fafc" in APP_CSS


def test_header_html_contains_brand_and_clock() -> None:
    html = header_html("14:32:05")
    assert "MastGuard" in html
    assert "14:32:05" in html
    assert "mg-header" in html


def test_kpi_card_tone_classes() -> None:
    from dashboard.styles import kpi_card_html

    assert "mg-kpi--critical" in kpi_card_html("Kritik", "1", "critical")
    assert "mg-kpi--warning" in kpi_card_html("Açık", "4", "warning")
    n = kpi_card_html("Cihaz", "6", "neutral")
    assert "mg-kpi--critical" not in n and "mg-kpi--warning" not in n
    assert ">6<" in n and "Cihaz" in n


def test_kpis_html_tone_from_counts() -> None:
    from dashboard.fleet import FleetKpis
    from dashboard.styles import kpis_html

    html = kpis_html(FleetKpis(device_count=6, open_alert_count=4, critical_alert_count=1,
                               last_detection="1 dk önce"))
    assert "mg-kpis" in html
    assert "mg-kpi--critical" in html  # kritik>0
    assert "1 dk önce" in html


def test_kpis_html_empty_last_detection() -> None:
    from dashboard.fleet import FleetKpis
    from dashboard.styles import kpis_html

    html = kpis_html(FleetKpis(device_count=6, open_alert_count=0, critical_alert_count=0,
                               last_detection="—"))
    assert "Henüz yok" in html  # boş "—" dostça gösterilir
    assert "mg-kpi--critical" not in html


def _health(
    badge: str = "ok", highlighted: bool = False, top_rule: str | None = None, n: int = 0
) -> DeviceHealth:
    from dashboard.fleet import SensorSnapshot

    return DeviceHealth(
        device_id="device_004", badge=badge, state="holding",
        snapshots=(SensorSnapshot("motor_voltage", 22.79, "V", highlighted),
                   SensorSnapshot("motor_current", 0.53, "A", False)),
        open_alert_count=n, top_rule=top_rule,
    )


def test_device_card_problem_plain_turkish() -> None:
    from dashboard.styles import device_card_html

    h = device_card_html(_health(badge="critical", n=1, top_rule="motor_voltage_erratic"))
    assert "mg-card--critical" in h and "mg-badge--critical" in h
    assert "Cihaz 004" in h  # device_id → insan adı
    assert "Sabit" in h  # state "holding" → Türkçe
    assert "KRİTİK" in h  # badge label
    assert "Motor voltajı dengesiz" in h  # top_rule → düz Türkçe sorun
    assert "mg-problem" in h
    # Ham sensör sayıları KART'ta YOK (sade, yönetici-dostu).
    assert "22.79" not in h and "motor_voltage_erratic" not in h


def test_device_card_ok_shows_no_problem() -> None:
    from dashboard.styles import device_card_html

    h = device_card_html(_health(badge="ok", n=0, top_rule=None))
    assert "mg-badge--ok" in h and "SAĞLIKLI" in h
    assert "mg-problem" not in h and "Sorun yok" in h


def test_fleet_html_wraps_grid() -> None:
    from dashboard.styles import fleet_html

    assert 'class="mg-fleet"' in fleet_html([_health(), _health()])


def _alert(severity: str = "critical", desc: str = "motor_voltage std 4.77V eşik <x>") -> Alert:
    return Alert(id=1, device_id="device_004", rule_name="motor_voltage_erratic", sensor="motor_voltage",
                 severity=severity, score=0.94, window_start="2026-06-19T12:55:00.000Z",
                 window_end="2026-06-19T12:57:29.854Z", value=4.77, description=desc,
                 created_at="2026-06-19T12:57:29.854Z", status="active", acknowledged_at=None,
                 resolved_at=None, clean_streak=0, rule_set="motor_voltage_erratic")


def test_alert_card_pill_and_escape() -> None:
    from datetime import UTC, datetime

    from dashboard.styles import alert_card_html

    now = datetime(2026, 6, 19, 12, 58, 0, tzinfo=UTC)
    h = alert_card_html(_alert(severity="critical"), now)
    assert "mg-pill--critical" in h and "mg-alert--critical" in h
    assert "Cihaz 004" in h  # device_id → insan adı
    assert "Motor voltajı dengesiz" in h  # rule → düz Türkçe başlık
    assert "&lt;x&gt;" in h  # ham açıklama (soluk detay) html.escape'lendi
    assert "<x>" not in h


def test_alerts_section_empty() -> None:
    from datetime import UTC, datetime

    from dashboard.styles import alerts_section_html

    now = datetime(2026, 6, 19, 12, 58, 0, tzinfo=UTC)
    h = alerts_section_html("Arıza Uyarıları", [], now, "Açık arıza uyarısı yok.")
    assert "Açık arıza uyarısı yok." in h and "mg-empty" in h
    assert "Arıza Uyarıları" in h


def test_alerts_section_lists_alerts() -> None:
    from datetime import UTC, datetime

    from dashboard.styles import alerts_section_html

    now = datetime(2026, 6, 19, 12, 58, 0, tzinfo=UTC)
    h = alerts_section_html("Arıza Uyarıları", [_alert()], now, "yok")
    assert "Cihaz 004" in h and "mg-alert" in h


def test_fleet_summary_counts_and_tone() -> None:
    from dashboard.styles import fleet_summary_html

    fleet = [_health(badge="ok"), _health(badge="ok"), _health(badge="warning"),
             _health(badge="critical")]
    h = fleet_summary_html(fleet)
    assert "4 masttan" in h and "2'i sağlıklı" in h
    assert "1'i dikkat gerektiriyor" in h and "1'i KRİTİK" in h
    assert "mg-summary--critical" in h  # en kötü ton


def test_panel_header_html_status_and_escape() -> None:
    from dashboard.styles import panel_header_html

    h = panel_header_html("Motor Sıcaklığı", "KRİTİK", "critical", "76 °C",
                          "Uyarı 95 · Kritik 130 <x>")
    assert "mg-panel" in h
    assert "Motor Sıcaklığı" in h
    assert "KRİTİK" in h
    assert "mg-badge--critical" in h  # mevcut pill renk sınıfı yeniden kullanılır
    assert "76 °C" in h
    assert "&lt;x&gt;" in h and "<x>" not in h  # meta html.escape'li


def test_panel_header_html_ok_uses_ok_class() -> None:
    from dashboard.styles import panel_header_html

    h = panel_header_html("Titreşim", "NORMAL", "ok", "0.12 g", "Uyarı 0.37 · Kritik 0.5")
    assert "mg-badge--ok" in h and "NORMAL" in h

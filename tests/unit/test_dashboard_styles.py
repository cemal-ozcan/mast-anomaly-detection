"""dashboard.styles saf CSS + HTML-builder testleri (Clean Corporate yeniden tasarım)."""
from __future__ import annotations

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


def test_device_card_badge_and_strip() -> None:
    from dashboard.styles import device_card_html

    h = device_card_html(_health(badge="critical", n=1, top_rule="motor_voltage_erratic"))
    assert "mg-card--critical" in h and "mg-badge--critical" in h
    assert "device_004" in h and "holding" in h
    assert "motor_voltage" in h and "22.79" in h  # metrik değer, kelime bölünmesi yok
    assert "motor_voltage_erratic" in h  # top rule
    assert "1 açık" in h


def test_device_card_highlighted_value_class() -> None:
    from dashboard.styles import device_card_html

    assert "mg-v--hot" in device_card_html(_health(badge="critical", highlighted=True))


def test_device_card_ok_no_toprule() -> None:
    from dashboard.styles import device_card_html

    h = device_card_html(_health(badge="ok", n=0, top_rule=None))
    assert "mg-badge--ok" in h and "mg-toprule" not in h


def test_fleet_html_wraps_grid() -> None:
    from dashboard.styles import fleet_html

    assert 'class="mg-fleet"' in fleet_html([_health(), _health()])

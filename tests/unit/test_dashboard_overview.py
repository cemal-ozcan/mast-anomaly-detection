"""dashboard.overview saf builder testleri (Operasyon Merkezi açılış)."""
from __future__ import annotations

from datetime import UTC, datetime

from alerts.models import Alert
from dashboard.fleet import DeviceHealth, SensorSnapshot


def _h(badge: str, *, oac: int = 0, rule: str | None = None,
       highlighted: str | None = None) -> DeviceHealth:
    snaps = (SensorSnapshot("motor_current", 1.0, "A", highlighted == "motor_current"),
             SensorSnapshot("vibration", 0.1, "g", highlighted == "vibration"))
    return DeviceHealth("device_001", badge, "idle", snaps, oac, rule)


def _alert(status: str = "active", severity: str = "warning",
           created_at: str = "2026-06-20T12:00:00.000Z", device: str = "device_003",
           rule: str = "hydraulic_pressure_decline") -> Alert:
    return Alert(id=1, device_id=device, rule_name=rule, sensor="hydraulic_pressure",
                 severity=severity, score=0.5, window_start="s", window_end="e", value=1.0,
                 description="d", created_at=created_at, status=status, acknowledged_at=None,
                 resolved_at=None)


# ---- hero (Task 3) ----

def test_summarize_fleet() -> None:
    from dashboard.overview import summarize_fleet
    s = summarize_fleet([_h("ok"), _h("ok"), _h("warning"), _h("critical")])
    assert (s.total, s.ok, s.warning, s.critical, s.worst) == (4, 2, 1, 1, "critical")
    assert summarize_fleet([_h("ok")]).worst == "ok"


def test_info_badge_escape() -> None:
    from dashboard.overview import info_badge_html
    h = info_badge_html("Açıklama <x>")
    assert "mg-info" in h and 'data-tip="Açıklama &lt;x&gt;"' in h


def test_section_html_with_and_without_tip() -> None:
    from dashboard.overview import section_html
    plain = section_html("Mastlar")
    assert plain == '<div class="mg-section">Mastlar</div>'
    tipped = section_html("Son 24 saat", "Yakalanan olaylar.")
    assert "mg-section" in tipped and "Son 24 saat" in tipped
    assert "mg-info" in tipped and 'data-tip="Yakalanan olaylar."' in tipped


def test_health_ring_svg() -> None:
    from dashboard.overview import health_ring_svg, summarize_fleet
    svg = health_ring_svg(summarize_fleet([_h("ok"), _h("ok"), _h("critical"), _h("critical")]))
    assert "mg-ring" in svg and "2/4" in svg
    assert 'stroke-dasharray="50 100"' in svg


def test_hero_html_states() -> None:
    from dashboard.overview import hero_html, summarize_fleet
    ok = hero_html(summarize_fleet([_h("ok"), _h("ok")]), 2, 12, "2 sn önce", "4g 12sa")
    assert "TÜM FİLO SAĞLIKLI" in ok and "<b>2</b> mast" in ok and "<b>12</b> sensör" in ok
    mixed = hero_html(summarize_fleet([_h("critical"), _h("warning"), _h("ok")]), 3, 18,
                      "1 sn önce", "4g")
    assert "1 kritik" in mixed and "1 dikkat" in mixed and "1 sağlıklı" in mixed
    assert "mg-hero--critical" in mixed


# ---- coverage + timeline (Task 4) ----

def test_coverage_stats_and_html() -> None:
    from dashboard.overview import coverage_html, coverage_stats
    stats = coverage_stats(6, 36, 36, "2 sn önce", 3)
    assert len(stats) == 5 and stats[0].label == "İzlenen Mast"
    h = coverage_html(stats)
    assert "mg-stats" in h and "İzlenen Mast" in h and "data-tip=" in h and ">36<" in h


def test_timeline_events() -> None:
    from dashboard.overview import timeline_events
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    evs = timeline_events([
        _alert(status="active", severity="critical", created_at="2026-06-20T11:00:00.000Z"),
        _alert(status="resolved", created_at="2026-06-20T10:00:00.000Z"),
        _alert(status="acknowledged", created_at="2026-06-20T09:00:00.000Z"),
        _alert(status="active", created_at="2026-06-18T12:00:00.000Z"),  # 24s dışı → elenir
    ], now)
    assert len(evs) == 3
    assert evs[0].tone == "critical" and "sürüyor" in evs[0].text
    assert any(e.tone == "ok" and "çözüldü" in e.text for e in evs)
    assert any(e.tone == "ack" and "teknisyen onayı" in e.text for e in evs)


def test_timeline_html_empty() -> None:
    from dashboard.overview import timeline_events, timeline_html
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    assert "olay yok" in timeline_html(timeline_events([], now))


# ---- sparkline + fleet card (Task 5) ----

def test_sparkline_svg() -> None:
    from dashboard.overview import sparkline_svg
    assert sparkline_svg([]) == ""
    svg = sparkline_svg([0.0, 1.0, 0.5, 2.0])
    assert svg.startswith("<svg") and "polyline" in svg and "points=" in svg


def test_fleet_card_clickable_and_status() -> None:
    from dashboard.overview import fleet_card_html
    crit = fleet_card_html(
        _h("critical", oac=1, rule="hydraulic_pressure_decline", highlighted="vibration"),
        [1.0, 2.0, 3.0], "12 bar")
    assert 'href="?dev=device_001"' in crit and 'target="_self"' in crit
    assert "mg-card--critical" in crit and "Cihaz 1" in crit and "12 bar" in crit
    ok = fleet_card_html(_h("ok"), [1.0, 1.1], "")
    assert "incele" in ok and "SAĞLIKLI" in ok


def test_fleet_grid_wraps() -> None:
    from dashboard.overview import fleet_grid_html
    assert fleet_grid_html(["<a></a>", "<a></a>"]).startswith('<div class="mg-fleet">')

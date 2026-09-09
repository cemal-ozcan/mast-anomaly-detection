# Dashboard — Açılış "Operasyon Merkezi" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Açılış (Filo Genel Bakış) sayfasını "Operasyon Merkezi"ne çevir: sağlık hero'su (halka) + kapsam/ölçek şeridi (info tooltip) + sinyal-öncelikli tıklanır filo ızgarası (inline-SVG sparkline) + son-24s olay timeline; ayrıca Cihaz Detayı radar zone'larını belirginleştir.

**Architecture:** Yeni saf `overview.py` (hero/stats/timeline/sparkline/fleet-card HTML builder'ları — streamlit/DB import etmez). `fleet.py` saf sıralama+temsilci-sensör. 2 yeni salt-okuma repository metodu. `app.py` `_render_overview` yeniden yazılır + `?dev=` query-param drill-down. Sparkline = saf inline SVG (Altair değil; HTML karta gömülür). Veri/tespit/gözlem-modu DEĞİŞMEZ.

**Tech Stack:** Python 3.11, Streamlit 1.36, Altair 5.5, SQLAlchemy Core, pytest, mypy strict, ruff.

## Global Constraints
- Streamlit-native (React YOK); yeni ağır bağımlılık YOK.
- Veri/tespit/füzyon/reconciliation/migration/gözlem-modu DEĞİŞMEZ; dashboard yalnız okur + ack yazar.
- Sayı/eşik DB/config'ten (uydurma yok). Sektör-nötr. Serbest metin `html.escape`.
- Yeni repository metodları SALT-OKUMA.
- Gate (her task): `.venv/bin/python -m pytest -q` + `.venv/bin/python -m mypy src/dashboard src/storage tests/unit` + `ruff check src/dashboard src/storage tests/unit`. Ortam: subagent Bash/Write izinsiz → controller-inline + salt-okunur reviewer. Dal: `dashboard-redesign-clean-corporate`.

---

### Task 1: repository — 2 salt-okuma metodu

**Files:** Modify `src/storage/repository.py` · Test `tests/unit/test_storage_overview_reads.py` (yeni)

**Interfaces — Produces:** `earliest_telemetry_timestamp() -> str | None`, `count_anomalies_since(since: str) -> int`.

- [ ] **Step 1: Failing test** — `tests/unit/test_storage_overview_reads.py`:
```python
"""Açılış (Operasyon Merkezi) için salt-okuma repository metodları."""
from __future__ import annotations

from sqlalchemy import Engine

from detectors.base import Anomaly
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository


def _reading(ts: str) -> IngestedReading:
    return IngestedReading("device_001", "motor_current", ts, "idle", 1.0, "A")


def _anomaly() -> Anomaly:
    return Anomaly("device_001", "motor_current_high", "motor_current", "high", 0.5,
                   "2026-06-20T11:59:00.000Z", "2026-06-20T12:00:00.000Z", 10.0, "d")


def test_earliest_telemetry_timestamp(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    assert repo.earliest_telemetry_timestamp() is None
    repo.insert(_reading("2026-06-20T10:00:00.000Z"))
    repo.insert(_reading("2026-06-20T09:00:00.000Z"))
    assert repo.earliest_telemetry_timestamp() == "2026-06-20T09:00:00.000Z"


def test_count_anomalies_since(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    assert repo.count_anomalies_since("2026-06-20T00:00:00.000Z") == 0
    repo.insert_anomaly(_anomaly(), "2026-06-20T12:00:00.000Z", "motor_current_high")
    repo.insert_anomaly(_anomaly(), "2026-06-19T12:00:00.000Z", "motor_current_high")
    assert repo.count_anomalies_since("2026-06-20T00:00:00.000Z") == 1
```
> `migrated_engine` fixture mevcut (StaticPool in-memory, conftest).

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/unit/test_storage_overview_reads.py -q` → AttributeError.

- [ ] **Step 3: Implement** — `src/storage/repository.py`, `count()` metodunun altına ekle:
```python
    def earliest_telemetry_timestamp(self) -> str | None:
        """En eski telemetri timestamp'i (izleme süresi için); veri yoksa None."""
        with self._engine.connect() as conn:
            return conn.execute(select(func.min(telemetry.c.timestamp))).scalar()

    def count_anomalies_since(self, since: str) -> int:
        """created_at >= since olan anomali sayısı (son-24s tespit KPI'si)."""
        stmt = select(func.count()).select_from(anomalies).where(anomalies.c.created_at >= since)
        with self._engine.connect() as conn:
            return int(conn.execute(stmt).scalar_one())
```
(`func`, `select`, `telemetry`, `anomalies` zaten import edilmiş.)

- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Gate + commit** — `git commit -m "feat(storage): earliest_telemetry_timestamp + count_anomalies_since (açılış KPI'leri, salt-okuma)"`

---

### Task 2: fleet — sıralama + temsilci sensör

**Files:** Modify `src/dashboard/fleet.py` · Test `tests/unit/test_dashboard_fleet.py`

**Interfaces — Produces:** `sort_fleet_by_severity(fleet) -> list[DeviceHealth]`, `representative_sensor(health) -> str`.

- [ ] **Step 1: Failing test** — `tests/unit/test_dashboard_fleet.py` sonuna ekle:
```python
def _health(device: str, badge: str, highlighted_sensor: str | None = None):
    from dashboard.fleet import DeviceHealth, SensorSnapshot
    snaps = (SensorSnapshot("motor_current", 1.0, "A", highlighted_sensor == "motor_current"),
             SensorSnapshot("vibration", 0.1, "g", highlighted_sensor == "vibration"))
    return DeviceHealth(device, badge, "idle", snaps, 1 if highlighted_sensor else 0, None)


def test_sort_fleet_by_severity() -> None:
    from dashboard.fleet import sort_fleet_by_severity
    fleet = [_health("device_002", "ok"), _health("device_001", "critical"),
             _health("device_003", "warning"), _health("device_004", "critical")]
    order = [h.device_id for h in sort_fleet_by_severity(fleet)]
    assert order == ["device_001", "device_004", "device_003", "device_002"]


def test_representative_sensor() -> None:
    from dashboard.fleet import representative_sensor
    assert representative_sensor(_health("d", "warning", "vibration")) == "vibration"
    assert representative_sensor(_health("d", "ok")) == "motor_current"
```

- [ ] **Step 2: Run, expect FAIL** (ImportError).
- [ ] **Step 3: Implement** — `src/dashboard/fleet.py` sonuna:
```python
def sort_fleet_by_severity(fleet: list[DeviceHealth]) -> list[DeviceHealth]:
    """Filoyu duruma göre sıralar: critical > warning > ok, eşitlikte device_id (management by exception)."""
    rank = {BADGE_CRITICAL: 0, BADGE_WARNING: 1, BADGE_OK: 2}
    return sorted(fleet, key=lambda h: (rank.get(h.badge, 3), h.device_id))


def representative_sensor(health: DeviceHealth) -> str:
    """Kart sparkline'ı için temsilci sensör: açık-uyarılı (vurgulu) sensör; yoksa motor_current."""
    for snap in health.snapshots:
        if snap.highlighted:
            return snap.sensor
    return "motor_current"
```

- [ ] **Step 4: Run PASS. Step 5: Gate + commit** — `"feat(dashboard): fleet sort_fleet_by_severity + representative_sensor (sinyal-öncelikli ızgara)"`

---

### Task 3: overview.py — hero (summary + halka + hero_html + info)

**Files:** Create `src/dashboard/overview.py` · Test `tests/unit/test_dashboard_overview.py` (yeni)

**Interfaces — Produces:** `FleetSummary`, `summarize_fleet`, `info_badge_html`, `health_ring_svg`, `hero_html`.

- [ ] **Step 1: Failing test** — `tests/unit/test_dashboard_overview.py`:
```python
"""dashboard.overview saf builder testleri (Operasyon Merkezi açılış)."""
from __future__ import annotations

from dashboard.fleet import DeviceHealth


def _h(badge: str) -> DeviceHealth:
    return DeviceHealth("device_001", badge, "idle", (), 0, None)


def test_summarize_fleet() -> None:
    from dashboard.overview import summarize_fleet
    s = summarize_fleet([_h("ok"), _h("ok"), _h("warning"), _h("critical")])
    assert (s.total, s.ok, s.warning, s.critical, s.worst) == (4, 2, 1, 1, "critical")
    assert summarize_fleet([_h("ok")]).worst == "ok"


def test_info_badge_escape() -> None:
    from dashboard.overview import info_badge_html
    h = info_badge_html("Açıklama <x>")
    assert "mg-info" in h and 'data-tip="Açıklama &lt;x&gt;"' in h


def test_health_ring_svg() -> None:
    from dashboard.overview import health_ring_svg, summarize_fleet
    svg = health_ring_svg(summarize_fleet([_h("ok"), _h("ok"), _h("critical"), _h("critical")]))
    assert "mg-ring" in svg and "2/4" in svg
    assert 'stroke-dasharray="50 100"' in svg  # ok/total*100


def test_hero_html_states() -> None:
    from dashboard.overview import hero_html, summarize_fleet
    ok = hero_html(summarize_fleet([_h("ok"), _h("ok")]), 2, 12, "2 sn önce", "4g 12sa")
    assert "TÜM FİLO SAĞLIKLI" in ok and "<b>2</b> mast" in ok and "<b>12</b> sensör" in ok
    mixed = hero_html(summarize_fleet([_h("critical"), _h("warning"), _h("ok")]), 3, 18,
                      "1 sn önce", "4g")
    assert "1 kritik" in mixed and "1 dikkat" in mixed and "1 sağlıklı" in mixed
    assert "mg-hero--critical" in mixed
```

- [ ] **Step 2: Run FAIL** (ModuleNotFoundError).
- [ ] **Step 3: Implement** — `src/dashboard/overview.py`:
```python
"""Açılış 'Operasyon Merkezi' saf HTML/SVG builder'ları (streamlit/DB import etmez).

SAF leaf: alerts.models.Alert + dashboard.fleet/labels/transform + stdlib. app.py string'leri
st.markdown(unsafe_allow_html=True) ile basar. Serbest metin html.escape; renkler styles paletiyle uyumlu.
"""
from __future__ import annotations

import html as _html
from dataclasses import dataclass
from datetime import datetime, timedelta

from alerts.models import Alert
from dashboard.fleet import DeviceHealth
from dashboard.labels import device_label, rule_label
from dashboard.transform import relative_time

_OK = "#2f8f5b"
_WARN = "#c07d12"
_CRIT = "#bd3a2c"
_RING_BG = "#e9ecef"
_INK = "#171b21"
_MUTED = "#697078"


@dataclass(frozen=True)
class FleetSummary:
    """Filo sağlık özeti (hero + halka)."""

    total: int
    ok: int
    warning: int
    critical: int
    worst: str  # ok | warning | critical


def summarize_fleet(fleet: list[DeviceHealth]) -> FleetSummary:
    """DeviceHealth listesini sağlık sayımlarına indirger (worst: critical>warning>ok)."""
    ok = sum(1 for h in fleet if h.badge == "ok")
    warning = sum(1 for h in fleet if h.badge == "warning")
    critical = sum(1 for h in fleet if h.badge == "critical")
    worst = "critical" if critical else ("warning" if warning else "ok")
    return FleetSummary(len(fleet), ok, warning, critical, worst)


def info_badge_html(tip: str) -> str:
    """Köşe 'i' bilgi rozeti — imleç gelince data-tip CSS tooltip'i (html.escape)."""
    return f'<span class="mg-info" data-tip="{_html.escape(tip)}">i</span>'


def health_ring_svg(summary: FleetSummary) -> str:
    """Sağlık halkası (donut): yeşil yay = ok/total; merkez 'N/M' + 'SAĞLIKLI'."""
    pct = (summary.ok / summary.total * 100) if summary.total else 0.0
    return (
        '<svg class="mg-ring" viewBox="0 0 36 36">'
        f'<circle cx="18" cy="18" r="15.9" fill="none" stroke="{_RING_BG}" stroke-width="3.4"/>'
        f'<circle cx="18" cy="18" r="15.9" fill="none" stroke="{_OK}" stroke-width="3.4" '
        f'stroke-dasharray="{pct:.0f} 100" stroke-linecap="round" transform="rotate(-90 18 18)"/>'
        f'<text x="18" y="17.6" text-anchor="middle" font-size="8.5" font-weight="700" '
        f'font-family="IBM Plex Mono" fill="{_INK}">{summary.ok}/{summary.total}</text>'
        f'<text x="18" y="23.4" text-anchor="middle" font-size="3.1" '
        f'font-family="IBM Plex Mono" fill="{_MUTED}">SAĞLIKLI</text>'
        "</svg>"
    )


def hero_html(
    summary: FleetSummary, device_count: int, sensor_count: int,
    freshness_str: str, span_str: str,
) -> str:
    """Sağlık hero'su: halka + büyük durum + kapsam/tazelik subline + izleme süresi."""
    if summary.worst == "ok":
        status = f'<span style="color:{_OK}">TÜM FİLO SAĞLIKLI</span>'
    else:
        parts = []
        if summary.critical:
            parts.append(f'<span style="color:{_CRIT}">{summary.critical} kritik</span>')
        if summary.warning:
            parts.append(f'<span style="color:{_WARN}">{summary.warning} dikkat</span>')
        parts.append(f"{summary.ok} sağlıklı")
        status = " · ".join(parts)
    return (
        f'<div class="mg-hero mg-hero--{summary.worst}">'
        f"{health_ring_svg(summary)}"
        '<div class="mg-hero-mid">'
        '<div class="mg-hero-ey">Filo Durumu</div>'
        f'<div class="mg-hero-big">{status}</div>'
        f'<div class="mg-hero-sub"><b>{device_count}</b> mast · <b>{sensor_count}</b> sensör '
        f"kesintisiz izleniyor · son veri <b>{_html.escape(freshness_str)}</b></div>"
        "</div>"
        f'<div class="mg-hero-right"><div class="mg-hero-u">{_html.escape(span_str)}</div>'
        '<div class="mg-hero-ul">izleme süresi</div></div>'
        "</div>"
    )
```
> Renkli `<span style>` durum metni iç-sabit (kullanıcı girdisi değil) → escape gerekmez; sayılar int; serbest metin (freshness/span) escape'li.

- [ ] **Step 4: Run PASS. Step 5: Gate + commit** — `"feat(dashboard): overview.py hero — summarize_fleet + health_ring_svg + hero_html + info_badge"`

---

### Task 4: overview.py — kapsam (coverage) + timeline

**Files:** Modify `src/dashboard/overview.py` · Test `tests/unit/test_dashboard_overview.py`

**Interfaces — Produces:** `CoverageStat`, `coverage_stats`, `coverage_html`, `TimelineEvent`, `timeline_events`, `timeline_html`.

- [ ] **Step 1: Failing test** — ekle:
```python
def _alert(status: str = "active", severity: str = "warning",
           created_at: str = "2026-06-20T12:00:00.000Z", device: str = "device_003",
           rule: str = "hydraulic_pressure_decline"):
    from alerts.models import Alert
    return Alert(id=1, device_id=device, rule_name=rule, sensor="hydraulic_pressure",
                 severity=severity, score=0.5, window_start="s", window_end="e", value=1.0,
                 description="d", created_at=created_at, status=status, acknowledged_at=None,
                 resolved_at=None)


def test_coverage_stats_and_html() -> None:
    from dashboard.overview import coverage_html, coverage_stats
    stats = coverage_stats(6, 36, 36, "2 sn önce", 3)
    assert len(stats) == 5 and stats[0].label == "İzlenen Mast"
    h = coverage_html(stats)
    assert "mg-stats" in h and "İzlenen Mast" in h and "data-tip=" in h and ">36<" in h


def test_timeline_events() -> None:
    from datetime import UTC, datetime
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
    from datetime import UTC, datetime
    from dashboard.overview import timeline_events, timeline_html
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    assert "olay yok" in timeline_html(timeline_events([], now))
```

- [ ] **Step 2: Run FAIL.**
- [ ] **Step 3: Implement** — `overview.py` sonuna:
```python
@dataclass(frozen=True)
class CoverageStat:
    """Kapsam/ölçek şeridi tek istatistiği (info tooltip'li)."""

    value: str
    label: str
    tip: str


def coverage_stats(
    device_count: int, sensor_count: int, rate_per_s: int,
    freshness_str: str, detections_24h: int,
) -> list[CoverageStat]:
    """5 kapsam istatistiği (her biri açıklayıcı info tooltip ile)."""
    return [
        CoverageStat(str(device_count), "İzlenen Mast",
                     "Sisteme bağlı, sürekli izlenen mast sayısı."),
        CoverageStat(str(sensor_count), "Aktif Sensör",
                     "Her mastta 6 sensör — toplam izlenen kanal."),
        CoverageStat(f"~{rate_per_s}/sn", "Ölçüm Hızı",
                     "Saniyede işlenen telemetri ölçümü (~mast × 6)."),
        CoverageStat(freshness_str, "Veri Tazeliği",
                     "En son telemetrinin üstünden geçen süre."),
        CoverageStat(str(detections_24h), "Son 24s Tespit",
                     "Son 24 saatte üretilen anomali uyarısı sayısı."),
    ]


def coverage_html(stats: list[CoverageStat]) -> str:
    """Kapsam şeridi HTML'i (hairline ızgara + her stat'ta info tooltip)."""
    cells = "".join(
        f'<div class="mg-stat"><div class="mg-stat-v">{_html.escape(s.value)}'
        f"{info_badge_html(s.tip)}</div>"
        f'<div class="mg-stat-l">{_html.escape(s.label)}</div></div>'
        for s in stats
    )
    return f'<div class="mg-stats">{cells}</div>'


@dataclass(frozen=True)
class TimelineEvent:
    """Son-24s olay akışı satırı."""

    when: str
    tone: str  # critical | warning | ok | ack
    text: str


def timeline_events(alerts: list[Alert], now: datetime, limit: int = 8) -> list[TimelineEvent]:
    """Son 24 saatteki olayları (en yeni üstte) TimelineEvent'lere çevirir.

    resolved → 'çözüldü' (ok); acknowledged → 'teknisyen onayı' (ack); aktif → 'sürüyor'
    (severity tonunda). 24s filtre created_at üzerinden (lexicographic ISO).
    """
    cutoff = (now - timedelta(hours=24)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    recent = sorted(
        (a for a in alerts if a.created_at >= cutoff), key=lambda a: a.created_at, reverse=True
    )
    events: list[TimelineEvent] = []
    for a in recent[:limit]:
        if a.status == "resolved":
            tone, suffix = "ok", "çözüldü"
        elif a.status == "acknowledged":
            tone, suffix = "ack", "teknisyen onayı"
        else:
            tone = a.severity if a.severity in ("critical", "warning") else "warning"
            suffix = "sürüyor"
        text = f"{device_label(a.device_id)} · {rule_label(a.rule_name)} {suffix}"
        events.append(TimelineEvent(relative_time(now, a.created_at), tone, text))
    return events


def timeline_html(events: list[TimelineEvent]) -> str:
    """Olay akışı HTML'i (boşsa dostça 'olay yok' mesajı)."""
    if not events:
        return ('<div class="mg-tl"><div class="mg-empty">'
                "Son 24 saatte olay yok — izleme sürüyor.</div></div>")
    rows = "".join(
        f'<div class="mg-ev"><span class="mg-ev-t">{_html.escape(e.when)}</span>'
        f'<span class="mg-ev-d mg-ev-d--{e.tone}"></span>'
        f'<span class="mg-ev-x">{_html.escape(e.text)}</span></div>'
        for e in events
    )
    return f'<div class="mg-tl">{rows}</div>'
```

- [ ] **Step 4: Run PASS. Step 5: Gate + commit** — `"feat(dashboard): overview.py kapsam şeridi (info tooltip) + son-24s timeline"`

---

### Task 5: overview.py — inline-SVG sparkline + tıklanır filo kartı

**Files:** Modify `src/dashboard/overview.py` · Test `tests/unit/test_dashboard_overview.py`

**Interfaces — Produces:** `sparkline_svg(values, tone="muted") -> str`, `fleet_card_html(health, spark_values, value_str) -> str`, `fleet_grid_html(cards) -> str`.

- [ ] **Step 1: Failing test** — ekle:
```python
def test_sparkline_svg() -> None:
    from dashboard.overview import sparkline_svg
    assert sparkline_svg([]) == ""  # veri yok → boş
    svg = sparkline_svg([0.0, 1.0, 0.5, 2.0])
    assert svg.startswith("<svg") and "polyline" in svg and "points=" in svg


def test_fleet_card_clickable_and_status() -> None:
    from dashboard.overview import fleet_card_html
    crit = fleet_card_html(_h("critical"), [1.0, 2.0, 3.0], "12 bar")
    assert 'href="?dev=device_001"' in crit and 'target="_self"' in crit
    assert "mg-card--critical" in crit and "Cihaz 1" in crit and "12 bar" in crit
    ok = fleet_card_html(_h("ok"), [1.0, 1.1], "")
    assert "incele" in ok and "SAĞLIKLI" in ok


def test_fleet_grid_wraps() -> None:
    from dashboard.overview import fleet_grid_html
    assert fleet_grid_html(["<a></a>", "<a></a>"]).startswith('<div class="mg-fleet">')
```
> `_h` (Task 3 test helper) device_id="device_001" → "Cihaz 1".

- [ ] **Step 2: Run FAIL.**
- [ ] **Step 3: Implement** — import ekle: `from dashboard.labels import badge_label, device_label, rule_label, sensor_status_label` (mevcut device_label/rule_label satırını genişlet). `overview.py` sonuna:
```python
_TONE_COLOR = {"ok": _OK, "warning": _WARN, "critical": _CRIT, "muted": "#9aa1a9"}


def sparkline_svg(values: list[float], tone: str = "muted", width: int = 140, height: int = 30) -> str:
    """Değer listesini minik inline-SVG polyline sparkline'a çevirir (boş → '')."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(values)
    pts = " ".join(
        f"{i / (n - 1) * width:.1f},{height - (v - lo) / span * (height - 4) - 2:.1f}"
        for i, v in enumerate(values)
    )
    color = _TONE_COLOR.get(tone, _TONE_COLOR["muted"])
    return (
        f'<svg class="mg-spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>'
    )


def fleet_card_html(health: DeviceHealth, spark_values: list[float], value_str: str) -> str:
    """Tıklanır (drill-down) filo kartı: ad + durum rozeti + sorun/incele + sparkline + değer.

    `<a href="?dev=...">` ile tıklanınca o cihaz sayfası açılır (app.py query-param). Ham metin escape.
    """
    badge = health.badge if health.badge in ("ok", "warning", "critical") else "ok"
    tone = badge if badge != "ok" else "muted"
    if health.open_alert_count and health.top_rule:
        prob = f'<div class="mg-cprob bad">{_html.escape(rule_label(health.top_rule))}</div>'
        right = f"<span class='mg-cval'>{_html.escape(value_str)}</span>" if value_str else ""
    else:
        prob = '<div class="mg-cprob">Sorun yok</div>'
        right = '<span class="mg-go">incele →</span>'
    return (
        f'<a href="?dev={_html.escape(health.device_id)}" target="_self" '
        f'class="mg-card mg-card--{badge}"><div class="mg-strip"></div><div class="mg-body">'
        f'<div class="mg-cardhead"><span class="mg-dev">{_html.escape(device_label(health.device_id))}</span>'
        f'<span class="mg-badge mg-badge--{badge}">{_html.escape(sensor_status_label(badge) if badge=="ok" else badge_label(badge))}</span></div>'
        f"{prob}"
        f'<div class="mg-cfoot">{sparkline_svg(spark_values, tone)}{right}</div>'
        "</div></a>"
    )


def fleet_grid_html(cards: list[str]) -> str:
    """Filo kartlarını ızgara sarmalayıcısına koyar."""
    return f'<div class="mg-fleet">{"".join(cards)}</div>'
```
> Rozet etiketi: ok → "SAĞLIKLI" (badge_label); böylece kart "SAĞLIKLI/DİKKAT/KRİTİK" tutarlı. (`sensor_status_label(ok)`="NORMAL" istenmiyor burada → `badge_label` kullan.) **Düzeltme:** sadeleştir — her durumda `badge_label(badge)`:
```python
        f'<span class="mg-badge mg-badge--{badge}">{_html.escape(badge_label(badge))}</span></div>'
```
ve import'tan `sensor_status_label` çıkar (gerekmez).

- [ ] **Step 4: Run PASS** (testler `badge_label(ok)`="SAĞLIKLI" bekler — `test_fleet_card_clickable_and_status` "SAĞLIKLI" assert'i bununla geçer).
- [ ] **Step 5: Gate + commit** — `"feat(dashboard): overview.py inline-SVG sparkline + tıklanır filo kartı (drill-down)"`

---

### Task 6: charts — radar zone belirginleştirme

**Files:** Modify `src/dashboard/charts.py` · Test `tests/unit/test_dashboard_charts.py` (mevcut band testleri yeşil kalır)

- [ ] **Step 1: Implement** — `ZONE_OPACITY = 0.10` → `ZONE_OPACITY = 0.16` (zone'lar beyaz zeminde daha belirgin).
- [ ] **Step 2: Run** — `.venv/bin/python -m pytest tests/unit/test_dashboard_charts.py -q` → mevcut 7 test PASS (opaklık değeri yapıyı kırmaz; testler katman varlığını kontrol eder, opaklığı değil).
- [ ] **Step 3: Gate + commit** — `"style(dashboard): radar zone opaklığı 0.10→0.16 (beyaz zeminde belirginlik)"`

---

### Task 7: styles — Operasyon Merkezi CSS

**Files:** Modify `src/dashboard/styles.py` · Test `tests/unit/test_dashboard_styles.py`

- [ ] **Step 1: Failing test** — `tests/unit/test_dashboard_styles.py` `test_app_css_nonempty_and_hides_chrome` altına ekle:
```python
def test_app_css_has_operations_center_classes() -> None:
    from dashboard.styles import APP_CSS
    for cls in (".mg-hero", ".mg-stats", ".mg-info", ".mg-tl", ".mg-ev", ".mg-ring"):
        assert cls in APP_CSS
```

- [ ] **Step 2: Run FAIL.**
- [ ] **Step 3: Implement** — `styles.py` `APP_CSS` içinde `.mg-section {{...}}` satırından ÖNCE ekle (f-string `{{ }}` kaçışı):
```css
/* Operasyon Merkezi — hero */
.mg-hero {{display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:24px;
  background:{_SURFACE}; border:1px solid {_BORDER}; border-left:4px solid {_OK};
  border-radius:8px; padding:18px 24px; margin:6px 0 14px;}}
.mg-hero--warning {{border-left-color:{_WARN};}}
.mg-hero--critical {{border-left-color:{_CRIT};}}
.mg-ring {{width:92px; height:92px; flex:0 0 auto;}}
.mg-hero-ey {{font-family:{_MONO}; font-size:11px; letter-spacing:.14em; text-transform:uppercase;
  color:{_MUTED}; margin-bottom:4px;}}
.mg-hero-big {{font-size:27px; font-weight:700; color:{_TEXT}; letter-spacing:-.01em;}}
.mg-hero-sub {{color:{_MUTED}; font-size:14px; margin-top:8px;}}
.mg-hero-sub b {{color:{_TEXT}; font-family:{_MONO};}}
.mg-hero-right {{text-align:right;}}
.mg-hero-u {{font-family:{_MONO}; font-size:21px; font-weight:600; color:{_TEXT};}}
.mg-hero-ul {{font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:{_MUTED}; margin-top:3px;}}

/* Kapsam şeridi + info tooltip */
.mg-stats {{display:grid; grid-template-columns:repeat(5,1fr); background:{_SURFACE};
  border:1px solid {_BORDER}; border-radius:6px; overflow:hidden; margin-bottom:6px;}}
.mg-stat {{padding:13px 18px; border-left:1px solid {_BORDER};}}
.mg-stat:first-child {{border-left:0;}}
.mg-stat-v {{font-family:{_MONO}; font-size:21px; font-weight:600; display:flex; align-items:center; gap:6px;}}
.mg-stat-l {{font-size:10.5px; letter-spacing:.1em; text-transform:uppercase; color:{_MUTED}; margin-top:5px;}}
.mg-info {{display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px;
  border:1px solid {_BORDER}; border-radius:50%; font-family:{_MONO}; font-size:10px; font-weight:400;
  color:{_MUTED}; cursor:help; position:relative;}}
.mg-info::after {{content:attr(data-tip); position:absolute; bottom:150%; left:50%;
  transform:translateX(-50%); background:{_GRAPHITE}; color:#eef0f2; font-family:{_FONT}; font-size:12px;
  letter-spacing:0; text-transform:none; padding:7px 10px; border-radius:5px; width:max-content;
  max-width:230px; white-space:normal; opacity:0; pointer-events:none; transition:opacity .12s;
  z-index:60; box-shadow:0 4px 14px rgba(0,0,0,.18);}}
.mg-info:hover::after {{opacity:1;}}

/* Filo kartı sparkline ayağı (mg-card mevcut; link + foot eklemeleri) */
a.mg-card {{text-decoration:none; color:inherit; display:block;}}
.mg-card .mg-cprob {{font-size:13px; color:{_MUTED}; margin:7px 0 0;}}
.mg-card .mg-cprob.bad {{color:{_TEXT}; font-weight:500;}}
.mg-card .mg-cfoot {{display:flex; align-items:flex-end; justify-content:space-between; gap:10px; margin-top:9px;}}
.mg-card .mg-spark {{flex:1; min-width:0; height:30px;}}
.mg-card .mg-go {{font-family:{_MONO}; font-size:11px; color:{_MUTED};}}
.mg-card .mg-cval {{font-family:{_MONO}; font-size:13px; color:{_MUTED};}}
.mg-card .mg-cval b {{color:{_TEXT};}}

/* Timeline */
.mg-tl {{background:{_SURFACE}; border:1px solid {_BORDER}; border-radius:6px; padding:4px 18px; margin-bottom:6px;}}
.mg-ev {{display:grid; grid-template-columns:78px 12px 1fr; align-items:center; gap:12px;
  padding:11px 0; border-top:1px solid {_BORDER};}}
.mg-ev:first-child {{border-top:0;}}
.mg-ev-t {{font-family:{_MONO}; font-size:12px; color:{_MUTED};}}
.mg-ev-d {{width:9px; height:9px; border-radius:50%; background:{_OK};}}
.mg-ev-d--warning {{background:{_WARN};}}
.mg-ev-d--critical {{background:{_CRIT};}}
.mg-ev-d--ack {{background:{_MUTED};}}
.mg-ev-x {{font-size:14px; color:{_TEXT};}}
```

- [ ] **Step 4: Run PASS. Step 5: Gate + commit** — `"style(dashboard): Operasyon Merkezi CSS (hero/halka/kapsam/info-tooltip/sparkline-kart/timeline)"`

---

### Task 8: app.py — _render_overview yeniden yazımı + drill-down

**Files:** Modify `src/dashboard/app.py` · Test `tests/unit/test_dashboard_app_boot.py` (yeşil kalır)

**Interfaces — Consumes:** Task 1-5 + 7. Yardımcılar: `_freshness_str`, `_span_str`, `_detections_24h`, `_spark_values`.

- [ ] **Step 1: Import bloğunu genişlet** — mevcut blokları MERGE et (duplicate yok):
  - `from dashboard.fleet import (...)` → ekle `representative_sensor`, `sort_fleet_by_severity`.
  - Yeni: `from dashboard.overview import (coverage_html, coverage_stats, fleet_card_html, fleet_grid_html, hero_html, summarize_fleet, timeline_events, timeline_html)  # noqa: E402`
  - `from dashboard.transform import (...)` → `relative_time` ekle (freshness için).

- [ ] **Step 2: Yardımcılar ekle** — `_render_overview`'dan önce:
```python
_DAY_S = 24 * 60 * 60


def _freshness_str(latest: list, now: datetime) -> str:
    """En yeni telemetrinin tazeliği ('2 sn önce'); veri yoksa '—'."""
    if not latest:
        return "—"
    newest = max(r.timestamp for r in latest)
    return relative_time(now, newest)


def _span_str(repository: TelemetryRepository, now: datetime) -> str:
    """İzleme süresi (en eski telemetriden bu yana, kabaca 'Ng Msa')."""
    try:
        earliest = repository.earliest_telemetry_timestamp()
    except OperationalError:
        return "—"
    if not earliest:
        return "—"
    try:
        start = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    secs = max(0, int((now - start).total_seconds()))
    days, rem = divmod(secs, _DAY_S)
    hours = rem // 3600
    if days:
        return f"{days}g {hours}sa"
    mins = (rem % 3600) // 60
    return f"{hours}sa {mins}dk" if hours else f"{mins} dk"


def _detections_24h(repository: TelemetryRepository, now: datetime) -> int:
    """Son 24 saatteki anomali tespiti sayısı (KPI)."""
    since = (now - timedelta(seconds=_DAY_S)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    try:
        return repository.count_anomalies_since(since)
    except OperationalError:
        return 0


def _spark_values(repository: TelemetryRepository, device_id: str, sensor: str, since: str) -> list[float]:
    """Bir cihaz+sensörün son penceredeki değerleri (kart sparkline'ı); hata→[]."""
    try:
        readings = repository.fetch_window(device_id, sensor, since)
    except OperationalError:
        return []
    return [r.value for r in readings]
```
> `from datetime import timedelta` import bloğunda var mı kontrol et; yoksa `from datetime import UTC, datetime, timedelta` yap.

- [ ] **Step 3: `_render_overview` yeniden yaz** — mevcut gövdeyi şununla değiştir:
```python
@st.experimental_fragment(run_every="5s")
def _render_overview(repository: TelemetryRepository) -> None:
    """Operasyon Merkezi açılışı: hero + kapsam + sinyal-ızgara + 24s timeline (5s, salt-görüntü)."""
    alerts, alerts_available = _fetch_alerts_safe(repository)
    try:
        latest = repository.fetch_latest_readings()
    except OperationalError as e:
        logger.error("Son okumalar alınamadı: {}", e)
        st.error("Son okumalar alınamadı (DB hatası).")
        return
    devices = sorted({r.device_id for r in latest})
    now = datetime.now(UTC)

    fleet = derive_fleet(devices, latest, alerts)
    summary = summarize_fleet(fleet)
    sensor_count = len({(r.device_id, r.sensor) for r in latest})
    freshness = _freshness_str(latest, now)

    st.markdown(
        hero_html(summary, len(devices), sensor_count, freshness, _span_str(repository, now)),
        unsafe_allow_html=True,
    )
    st.markdown(
        coverage_html(coverage_stats(
            len(devices), sensor_count, len(devices) * 6, freshness, _detections_24h(repository, now)
        )),
        unsafe_allow_html=True,
    )
    if not alerts_available:
        st.caption("Detector henüz çalışmadı — uyarı verisi yok (`python -m detectors`).")

    st.markdown('<div class="mg-section">Mastlar — duruma göre sıralı</div>', unsafe_allow_html=True)
    since60 = window_to_since(now, "Son 15 dakika")  # kısa pencere değerleri yeterli; sparkline downsample'sız
    cards = []
    for h in sort_fleet_by_severity(fleet):
        sensor = representative_sensor(h)
        values = _spark_values(repository, h.device_id, sensor, since60)
        snap = next((s for s in h.snapshots if s.sensor == sensor), None)
        value_str = f"{snap.value:.1f} {snap.unit}".strip() if (snap and h.open_alert_count) else ""
        cards.append(fleet_card_html(h, values, value_str))
    st.markdown(fleet_grid_html(cards), unsafe_allow_html=True)

    st.markdown('<div class="mg-section">Son 24 saat — olay akışı</div>', unsafe_allow_html=True)
    st.markdown(timeline_html(timeline_events(alerts, now)), unsafe_allow_html=True)

    open_alerts = [a for a in alerts if a.status in OPEN_STATUSES]
    if open_alerts:
        faults, data_quality = split_alerts_by_axis(open_alerts)
        st.markdown('<div class="mg-section">Açık Uyarılar</div>', unsafe_allow_html=True)
        if faults:
            st.markdown(alerts_section_html("Arıza Uyarıları", faults, now, ""), unsafe_allow_html=True)
        if data_quality:
            st.markdown(
                alerts_section_html("Veri Kalitesi / Sensör Sağlığı", data_quality, now, ""),
                unsafe_allow_html=True,
            )
```
> Eski `_render_fleet_cards`, `_VIEW_OPTIONS`, `_filter_view`, `compute_kpis`/`kpis_html`/`fleet_summary_html`/`fleet_html`/`latest_alert_per_device` artık `_render_overview`'da kullanılmıyor → **kullanılmayan import/fonksiyonları temizle** (ruff F401/F811). `compute_kpis`/`kpis_html`/`fleet_html`/`fleet_summary_html` import'larını kaldır; `_render_fleet_cards`/`_filter_view`/`_VIEW_OPTIONS` sil. (DeviceHealth hâlâ tip için gerekmiyorsa kaldır.)

- [ ] **Step 4: Drill-down query-param** — `main()`'de `if not devices:` guard'ından sonra, `config = _get_detector_config()` öncesine ekle:
```python
    dev_param = st.query_params.get("dev")
    if dev_param and dev_param in devices:
        st.session_state["nav"] = device_label(dev_param)
        st.query_params.clear()
```

- [ ] **Step 5: Boot smoke + full gate** — `.venv/bin/python -m pytest tests/unit/test_dashboard_app_boot.py -q` (boş-DB erken döner) + tam gate.
- [ ] **Step 6: Commit** — `"feat(dashboard): açılış Operasyon Merkezi'ne dönüştü (hero+kapsam+sinyal-ızgara+timeline) + ?dev drill-down"`

---

### Task 9: Canlı doğrulama + docs

**Files:** Modify `CLAUDE.md` (dashboard çalıştırma notu)

- [ ] **Step 1:** `./scripts/demo_down.sh && ./scripts/demo_up.sh`, ~90 sn bekle.
- [ ] **Step 2: Görsel doğrulama (kullanıcı):**
  1. Hero + sağlık halkası render; karışık/hep-yeşil doğru ("TÜM FİLO SAĞLIKLI" vs sayımlar).
  2. Kapsam şeridi + **info (i) tooltip** imleçle görünüyor.
  3. Filo ızgarası duruma göre sıralı; **kart tıklanınca o cihaz açılıyor** (`?dev`); sparkline + hover buz-mavisi.
  4. Son-24s timeline olayları (veya "olay yok") doğru.
  5. **Cihaz Detayı'nda zone'lar (yeşil/sarı/kırmızı) beyaz zeminde NET görünüyor** (kullanıcının istediği katmanlar).
- [ ] **Step 3:** CLAUDE.md dashboard maddesine açılış yapısını (Operasyon Merkezi: hero/kapsam/sinyal-ızgara/timeline + `?dev` drill-down) ekle.
- [ ] **Step 4: Commit** — `"docs(dashboard): Operasyon Merkezi açılış çalıştırma notu (canlı smoke)"`

---

## Self-Review
- **Spec coverage:** hero+halka (T3), kapsam+info (T4), sinyal-ızgara+sparkline+drill-down (T2/T5/T8), timeline (T4), repository (T1), zone belirginleştirme (T6), CSS (T7), wiring (T8), canlı+docs (T9). ✓
- **Placeholder:** yok; tüm kod tam. Task 5'te ilk taslak yerine "Düzeltme" notu kesin sürümü (badge_label) veriyor.
- **Type/isim tutarlılığı:** `FleetSummary`/`summarize_fleet`/`hero_html`/`coverage_stats`/`coverage_html`/`timeline_events`/`timeline_html`/`sparkline_svg`/`fleet_card_html`/`fleet_grid_html`/`sort_fleet_by_severity`/`representative_sensor`/`earliest_telemetry_timestamp`/`count_anomalies_since` — T8'de aynen tüketiliyor. ✓
- **Altair-in-HTML riski:** sparkline saf inline-SVG (Altair değil) → karta gömülür, widget yok. ✓
- **Drill-down:** `?dev` query-param + session_state nav (widget-state idiyomu); sidebar fallback korunur. ✓

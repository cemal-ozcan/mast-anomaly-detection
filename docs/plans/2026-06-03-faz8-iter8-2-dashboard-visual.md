# Faz 8 Iter 8.2 — Dashboard Görsel Zenginleştirme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard'ı yönetici demosu için görsel zenginleştir — KPI satırı + filo sağlık
kartları + severity-stilli uyarı akışı (cihaz-özeti flicker yumuşatma) + Altair grafikler +
anomali overlay + açık kurumsal tema.

**Architecture:** Saf modüller (`transform.py` genişler, `fleet.py` + `charts.py` yeni —
streamlit import ETMEZ, birim testli) + ince `app.py` wiring (fragment yapısı korunur: üst blok
5s, grafikler 2s, yönetim fragment dışı). Tek yeni read-only repository metodu
`fetch_latest_readings()`. Tema `.streamlit/config.toml`.

**Tech Stack:** Streamlit 1.36 (`st.experimental_fragment`, `st.container(border=True)`,
`st.metric`), Altair 5.5.0 (streamlit'le gelir, `py.typed` VAR), pandas Styler, SQLAlchemy Core
(window function; SQLite 3.53).

**Spec (tek hakem):** `docs/specs/2026-06-03-faz8-iter8-2-dashboard-visual-design.md`

**Komut konvansiyonları:** pytest/mypy = `.venv/bin/python -m ...`; ruff = homebrew `ruff`
(PATH'te; `.venv -m ruff` YOK). Her task sonunda tam suite + scoped mypy + ruff; Task 10 final
tam sweep.

---

### Task 1: Tema (`.streamlit/config.toml`) + altair pin

**Files:**
- Create: `.streamlit/config.toml`
- Modify: `requirements.txt` (streamlit satırının altına `altair==5.5.0`)

- [ ] **Step 1: Tema config'ini yaz**

`.streamlit/config.toml` (yeni dosya, commit'li):

```toml
[theme]
base = "light"
primaryColor = "#1d4ed8"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f8fafc"
textColor = "#1e293b"
font = "sans serif"
```

- [ ] **Step 2: requirements.txt'e altair pinini ekle**

`requirements.txt` içinde `streamlit==1.36.0` satırını bul, hemen altına ekle:

```
altair==5.5.0
```

(venv'de zaten kurulu — `pip install` GEREKMEZ; doğrudan import edeceğimiz için dürüst beyan.)

- [ ] **Step 3: Mevcut suite hâlâ yeşil mi doğrula**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: tamamı PASS (≈313 passed, 1 smoke skipped) — değişiklik davranış etkilemez.

- [ ] **Step 4: Commit**

```bash
git add .streamlit/config.toml requirements.txt
git commit -m "feat(dashboard): açık kurumsal tema (.streamlit/config.toml) + altair==5.5.0 pin (Faz 8 Iter 8.2 spec § 4/§ 8)"
```

---

### Task 2: `transform.relative_time`

**Files:**
- Modify: `src/dashboard/transform.py`
- Test: `tests/unit/test_dashboard_transform.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_dashboard_transform.py` sonuna ekle:

```python
def test_relative_time_seconds() -> None:
    """60 sn altı 'X sn önce' döner."""
    from datetime import UTC, datetime

    from dashboard.transform import relative_time

    now = datetime(2026, 6, 3, 12, 0, 30, tzinfo=UTC)
    assert relative_time(now, "2026-06-03T12:00:18.000Z") == "12 sn önce"


def test_relative_time_minutes_hours_days() -> None:
    """Dakika/saat/gün eşikleri doğru birimle döner."""
    from datetime import UTC, datetime

    from dashboard.transform import relative_time

    now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC)
    assert relative_time(now, "2026-06-03T11:55:00.000Z") == "5 dk önce"
    assert relative_time(now, "2026-06-03T09:00:00.000Z") == "3 sa önce"
    assert relative_time(now, "2026-06-01T12:00:00.000Z") == "2 gün önce"


def test_relative_time_future_clamps_to_zero() -> None:
    """Gelecek timestamp (saat kayması) negatife düşmez — '0 sn önce'."""
    from datetime import UTC, datetime

    from dashboard.transform import relative_time

    now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC)
    assert relative_time(now, "2026-06-03T12:00:05.000Z") == "0 sn önce"


def test_relative_time_naive_now_raises() -> None:
    """tz-naive now → ValueError (window_to_since deseni)."""
    from datetime import datetime

    import pytest

    from dashboard.transform import relative_time

    with pytest.raises(ValueError):
        relative_time(datetime(2026, 6, 3, 12, 0, 0), "2026-06-03T11:00:00.000Z")
```

- [ ] **Step 2: Testlerin FAIL ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_transform.py -q`
Expected: 4 FAIL — `ImportError: cannot import name 'relative_time'`

- [ ] **Step 3: Implementasyon**

`src/dashboard/transform.py`'a ekle (`window_to_since`'in altına):

```python
def relative_time(now: datetime, ts: str) -> str:
    """ISO 8601 timestamp'i insan-okur göreli zamana çevirir ("12 sn önce").

    Args:
        now: Şimdiki UTC-aware datetime (test için enjekte edilir). tz-naive → ValueError.
        ts: Publisher/DB formatında ISO 8601 string (`...Z` veya `+00:00`).

    Returns:
        "X sn önce" / "X dk önce" / "X sa önce" / "X gün önce". Gelecek ts → "0 sn önce".

    Raises:
        ValueError: now tz-naive ise.
    """
    if now.tzinfo is None:
        raise ValueError("now UTC-aware datetime olmalı (naive datetime kabul edilmez)")
    moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    seconds = max(0, int((now - moment).total_seconds()))
    if seconds < 60:
        return f"{seconds} sn önce"
    if seconds < 3600:
        return f"{seconds // 60} dk önce"
    if seconds < 86400:
        return f"{seconds // 3600} sa önce"
    return f"{seconds // 86400} gün önce"
```

- [ ] **Step 4: Testlerin PASS ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_transform.py -q`
Expected: hepsi PASS

- [ ] **Step 5: Tam suite + lint + commit**

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/dashboard tests/unit/test_dashboard_transform.py
ruff check src/dashboard tests/unit/test_dashboard_transform.py
git add src/dashboard/transform.py tests/unit/test_dashboard_transform.py
git commit -m "feat(dashboard): relative_time saf helper (göreli zaman, Faz 8 Iter 8.2 spec § 7)"
```

---

### Task 3: `transform.downsample_frame`

**Files:**
- Modify: `src/dashboard/transform.py`
- Test: `tests/unit/test_dashboard_transform.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_dashboard_transform.py` sonuna ekle:

```python
def test_downsample_frame_small_unchanged() -> None:
    """max_points altındaki frame AYNEN döner (kopya değil, aynı obje kabul)."""
    import pandas as pd

    from dashboard.transform import downsample_frame

    frame = pd.DataFrame({"value": range(10)})
    assert downsample_frame(frame, max_points=100) is frame


def test_downsample_frame_reduces_and_preserves_order_and_endpoints() -> None:
    """Büyük frame max_points'e iner; sıra korunur; ilk/son satır dahil."""
    import pandas as pd

    from dashboard.transform import downsample_frame

    frame = pd.DataFrame({"value": range(5000)})
    out = downsample_frame(frame, max_points=1000)
    assert len(out) <= 1000
    values = out["value"].tolist()
    assert values == sorted(values)  # sıra korunur
    assert values[0] == 0 and values[-1] == 4999  # uç noktalar dahil
```

- [ ] **Step 2: Testlerin FAIL ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_transform.py -q`
Expected: 2 FAIL — `ImportError: cannot import name 'downsample_frame'`

- [ ] **Step 3: Implementasyon**

`src/dashboard/transform.py` import bloğuna `import numpy as np` ekle (pandas'ın yanına;
numpy zaten proje bağımlılığı), sonra ekle:

```python
def downsample_frame(frame: pd.DataFrame, max_points: int = 1000) -> pd.DataFrame:
    """Frame'i eşit aralıklı seyrelterek en çok max_points satıra indirir (spec § 5).

    Altair'in max_rows=5000 sınırı uzun pencerelerde MaxRowsError fırlatır; her grafik
    öncesi bu guard uygulanır. Küçük frame DEĞİŞMEDEN (aynı obje) döner.

    Args:
        frame: Satır sırası anlamlı (timestamp ASC) DataFrame.
        max_points: Üst sınır (>0).

    Returns:
        En çok max_points satırlı, sıra + ilk/son satır korunmuş DataFrame.
    """
    if len(frame) <= max_points:
        return frame
    indices = np.unique(np.linspace(0, len(frame) - 1, num=max_points, dtype=int))
    return frame.iloc[indices]
```

- [ ] **Step 4: Testlerin PASS ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_transform.py -q`
Expected: hepsi PASS

- [ ] **Step 5: Tam suite + lint + commit**

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/dashboard tests/unit/test_dashboard_transform.py
ruff check src/dashboard tests/unit/test_dashboard_transform.py
git add src/dashboard/transform.py tests/unit/test_dashboard_transform.py
git commit -m "feat(dashboard): downsample_frame (Altair max_rows guard, Faz 8 Iter 8.2 spec § 5)"
```

---

### Task 4: `transform.latest_alert_per_device` (cihaz özeti / flicker yumuşatma)

**Files:**
- Modify: `src/dashboard/transform.py`
- Test: `tests/unit/test_dashboard_alerts_transform.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_dashboard_alerts_transform.py` sonuna ekle (dosyadaki Alert kurucu desenini
kullan — test başına lokal import):

```python
def _alert(id_: int, device: str, status: str, created_at: str, severity: str = "warning") -> object:
    """Test Alert fabrikası (yalnız bu dosyada)."""
    from alerts.models import Alert

    return Alert(id=id_, device_id=device, rule_name=f"rule_{id_}", sensor="motor_current",
                 severity=severity, score=0.5, window_start="s", window_end="e",
                 value=1.0, description="d", created_at=created_at, status=status,
                 acknowledged_at=None, resolved_at=None)


def test_latest_alert_per_device_keeps_first_open_per_device() -> None:
    """created_at DESC girdide cihaz başına İLK açık uyarı kalır; resolved atlanır."""
    from dashboard.transform import latest_alert_per_device

    alerts = [
        _alert(5, "device_002", "active", "2026-06-03T12:05:00.000Z"),
        _alert(4, "device_002", "resolved", "2026-06-03T12:04:00.000Z"),
        _alert(3, "device_001", "acknowledged", "2026-06-03T12:03:00.000Z"),
        _alert(2, "device_002", "active", "2026-06-03T12:02:00.000Z"),
        _alert(1, "device_001", "active", "2026-06-03T12:01:00.000Z"),
    ]
    result = latest_alert_per_device(alerts)  # type: ignore[arg-type]
    assert [(a.id, a.device_id) for a in result] == [(5, "device_002"), (3, "device_001")]


def test_latest_alert_per_device_all_resolved_empty() -> None:
    """Yalnız resolved uyarılar → boş liste (açık uyarı yok)."""
    from dashboard.transform import latest_alert_per_device

    alerts = [_alert(1, "device_001", "resolved", "2026-06-03T12:00:00.000Z")]
    assert latest_alert_per_device(alerts) == []  # type: ignore[arg-type]
```

- [ ] **Step 2: Testlerin FAIL ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_alerts_transform.py -q`
Expected: 2 FAIL — ImportError

- [ ] **Step 3: Implementasyon**

`src/dashboard/transform.py` import bloğuna `from alerts.lifecycle import ACKNOWLEDGED, ACTIVE`
ekle (stdlib-only saf leaf — transform safiyeti korunur), sonra ekle:

```python
OPEN_STATUSES: tuple[str, ...] = (ACTIVE, ACKNOWLEDGED)


def latest_alert_per_device(alerts: list[Alert]) -> list[Alert]:
    """Cihaz başına en son AÇIK uyarıyı döndürür — "Cihaz özeti" görünümü (spec § 2 flicker).

    Args:
        alerts: created_at DESC sıralı uyarılar (fetch_alerts çıktısı; tüm durumlar olabilir).

    Returns:
        Cihaz başına ilk görülen açık (active|acknowledged) uyarı; girdi sırası korunur.
        Açık uyarısı olmayan cihaz listede YOK (kartlar zaten OK gösterir).
    """
    seen: set[str] = set()
    result: list[Alert] = []
    for alert in alerts:
        if alert.status not in OPEN_STATUSES or alert.device_id in seen:
            continue
        seen.add(alert.device_id)
        result.append(alert)
    return result
```

- [ ] **Step 4: Testlerin PASS ettiğini doğrula + tam suite + lint + commit**

```bash
.venv/bin/python -m pytest tests/unit/test_dashboard_alerts_transform.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/dashboard tests/unit/test_dashboard_alerts_transform.py
ruff check src/dashboard tests/unit/test_dashboard_alerts_transform.py
git add src/dashboard/transform.py tests/unit/test_dashboard_alerts_transform.py
git commit -m "feat(dashboard): latest_alert_per_device cihaz-özeti görünümü (flicker yumuşatma, Faz 8 Iter 8.2 spec § 2/§ 7)"
```

---

### Task 5: `alerts_to_frame` göreli zaman + severity emoji + `severity_row_style`

> **BAĞIMLILIK: Task 4 TAMAMLANMIŞ OLMALI** — bu task'ın testleri Task 4'ün aynı test
> dosyasına eklediği `_alert` fabrikasını ve `latest_alert_per_device`'ı kullanır.

**Files:**
- Modify: `src/dashboard/transform.py` (`alerts_to_frame` İMZA DEĞİŞİR: `now` parametresi)
- Modify: `tests/unit/test_dashboard_alerts_transform.py` (mevcut 2 test güncellenir)
- Modify: `src/dashboard/app.py:110` (`alerts_to_frame(alerts)` çağrısı — Task 9'da app
  zaten yeniden yazılacak; bu task'ta SADECE çağrıyı `alerts_to_frame(alerts, datetime.now(UTC))`
  yap ki suite yeşil kalsın)

- [ ] **Step 1: Mevcut 2 testi güncelle + yeni testleri yaz**

`tests/unit/test_dashboard_alerts_transform.py` — mevcut iki testi ŞU HALE getir ve yenileri
ekle (`_alert` fabrikası Task 4'te bu dosyaya eklendi; Task 4 henüz yapılmadıysa önce onu yap):

```python
def test_alerts_to_frame_columns_and_status() -> None:
    """alerts_to_frame durum + göreli zaman kolonu içerir; severity emoji'li; skor yuvarlanır."""
    from datetime import UTC, datetime

    from alerts.models import Alert
    from dashboard.transform import alerts_to_frame

    alerts = [
        Alert(id=1, device_id="device_001", rule_name="motor_current_high", sensor="motor_current",
              severity="critical", score=0.912, window_start="s", window_end="2026-06-03T10:00:00.000Z",
              value=10.0, description="d", created_at="2026-06-03T10:00:05.000Z", status="active",
              acknowledged_at=None, resolved_at=None),
    ]
    now = datetime(2026, 6, 3, 10, 0, 17, tzinfo=UTC)
    frame = alerts_to_frame(alerts, now)
    assert list(frame.columns) == [
        "zaman", "ne zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"
    ]
    assert frame.iloc[0]["durum"] == "active"
    assert frame.iloc[0]["skor"] == 0.91
    assert frame.iloc[0]["zaman"] == "2026-06-03T10:00:00.000Z"
    assert frame.iloc[0]["ne zaman"] == "12 sn önce"
    assert frame.iloc[0]["severity"] == "🔴 critical"


def test_alerts_to_frame_empty_correct_schema() -> None:
    """Boş girdi → 0 satırlı, doğru kolonlu DataFrame."""
    from datetime import UTC, datetime

    from dashboard.transform import alerts_to_frame

    frame = alerts_to_frame([], datetime(2026, 6, 3, 10, 0, 0, tzinfo=UTC))
    assert list(frame.columns) == [
        "zaman", "ne zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"
    ]
    assert len(frame) == 0


def test_severity_emoji_fallback() -> None:
    """Bilinmeyen severity ⚪ ile işaretlenir (çökmez)."""
    from datetime import UTC, datetime

    from dashboard.transform import alerts_to_frame

    a = _alert(1, "device_001", "active", "2026-06-03T10:00:00.000Z", severity="exotic")
    frame = alerts_to_frame([a], datetime(2026, 6, 3, 10, 0, 5, tzinfo=UTC))  # type: ignore[list-item]
    assert frame.iloc[0]["severity"] == "⚪ exotic"


def test_severity_row_style_colors_by_severity() -> None:
    """critical/warning satırları CSS alır; OK/bilinmeyen boş string listesi."""
    from datetime import UTC, datetime

    from dashboard.transform import alerts_to_frame, severity_row_style

    crit = _alert(1, "device_001", "active", "2026-06-03T10:00:00.000Z", severity="critical")
    warn = _alert(2, "device_002", "active", "2026-06-03T10:00:00.000Z", severity="warning")
    frame = alerts_to_frame([crit, warn], datetime(2026, 6, 3, 10, 0, 5, tzinfo=UTC))  # type: ignore[list-item]
    crit_styles = severity_row_style(frame.iloc[0])
    warn_styles = severity_row_style(frame.iloc[1])
    assert len(crit_styles) == len(frame.columns)
    assert all("#fef2f2" in s for s in crit_styles)
    assert all("#fefce8" in s for s in warn_styles)
```

- [ ] **Step 2: Testlerin FAIL ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_alerts_transform.py -q`
Expected: FAIL — `alerts_to_frame() takes 1 positional argument` + ImportError `severity_row_style`

- [ ] **Step 3: Implementasyon**

`src/dashboard/transform.py` — `_ALERT_COLUMNS` ve `alerts_to_frame`'i ŞU HALE getir + yeni
sabit/fonksiyon ekle:

```python
_ALERT_COLUMNS = ["zaman", "ne zaman", "cihaz", "severity", "sensör", "kural", "skor", "durum", "açıklama"]

_SEVERITY_EMOJI = {"critical": "🔴", "high": "🟠", "warning": "🟡"}

# Tema B severity paleti (spec § 4) — satır zemin + metin rengi
_SEVERITY_ROW_CSS = {
    "critical": "background-color: #fef2f2; color: #b91c1c",
    "high": "background-color: #fff7ed; color: #c2410c",
    "warning": "background-color: #fefce8; color: #a16207",
}


def alerts_to_frame(alerts: list[Alert], now: datetime) -> pd.DataFrame:
    """Alert listesini severity-emoji'li + göreli zamanlı "Uyarılar" tablosuna çevirir (spec § 3).

    Args:
        alerts: fetch_alerts çıktısı (created_at DESC sıralı; boş olabilir).
        now: Göreli zaman hesabı için şimdiki UTC-aware datetime (enjekte edilir).

    Returns:
        [zaman, ne zaman, cihaz, severity, sensör, kural, skor, durum, açıklama] kolonlu
        DataFrame; girdi sırasını korur. `zaman` = window_end, `ne zaman` = created_at'ten
        göreli, `severity` emoji önekli. Boş girdi → 0 satırlı doğru-şemalı DataFrame.
    """
    return pd.DataFrame(
        {
            "zaman": [a.window_end for a in alerts],
            "ne zaman": [relative_time(now, a.created_at) for a in alerts],
            "cihaz": [a.device_id for a in alerts],
            "severity": [f"{_SEVERITY_EMOJI.get(a.severity, '⚪')} {a.severity}" for a in alerts],
            "sensör": [a.sensor for a in alerts],
            "kural": [a.rule_name for a in alerts],
            "skor": [round(a.score, 2) for a in alerts],
            "durum": [a.status for a in alerts],
            "açıklama": [a.description for a in alerts],
        },
        columns=_ALERT_COLUMNS,
    )


def severity_row_style(row: pd.Series) -> list[str]:
    """pandas Styler.apply(axis=1) için satır-bazlı severity CSS'i üretir (spec § 3/§ 4).

    Args:
        row: alerts_to_frame çıktısının bir satırı ("severity" kolonu emoji önekli).

    Returns:
        Satırdaki her hücre için aynı CSS string'i; eşleşme yoksa boş string'ler.
    """
    severity = str(row.get("severity", ""))
    for key, css in _SEVERITY_ROW_CSS.items():
        if key in severity:
            return [css] * len(row)
    return [""] * len(row)
```

Not: `pd.Series` tip imzası için dosya başındaki pandas importu yeterli.

- [ ] **Step 4: app.py çağrısını güncelle (geçici, Task 9 yeniden yazacak)**

`src/dashboard/app.py` `_render_alerts` içinde:

```python
    st.dataframe(
        alerts_to_frame(alerts, datetime.now(UTC)),
        use_container_width=True,
        hide_index=True,
    )
```

- [ ] **Step 5: Testlerin PASS ettiğini doğrula + tam suite + lint + commit**

```bash
.venv/bin/python -m pytest tests/unit/test_dashboard_alerts_transform.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/dashboard tests/unit/test_dashboard_alerts_transform.py
ruff check src/dashboard tests/unit/test_dashboard_alerts_transform.py
git add src/dashboard/transform.py src/dashboard/app.py tests/unit/test_dashboard_alerts_transform.py
git commit -m "feat(dashboard): severity-stilli uyarı frame'i (emoji + göreli zaman + Styler CSS, Faz 8 Iter 8.2 spec § 3)"
```

---

### Task 6: `fleet.py` — KPI + kart verisi türetimi

**Files:**
- Create: `src/dashboard/fleet.py`
- Test: `tests/unit/test_dashboard_fleet.py` (yeni)

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_dashboard_fleet.py` (yeni dosya):

```python
"""dashboard.fleet türetim birim testleri (Faz 8 Iter 8.2 spec § 7)."""
from __future__ import annotations

from datetime import UTC, datetime

from alerts.models import Alert
from ingestion.message_parser import IngestedReading


def _alert(id_: int, device: str, status: str = "active", severity: str = "warning",
           sensor: str = "motor_current", rule: str = "motor_current_high",
           created_at: str = "2026-06-03T12:00:00.000Z") -> Alert:
    return Alert(id=id_, device_id=device, rule_name=rule, sensor=sensor, severity=severity,
                 score=0.5, window_start="s", window_end="e", value=1.0, description="d",
                 created_at=created_at, status=status, acknowledged_at=None, resolved_at=None)


def _reading(device: str, sensor: str, value: float = 1.0, unit: str = "A",
             state: str = "idle", ts: str = "2026-06-03T12:00:00.000Z") -> IngestedReading:
    return IngestedReading(device_id=device, sensor=sensor, timestamp=ts,
                           state=state, value=value, unit=unit)


def test_badge_critical_beats_warning() -> None:
    """Açık critical varsa rozet critical; yalnız warning → warning; açık yoksa ok."""
    from dashboard.fleet import BADGE_CRITICAL, BADGE_OK, BADGE_WARNING, derive_device_health

    readings = [_reading("dev", "motor_current")]
    crit = derive_device_health("dev", readings, [
        _alert(1, "dev", severity="warning"), _alert(2, "dev", severity="critical")])
    warn = derive_device_health("dev", readings, [_alert(1, "dev", severity="warning")])
    ok = derive_device_health("dev", readings, [_alert(1, "dev", status="resolved")])
    assert crit.badge == BADGE_CRITICAL
    assert warn.badge == BADGE_WARNING
    assert ok.badge == BADGE_OK


def test_device_health_snapshots_highlight_and_state() -> None:
    """Uyarıyla ilişkili sensör vurgulu; state en güncel okumadan; unit passthrough."""
    from dashboard.fleet import derive_device_health

    readings = [
        _reading("dev", "motor_current", value=11.2, unit="A", state="raising",
                 ts="2026-06-03T12:00:01.000Z"),
        _reading("dev", "vibration", value=0.05, unit="g", state="idle",
                 ts="2026-06-03T12:00:00.000Z"),
        _reading("other", "motor_current", value=0.5),  # başka cihaz — dahil edilmez
    ]
    health = derive_device_health("dev", readings, [_alert(1, "dev", sensor="motor_current")])
    assert health.state == "raising"  # en güncel okuma 12:00:01
    by_sensor = {s.sensor: s for s in health.snapshots}
    assert set(by_sensor) == {"motor_current", "vibration"}
    assert by_sensor["motor_current"].highlighted is True
    assert by_sensor["motor_current"].unit == "A"
    assert by_sensor["vibration"].highlighted is False
    assert health.open_alert_count == 1


def test_top_rule_highest_severity_then_recency() -> None:
    """En yüksek severity'li, eşitlikte en güncel açık uyarının kuralı seçilir."""
    from dashboard.fleet import derive_device_health

    alerts = [
        _alert(1, "dev", severity="warning", rule="old_warning", created_at="2026-06-03T11:00:00.000Z"),
        _alert(2, "dev", severity="critical", rule="the_critical", created_at="2026-06-03T10:00:00.000Z"),
        _alert(3, "dev", severity="warning", rule="new_warning", created_at="2026-06-03T12:00:00.000Z"),
    ]
    health = derive_device_health("dev", [_reading("dev", "motor_current")], alerts)
    assert health.top_rule == "the_critical"


def test_compute_kpis_counts_and_last_detection() -> None:
    """KPI: açık = active+acknowledged; kritik = açık ∧ critical; son tespit göreli."""
    from dashboard.fleet import compute_kpis

    alerts = [
        _alert(1, "a", status="active", severity="critical", created_at="2026-06-03T12:00:00.000Z"),
        _alert(2, "b", status="acknowledged", severity="warning", created_at="2026-06-03T11:59:00.000Z"),
        _alert(3, "c", status="resolved", severity="critical", created_at="2026-06-03T11:00:00.000Z"),
    ]
    now = datetime(2026, 6, 3, 12, 0, 30, tzinfo=UTC)
    kpis = compute_kpis(["a", "b", "c"], alerts, now)
    assert kpis.device_count == 3
    assert kpis.open_alert_count == 2
    assert kpis.critical_alert_count == 1
    assert kpis.last_detection == "30 sn önce"


def test_compute_kpis_no_alerts_dash() -> None:
    """Hiç uyarı yoksa son tespit '—'."""
    from dashboard.fleet import compute_kpis

    kpis = compute_kpis(["a"], [], datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC))
    assert kpis.last_detection == "—"
    assert kpis.open_alert_count == 0
```

- [ ] **Step 2: Testlerin FAIL ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_fleet.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.fleet'`

- [ ] **Step 3: Implementasyon**

`src/dashboard/fleet.py` (yeni dosya, tamamı):

```python
"""Filo sağlık + KPI türetimi (Faz 8 Iter 8.2 spec § 7). Saf — streamlit/DB import etmez."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alerts.models import Alert
from dashboard.transform import OPEN_STATUSES, relative_time
from ingestion.message_parser import IngestedReading

BADGE_OK = "ok"
BADGE_WARNING = "warning"
BADGE_CRITICAL = "critical"

_SEVERITY_RANK = {"warning": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class SensorSnapshot:
    """Bir sensörün karttaki son değeri."""

    sensor: str
    value: float
    unit: str
    highlighted: bool  # açık uyarıyla ilişkili sensör (spec § 3)


@dataclass(frozen=True)
class DeviceHealth:
    """Bir cihazın filo kartı verisi (spec § 3/§ 7)."""

    device_id: str
    badge: str  # BADGE_OK | BADGE_WARNING | BADGE_CRITICAL
    state: str
    snapshots: tuple[SensorSnapshot, ...]
    open_alert_count: int
    top_rule: str | None  # en yüksek severity'li (eşitlikte en güncel) açık uyarının kuralı


@dataclass(frozen=True)
class FleetKpis:
    """KPI satırı verisi (spec § 3/§ 7)."""

    device_count: int
    open_alert_count: int
    critical_alert_count: int
    last_detection: str  # göreli zaman veya "—"


def derive_device_health(
    device_id: str, latest_readings: list[IngestedReading], alerts: list[Alert]
) -> DeviceHealth:
    """Bir cihazın kart verisini son okumalar + uyarılardan türetir (spec § 7).

    Args:
        device_id: Cihaz kimliği.
        latest_readings: fetch_latest_readings çıktısı (TÜM cihazlar; içeride filtrelenir).
        alerts: fetch_alerts çıktısı (TÜM durumlar; açıklar içeride filtrelenir).

    Returns:
        DeviceHealth — rozet (critical > warning > ok), en güncel okumanın state'i,
        sensör snapshot'ları (uyarılı sensör vurgulu), açık uyarı sayısı, en kritik kural.
    """
    open_alerts = [
        a for a in alerts if a.device_id == device_id and a.status in OPEN_STATUSES
    ]
    readings = [r for r in latest_readings if r.device_id == device_id]
    flagged_sensors = {a.sensor for a in open_alerts}
    snapshots = tuple(
        SensorSnapshot(r.sensor, r.value, r.unit, r.sensor in flagged_sensors)
        for r in readings
    )
    state = max(readings, key=lambda r: r.timestamp).state if readings else "?"
    if any(a.severity == "critical" for a in open_alerts):
        badge = BADGE_CRITICAL
    elif open_alerts:
        badge = BADGE_WARNING
    else:
        badge = BADGE_OK
    top_rule: str | None = None
    if open_alerts:
        top = max(open_alerts, key=lambda a: (_SEVERITY_RANK.get(a.severity, 0), a.created_at))
        top_rule = top.rule_name
    return DeviceHealth(device_id, badge, state, snapshots, len(open_alerts), top_rule)


def derive_fleet(
    devices: list[str], latest_readings: list[IngestedReading], alerts: list[Alert]
) -> list[DeviceHealth]:
    """Tüm filo kartlarını türetir (cihaz sırası korunur)."""
    return [derive_device_health(d, latest_readings, alerts) for d in devices]


def compute_kpis(devices: list[str], alerts: list[Alert], now: datetime) -> FleetKpis:
    """KPI satırını tek fetch_alerts sonucundan client-side türetir (spec § 6/§ 7).

    Args:
        devices: Cihaz listesi.
        alerts: fetch_alerts(None, ...) çıktısı (tüm durumlar).
        now: Göreli zaman için UTC-aware datetime.

    Returns:
        FleetKpis — açık = status ∈ OPEN_STATUSES; kritik = açık ∧ severity=critical;
        son tespit = en güncel created_at göreli (uyarı yoksa "—").
    """
    open_alerts = [a for a in alerts if a.status in OPEN_STATUSES]
    critical_count = sum(1 for a in open_alerts if a.severity == "critical")
    last_detection = "—"
    if alerts:
        latest = max(alerts, key=lambda a: a.created_at)
        last_detection = relative_time(now, latest.created_at)
    return FleetKpis(len(devices), len(open_alerts), critical_count, last_detection)
```

- [ ] **Step 4: Testlerin PASS ettiğini doğrula + tam suite + lint + commit**

```bash
.venv/bin/python -m pytest tests/unit/test_dashboard_fleet.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/dashboard tests/unit/test_dashboard_fleet.py
ruff check src/dashboard tests/unit/test_dashboard_fleet.py
git add src/dashboard/fleet.py tests/unit/test_dashboard_fleet.py
git commit -m "feat(dashboard): fleet.py KPI + kart türetimi (DeviceHealth/FleetKpis, Faz 8 Iter 8.2 spec § 7)"
```

---

### Task 7: `repository.fetch_latest_readings`

**Files:**
- Modify: `src/storage/repository.py`
- Test: `tests/unit/test_storage_repository.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_storage_repository.py` sonuna ekle (dosyadaki mevcut `migrated_engine: Engine`
fixture deseni — doğrulandı, dosyada zaten kullanılıyor):

```python
def test_fetch_latest_readings_latest_per_device_sensor(migrated_engine: Engine) -> None:
    """Her (device, sensor) çifti için yalnız EN GÜNCEL okuma döner."""
    from ingestion.message_parser import IngestedReading
    from storage.repository import TelemetryRepository

    repo = TelemetryRepository(migrated_engine)
    rows = [
        IngestedReading(device_id="dev_a", sensor="motor_current",
                        timestamp="2026-06-03T12:00:00.000Z", state="idle", value=1.0, unit="A"),
        IngestedReading(device_id="dev_a", sensor="motor_current",
                        timestamp="2026-06-03T12:00:05.000Z", state="raising", value=2.0, unit="A"),
        IngestedReading(device_id="dev_a", sensor="vibration",
                        timestamp="2026-06-03T12:00:01.000Z", state="idle", value=0.05, unit="g"),
        IngestedReading(device_id="dev_b", sensor="motor_current",
                        timestamp="2026-06-03T12:00:02.000Z", state="holding", value=0.4, unit="A"),
    ]
    repo.insert_batch(rows)
    latest = repo.fetch_latest_readings()
    key = {(r.device_id, r.sensor): r for r in latest}
    assert len(latest) == 3  # (dev_a, motor_current) tekilleşti
    assert key[("dev_a", "motor_current")].value == 2.0  # en güncel kazandı
    assert key[("dev_a", "motor_current")].state == "raising"
    assert key[("dev_b", "motor_current")].state == "holding"


def test_fetch_latest_readings_empty_db(migrated_engine: Engine) -> None:
    """Boş tablo → boş liste."""
    from storage.repository import TelemetryRepository

    assert TelemetryRepository(migrated_engine).fetch_latest_readings() == []
```

- [ ] **Step 2: Testlerin FAIL ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_repository.py -q`
Expected: 2 FAIL — `AttributeError: ... 'fetch_latest_readings'`

- [ ] **Step 3: Implementasyon**

`src/storage/repository.py` — `fetch_window`'un altına ekle:

```python
    def fetch_latest_readings(self) -> list[IngestedReading]:
        """Her (device_id, sensor) çifti için en güncel okumayı döndürür (Faz 8 Iter 8.2 spec § 6).

        SQLite window function (ROW_NUMBER ... PARTITION BY) ile tek sorgu — filo kartlarının
        anlık state + son değer + unit kaynağı. Read-only (gözlem modu korunur).

        Returns:
            (device_id, sensor) sıralı IngestedReading listesi; boş tablo → boş liste.

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        row_number = (
            func.row_number()
            .over(
                partition_by=(telemetry.c.device_id, telemetry.c.sensor),
                order_by=telemetry.c.timestamp.desc(),
            )
            .label("rn")
        )
        sub = select(telemetry, row_number).subquery()
        stmt = select(sub).where(sub.c.rn == 1).order_by(sub.c.device_id, sub.c.sensor)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_reading(row) for row in rows]
```

(`_row_to_reading` isimle erişir — fazladan `rn` kolonu sorun değil.)

- [ ] **Step 4: Testlerin PASS ettiğini doğrula + tam suite + lint + commit**

```bash
.venv/bin/python -m pytest tests/unit/test_storage_repository.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/storage tests/unit/test_storage_repository.py
ruff check src/storage tests/unit/test_storage_repository.py
git add src/storage/repository.py tests/unit/test_storage_repository.py
git commit -m "feat(storage): fetch_latest_readings — (device,sensor) başına en güncel okuma (Faz 8 Iter 8.2 spec § 6)"
```

---

### Task 8: `charts.py` — Altair builder + anomali overlay (+ `readings_to_chart_frame`)

**Files:**
- Create: `src/dashboard/charts.py`
- Modify: `src/dashboard/transform.py` (`readings_to_chart_frame` — tooltip için state kolonu)
- Test: `tests/unit/test_dashboard_charts.py` (yeni) + `tests/unit/test_dashboard_transform.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/unit/test_dashboard_transform.py` sonuna:

```python
def test_readings_to_chart_frame_columns() -> None:
    """Chart frame'i timestamp/value/state kolonlu (index DEĞİL — altair kolon ister)."""
    from dashboard.transform import readings_to_chart_frame
    from ingestion.message_parser import IngestedReading

    readings = [IngestedReading(device_id="d", sensor="motor_current",
                                timestamp="2026-06-03T12:00:00.000Z", state="raising",
                                value=1.5, unit="A")]
    frame = readings_to_chart_frame(readings)
    assert list(frame.columns) == ["timestamp", "value", "state"]
    assert frame.iloc[0]["state"] == "raising"
    assert len(readings_to_chart_frame([])) == 0
```

`tests/unit/test_dashboard_charts.py` (yeni dosya):

```python
"""dashboard.charts Altair builder birim testleri (Faz 8 Iter 8.2 spec § 5)."""
from __future__ import annotations

from alerts.models import Alert
from dashboard.transform import readings_to_chart_frame
from ingestion.message_parser import IngestedReading


def _readings(n: int = 5) -> list[IngestedReading]:
    return [
        IngestedReading(device_id="dev", sensor="motor_current",
                        timestamp=f"2026-06-03T12:00:0{i}.000Z", state="raising",
                        value=float(i), unit="A")
        for i in range(n)
    ]


def _alert(sensor: str = "motor_current") -> Alert:
    return Alert(id=1, device_id="dev", rule_name="motor_current_high", sensor=sensor,
                 severity="critical", score=0.86,
                 window_start="2026-06-03T12:00:01.000Z", window_end="2026-06-03T12:00:03.000Z",
                 value=3.0, description="d", created_at="2026-06-03T12:00:03.000Z",
                 status="active", acknowledged_at=None, resolved_at=None)


def test_chart_without_alerts_single_line_layer() -> None:
    """Uyarı yoksa katmansız tek çizgi chart döner (spec § 5 boş overlay)."""
    from dashboard.charts import build_sensor_chart

    chart = build_sensor_chart(readings_to_chart_frame(_readings()), [], "motor_current", "A")
    spec = chart.to_dict()
    assert "layer" not in spec
    assert spec["mark"]["type"] == "line"
    assert spec["encoding"]["y"]["title"] == "motor_current (A)"


def test_chart_with_alert_has_four_layers() -> None:
    """Uyarılı chart 4 katman: bant(rect) + çizgi(rule) + etiket(text) + telemetri(line)."""
    from dashboard.charts import build_sensor_chart

    chart = build_sensor_chart(
        readings_to_chart_frame(_readings()), [_alert()], "motor_current", "A")
    spec = chart.to_dict()
    marks = [layer["mark"]["type"] for layer in spec["layer"]]
    assert marks == ["rect", "rule", "text", "line"]


def test_chart_ignores_other_sensor_alerts() -> None:
    """Başka sensörün uyarısı bu grafiğe bant ÇİZMEZ (fused temsilci-sensör kuralı)."""
    from dashboard.charts import build_sensor_chart

    chart = build_sensor_chart(
        readings_to_chart_frame(_readings()), [_alert(sensor="vibration")], "motor_current", "A")
    assert "layer" not in chart.to_dict()


def test_overlay_frame_label_format() -> None:
    """Etiket '⚠ {rule} ({score:.2f})' formatında."""
    from dashboard.charts import alerts_to_overlay_frame

    frame = alerts_to_overlay_frame([_alert()])
    assert frame.iloc[0]["label"] == "⚠ motor_current_high (0.86)"
    assert list(frame.columns) == ["window_start", "window_end", "severity", "label"]
```

- [ ] **Step 2: Testlerin FAIL ettiğini doğrula**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_charts.py tests/unit/test_dashboard_transform.py -q`
Expected: FAIL — ModuleNotFoundError `dashboard.charts` + ImportError `readings_to_chart_frame`

- [ ] **Step 3: `readings_to_chart_frame` implementasyonu**

`src/dashboard/transform.py` — `readings_to_frame`'in altına:

```python
def readings_to_chart_frame(readings: list[IngestedReading]) -> pd.DataFrame:
    """IngestedReading listesini Altair chart frame'ine çevirir (spec § 5 tooltip: state dahil).

    readings_to_frame'den farkı: timestamp INDEX değil KOLON (altair kolon encode eder)
    ve tooltip için state kolonu taşır.

    Args:
        readings: timestamp ASC sıralı okumalar (boş olabilir).

    Returns:
        [timestamp (datetime), value, state] kolonlu DataFrame.
    """
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [r.timestamp for r in readings], format="ISO8601", utc=True
            ),
            "value": [r.value for r in readings],
            "state": [r.state for r in readings],
        }
    )
```

- [ ] **Step 4: `charts.py` implementasyonu**

`src/dashboard/charts.py` (yeni dosya, tamamı):

```python
"""Altair chart builder'ları (Faz 8 Iter 8.2 spec § 5). Saf — streamlit/DB import etmez."""
from __future__ import annotations

import altair as alt
import pandas as pd

from alerts.models import Alert

LINE_COLOR = "#1d4ed8"  # tema B lacivert (spec § 4)

# Severity → bant/çizgi/etiket rengi (tema B paleti, spec § 4)
SEVERITY_COLORS = {"critical": "#b91c1c", "high": "#ea580c", "warning": "#a16207"}

BAND_OPACITY = 0.15


def alerts_to_overlay_frame(alerts: list[Alert]) -> pd.DataFrame:
    """Alert listesini overlay katmanlarının veri frame'ine çevirir (spec § 5).

    Args:
        alerts: Grafiğin sensörüne ait uyarılar (boş olabilir).

    Returns:
        [window_start (datetime), window_end (datetime), severity, label] kolonlu DataFrame;
        label = "⚠ {rule_name} ({score:.2f})".
    """
    return pd.DataFrame(
        {
            "window_start": pd.to_datetime(
                [a.window_start for a in alerts], format="ISO8601", utc=True
            ),
            "window_end": pd.to_datetime(
                [a.window_end for a in alerts], format="ISO8601", utc=True
            ),
            "severity": [a.severity for a in alerts],
            "label": [f"⚠ {a.rule_name} ({a.score:.2f})" for a in alerts],
        }
    )


def _severity_color() -> alt.Color:
    """Overlay katmanları için paylaşılan severity renk encoding'i (legend kapalı)."""
    return alt.Color(
        "severity:N",
        scale=alt.Scale(domain=list(SEVERITY_COLORS), range=list(SEVERITY_COLORS.values())),
        legend=None,
    )


def build_sensor_chart(
    frame: pd.DataFrame, alerts: list[Alert], sensor: str, unit: str
) -> alt.LayerChart | alt.Chart:
    """Bir sensörün telemetri çizgisi + anomali overlay'li Altair chart'ını kurar (spec § 5).

    Katmanlar (alttan üste): severity bandı (mark_rect) → başlangıç çizgisi (mark_rule,
    kesikli) → kural etiketi (mark_text) → telemetri çizgisi (mark_line, tooltip'li).
    Bu sensöre ait uyarı yoksa (veya frame boşsa) yalnız çizgi döner.

    Args:
        frame: readings_to_chart_frame çıktısı (timestamp/value/state; downsample edilmiş).
        alerts: Seçili cihazın uyarıları (TÜM sensörler; içeride sensor'e filtrelenir —
            fused(N) bandı yalnız temsilci Alert.sensor grafiğine çizilir, spec § 7).
        sensor: Sensör adı (y-ekseni başlığı).
        unit: Birim etiketi (DB'den; boşsa başlık yalnız sensör adı).

    Returns:
        İnteraktif (zoom/pan) Altair chart'ı.
    """
    y_title = f"{sensor} ({unit})" if unit else sensor
    line = (
        alt.Chart(frame)
        .mark_line(color=LINE_COLOR)
        .encode(
            x=alt.X("timestamp:T", title=None),
            y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("timestamp:T", format="%H:%M:%S", title="zaman"),
                alt.Tooltip("value:Q", title="değer", format=".3f"),
                alt.Tooltip("state:N", title="state"),
            ],
        )
    )
    relevant = [a for a in alerts if a.sensor == sensor]
    if frame.empty or not relevant:
        return line.interactive()

    # x-domain telemetri verisinden sabitlenir — bant domain'i esnetmesin (spec § 5).
    domain = [frame["timestamp"].min(), frame["timestamp"].max()]
    line = line.encode(x=alt.X("timestamp:T", title=None, scale=alt.Scale(domain=domain)))
    overlay = alerts_to_overlay_frame(relevant)
    band = (
        alt.Chart(overlay)
        .mark_rect(opacity=BAND_OPACITY, clip=True)
        .encode(x="window_start:T", x2="window_end:T", color=_severity_color())
    )
    rule = (
        alt.Chart(overlay)
        .mark_rule(strokeDash=[4, 2], clip=True)
        .encode(x="window_start:T", color=_severity_color())
    )
    text = (
        alt.Chart(overlay)
        .mark_text(align="left", baseline="top", dx=4, clip=True)
        .encode(x="window_start:T", y=alt.value(8), text="label:N", color=_severity_color())
    )
    return alt.layer(band, rule, text, line).interactive()
```

- [ ] **Step 5: Testlerin PASS ettiğini doğrula + tam suite + lint + commit**

```bash
.venv/bin/python -m pytest tests/unit/test_dashboard_charts.py tests/unit/test_dashboard_transform.py -q   # PASS
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m mypy src/dashboard tests/unit/test_dashboard_charts.py
ruff check src/dashboard tests/unit/test_dashboard_charts.py
git add src/dashboard/charts.py src/dashboard/transform.py tests/unit/test_dashboard_charts.py tests/unit/test_dashboard_transform.py
git commit -m "feat(dashboard): Altair sensör grafiği + anomali overlay builder'ları (Faz 8 Iter 8.2 spec § 5)"
```

---

### Task 9: `app.py` rework — komuta merkezi layout + AppTest boot smoke

**Files:**
- Modify: `src/dashboard/app.py` (büyük rework — aşağıdaki TAM içerikle değiştir)
- Test: `tests/unit/test_dashboard_app_boot.py` (yeni)

- [ ] **Step 1: AppTest boot testini yaz**

`tests/unit/test_dashboard_app_boot.py` (yeni dosya):

```python
"""Dashboard AppTest boot smoke (Faz 8 Iter 8.2 spec § 10).

Boş DB (tablo yok) → main() list_devices OperationalError guard'ında st.info ile erken döner;
fragment'lere ulaşılmaz (run_every fragment AppTest'te timeout verir — bilinen gotcha).
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_app_boots_with_empty_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tablosuz boş DB ile app exception'sız boot eder, info mesajı gösterir."""
    from streamlit.testing.v1 import AppTest

    db = tmp_path / "empty.db"
    db.touch()
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(db))
    at = AppTest.from_file("src/dashboard/app.py", default_timeout=10)
    at.run()
    assert not at.exception
    assert len(at.info) >= 1  # "Henüz veri yok" bilgilendirmesi
```

- [ ] **Step 2: Testin mevcut app ile PASS ettiğini doğrula (guard zaten var)**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_app_boot.py -q`
Expected: PASS (mevcut app.py'de de guard var — bu test rework'ün regresyon ağıdır).
FAIL ederse durumu rapor et, rework'e geçmeden nedeni anla.

- [ ] **Step 3: app.py'yi yeniden yaz**

`src/dashboard/app.py` TAM içerik (mevcut dosyayı değiştir):

```python
"""Streamlit dashboard entry (Faz 8 Iter 8.2): streamlit run src/dashboard/app.py.

Tek sayfa komuta merkezi (spec § 3): KPI satırı → filo sağlık kartları → severity-stilli
uyarı akışı (cihaz-özeti varsayılan) → uyarı yönetimi → seçili cihazın 6 Altair grafiği
(anomali overlay'li). Üst blok 5s, grafikler 2s fragment; yönetim fragment DIŞI (S1).
SQLite'ı read-only sorgular; tek yazma yolu uyarı durumu geçişleri (gözlem modu).

db_path: DASHBOARD_DB_PATH env varsa o, yoksa config/ingestion.yaml db_path.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

# `streamlit run src/dashboard/app.py` yalnızca src/dashboard'ı sys.path'e ekler; top-level
# paketler (dashboard, ingestion, storage) için src/ kökünü ekle. Editable install .pth'i
# Python 3.11.15 hardening ile silent-skip edildiğinden bu bootstrap gerekir (env notu).
_SRC_ROOT = Path(__file__).resolve().parent.parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

import streamlit as st  # noqa: E402
from loguru import logger  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from alerts.lifecycle import ACKNOWLEDGED, RESOLVED, can_transition  # noqa: E402
from alerts.models import Alert  # noqa: E402
from dashboard.charts import build_sensor_chart  # noqa: E402
from dashboard.fleet import (  # noqa: E402
    BADGE_CRITICAL,
    BADGE_OK,
    BADGE_WARNING,
    DeviceHealth,
    compute_kpis,
    derive_fleet,
)
from dashboard.transform import (  # noqa: E402
    OPEN_STATUSES,
    WINDOW_OPTIONS,
    alerts_to_frame,
    downsample_frame,
    latest_alert_per_device,
    readings_to_chart_frame,
    severity_row_style,
    window_to_since,
)
from ingestion.config import load_ingestion_config  # noqa: E402
from storage.engine import create_sqlite_engine  # noqa: E402
from storage.repository import TelemetryRepository  # noqa: E402

SIX_SENSORS = [
    "motor_current",
    "motor_voltage",
    "hydraulic_pressure",
    "motor_temperature",
    "mast_position",
    "vibration",
]

ALERTS_FETCH_LIMIT = 200  # spec § 6 — tek fetch, client-side türetim

_BADGE_LABELS = {
    BADGE_OK: "🟢 OK",
    BADGE_WARNING: "🟡 UYARI",
    BADGE_CRITICAL: "🔴 KRİTİK",
}

# Uyarı akışı görünümleri (spec § 3): cihaz özeti varsayılan; gerisi durum filtresi.
_VIEW_OPTIONS = ["Cihaz özeti", "Açık", "Tümü", "active", "acknowledged", "resolved"]


def _resolve_db_path() -> Path:
    """DASHBOARD_DB_PATH env override; yoksa ingestion.yaml db_path."""
    env = os.environ.get("DASHBOARD_DB_PATH")
    if env:
        return Path(env)
    return load_ingestion_config(Path("config/ingestion.yaml")).db_path


@st.cache_resource
def _get_repository() -> TelemetryRepository:
    """Engine + repository bir kez kurulur (her rerun'da yeniden açılmaz)."""
    engine = create_sqlite_engine(_resolve_db_path())
    return TelemetryRepository(engine)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _apply_transition(fn: Callable[[int, str], bool], alert_id: int) -> None:
    """Geçiş metodunu çağırır; sonuca göre kullanıcıyı bilgilendirir (Faz 7 spec § 9)."""
    try:
        ok = fn(alert_id, _now_iso())
    except OperationalError as e:
        logger.error("Uyarı durumu yazılamadı: {}", e)
        st.error("Uyarı durumu güncellenemedi (DB hatası).")
        return
    if not ok:
        st.info("Uyarı durumu değişmiş olabilir — listeyi yenileyin.")


def _fetch_alerts_safe(repository: TelemetryRepository) -> tuple[list[Alert], bool]:
    """Uyarıları çeker; anomalies tablosu yoksa (boş, False) döner — üst blok degrade (spec § 9)."""
    try:
        return repository.fetch_alerts(None, ALERTS_FETCH_LIMIT), True
    except OperationalError as e:
        logger.info("anomalies tablosu henüz yok: {}", e)
        return [], False


def _filter_view(alerts: list[Alert], view: str) -> list[Alert]:
    """Uyarı akışı görünümünü tek fetch sonucundan client-side türetir (spec § 6)."""
    if view == "Cihaz özeti":
        return latest_alert_per_device(alerts)
    if view == "Açık":
        return [a for a in alerts if a.status in OPEN_STATUSES]
    if view == "Tümü":
        return alerts
    return [a for a in alerts if a.status == view]


def _render_fleet_cards(fleet_health: list[DeviceHealth]) -> None:
    """Filo sağlık kartlarını çizer (spec § 3 madde 3)."""
    if not fleet_health:
        return
    cols = st.columns(len(fleet_health))
    for col, health in zip(cols, fleet_health):
        with col, st.container(border=True):
            st.markdown(f"**{health.device_id}** · {_BADGE_LABELS[health.badge]}")
            st.caption(f"state: {health.state}")
            lines = []
            for snap in health.snapshots:
                text = f"{snap.sensor}: {snap.value:.2f} {snap.unit}"
                # Bold renk köşeli parantezinin İÇİNDE — Streamlit'in dokümante deseni
                # (":red[**...**]"); dışarıda iç içe markdown 1.36'da kırılgan (plan review S2).
                lines.append(f":red[**{text}**]" if snap.highlighted else text)
            st.markdown("  \n".join(lines))
            if health.open_alert_count:
                st.caption(f"⚠ {health.open_alert_count} açık uyarı · {health.top_rule}")


@st.experimental_fragment(run_every="5s")
def _render_overview(repository: TelemetryRepository) -> None:
    """Üst blok: KPI satırı + filo kartları + uyarı akışı; 5s'de bir yenilenir (spec § 3).

    SALT-GÖRÜNTÜ (gözlem modu). Sorgu bütçesi: fetch_alerts + fetch_latest_readings (spec § 6).
    """
    alerts, alerts_available = _fetch_alerts_safe(repository)
    try:
        latest = repository.fetch_latest_readings()
    except OperationalError as e:
        logger.error("Son okumalar alınamadı: {}", e)
        st.error("Son okumalar alınamadı (DB hatası).")
        return
    devices = sorted({r.device_id for r in latest})
    now = datetime.now(UTC)

    kpis = compute_kpis(devices, alerts, now)
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Cihaz", kpis.device_count)
    kpi_cols[1].metric("Açık uyarı", kpis.open_alert_count)
    kpi_cols[2].metric("Kritik", kpis.critical_alert_count)
    kpi_cols[3].metric("Son tespit", kpis.last_detection)
    if not alerts_available:
        st.caption("Detector henüz çalışmadı — uyarı verisi yok (`python -m detectors`).")

    _render_fleet_cards(derive_fleet(devices, latest, alerts))

    st.subheader("🚨 Uyarılar")
    choice = st.selectbox("Görünüm", _VIEW_OPTIONS, index=0, key="alert_view")
    visible = _filter_view(alerts, choice or "Cihaz özeti")
    if not visible:
        st.caption("Bu görünümde uyarı yok.")
        return
    frame = alerts_to_frame(visible, now)
    st.dataframe(
        frame.style.apply(severity_row_style, axis=1),
        use_container_width=True,
        hide_index=True,
    )


def _render_alert_management(repository: TelemetryRepository) -> None:
    """Açık bir uyarı seçip ack/resolve eden yönetim kontrolü (main() içinde, fragment DIŞINDA, S1).

    Gözlem modu: yalnız uyarı DURUMU yazılır (telemetri değil, cihaz komutu değil). Buton tıklaması
    tam app rerun'ı tetikler → liste tazelenir.
    """
    try:
        open_alerts = repository.fetch_alerts(OPEN_STATUSES, limit=50)
    except OperationalError:
        return  # tablo yoksa _render_overview zaten bilgilendirdi
    if not open_alerts:
        return
    options = {f"#{a.id} {a.device_id} · {a.rule_name} ({a.status})": a for a in open_alerts}
    label = st.selectbox("Uyarı yönet", list(options.keys()), key="alert_manage")
    selected = options.get(label) if label else None
    if selected is None:
        return
    cols = st.columns(2)
    if can_transition(selected.status, ACKNOWLEDGED) and cols[0].button("Gör (ack)", key="ack_btn"):
        _apply_transition(repository.acknowledge_alert, selected.id)
    if can_transition(selected.status, RESOLVED) and cols[1].button("Çöz (resolve)", key="resolve_btn"):
        _apply_transition(repository.resolve_alert, selected.id)


@st.experimental_fragment(run_every="2s")
def _render_charts(repository: TelemetryRepository, device_id: str, window: str) -> None:
    """Seçili cihazın 6 sensörünü anomali overlay'li Altair grafikleriyle çizer (spec § 3/§ 5)."""
    since = window_to_since(datetime.now(UTC), window)
    alerts, _ = _fetch_alerts_safe(repository)
    device_alerts = [a for a in alerts if a.device_id == device_id]
    if since is not None:
        # Uyarı penceresi ∩ grafik zaman penceresi (lexicographic ISO karşılaştırma, spec § 6)
        device_alerts = [a for a in device_alerts if a.window_end >= since]
    cols = st.columns(2)
    for i, sensor in enumerate(SIX_SENSORS):
        try:
            readings = repository.fetch_window(device_id, sensor, since)
        except OperationalError as e:
            logger.error("Okuma hatası device={} sensor={}: {}", device_id, sensor, e)
            with cols[i % 2]:
                st.error(f"{sensor}: okuma hatası")
            continue
        frame = downsample_frame(readings_to_chart_frame(readings))
        unit = readings[-1].unit if readings else ""
        with cols[i % 2]:
            st.subheader(sensor)
            st.altair_chart(
                build_sensor_chart(frame, device_alerts, sensor, unit),
                use_container_width=True,
                theme="streamlit",
            )


def main() -> None:
    """Dashboard ana akışı (spec § 3 sayfa yapısı)."""
    st.set_page_config(page_title="Mast Filo İzleme", layout="wide")
    st.title("Mast Filo İzleme")
    st.caption("Teleskopik mast filosu — gerçek zamanlı telemetri ve erken uyarı (gözlem modu)")

    try:
        repository = _get_repository()
    except FileNotFoundError as e:
        logger.error("Yapılandırma/DB bulunamadı: {}", e)
        st.error(f"Yapılandırma/DB bulunamadı: {e} — config/ingestion.yaml var mı, ingestion çalıştı mı?")
        return

    try:
        devices = repository.list_devices()
    except OperationalError as e:
        logger.info("telemetry tablosu henüz yok: {}", e)
        st.info(
            "Henüz veri yok — ingestion telemetry tablosunu oluşturmadı"
            " (simulator + ingestion çalışıyor mu?)"
        )
        return

    if not devices:
        st.info("Henüz veri yok — simulator + ingestion çalışıyor mu?")
        return

    _render_overview(repository)
    _render_alert_management(repository)
    st.divider()

    device_id: str = st.sidebar.selectbox("Cihaz", devices) or devices[0]
    window: str = st.sidebar.selectbox("Zaman aralığı", list(WINDOW_OPTIONS.keys()), index=1) or list(WINDOW_OPTIONS.keys())[1]
    _render_charts(repository, device_id, window)


# Streamlit betiği yukarıdan aşağıya çalıştırır; __main__ guard yok.
# Bu modülü import ETME — main() import-time çalışır ve Streamlit runtime gerektirir.
main()
```

- [ ] **Step 4: Boot testi + tam suite PASS doğrula**

```bash
.venv/bin/python -m pytest tests/unit/test_dashboard_app_boot.py -q   # PASS
.venv/bin/python -m pytest tests/ -q                                  # tamamı PASS
.venv/bin/python -m mypy src/dashboard tests/unit/test_dashboard_app_boot.py
ruff check src/dashboard tests/unit/test_dashboard_app_boot.py
```

- [ ] **Step 5: Headless görsel sanity (manuel-benzeri)**

```bash
DASHBOARD_DB_PATH=data/telemetry.db .venv/bin/python -m streamlit run src/dashboard/app.py --server.headless true --server.port 8599 & SRV=$!
sleep 6 && curl -s http://localhost:8599 | head -c 200; kill $SRV
```

Expected: HTML çıktı (sunucu ayakta). Bu yalnız boot doğrular — gerçek görsel doğrulama
Task 10 sonrası canlı demo smoke'ta (controller).

- [ ] **Step 6: Commit**

```bash
git add src/dashboard/app.py tests/unit/test_dashboard_app_boot.py
git commit -m "feat(dashboard): komuta merkezi layout — KPI + filo kartları + stilli uyarı akışı + Altair overlay grafikleri (Faz 8 Iter 8.2 spec § 3)"
```

---

### Task 10: Final sweep — tam suite + mypy + ruff (tüm kapsam)

**Files:** (yalnız doğrulama; düzeltme gerekirse ilgili dosyalar)

- [ ] **Step 1: Tam test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: tamamı PASS (313 + bu iterasyonun yenileri; 1 smoke skipped)

- [ ] **Step 2: mypy tam kapsam**

Run: `.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/dashboard src/alerts tests/unit tests/integration tests/scenarios`
Expected: Success. (Altair 5.5.0 `py.typed` taşır — override GEREKMEMELİ; hata çıkarsa
pandas-tarzı dar override eklemeden önce hatayı incele ve rapor et.)

- [ ] **Step 3: ruff tam kapsam**

Run: `ruff check src tests`
Expected: All checks passed.

- [ ] **Step 4: Düzeltme gerektiyse commit**

```bash
git add -A && git commit -m "chore(faz8): Iter 8.2 final lint/type sweep düzeltmeleri"
```

(Düzeltme yoksa bu step atlanır.)

---

## Closure (controller işi — plan task'ı DEĞİL)

Subagent execution bittikten sonra controller: (1) final whole-iteration review,
(2) **canlı demo smoke** `./scripts/demo_up.sh` — spec § 10'un 7 maddesi
(tema / KPI / 4 kart / dev_002 overlay / cihaz-özeti flicker'sız / temiz cihaz 0 FP / teardown),
(3) CLAUDE.md + ROADMAP + memory güncelle, (4) kullanıcı onayıyla merge/push (PROAKTİF YAPMA).

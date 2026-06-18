# Faz 8 Iter 8.6 — "Yaşayan Uyarı" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uyarı kimliğini cihaz-seviyesi tek "olay"a taşıyıp arıza süresince in-place güncellenen (skor/değer/severity), eskalasyonda tek satır kalan, severity'si band skorundan türetilen, ack sonrası kötüleşince yeniden aktifleşen "yaşayan uyarı" davranışı kurmak.

**Architecture:** `_detect_once` reconciliation'ı fingerprint-kimliğinden (8.5) **cihaz-seviyesi tek incident** kimliğine taşınır: cihaz firing + açık uyarı var → o satırı UPDATE (skor refresh + eskalasyon birleşik); açık yok → yeni aç; temiz → resolve. Severity, fusion'dan ÖNCE her band-skorlu anomaliye band'dan türetilir (sensör-sağlığı muaf). Migration yok; mevcut kolonlar UPDATE edilir. `Anomaly`/`fuse_anomalies`/gözlem-modu değişmez.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 Core, pandas, pytest, mypy (strict), ruff, loguru.

## Global Constraints

- **Spec (tek hakem):** `docs/specs/2026-06-18-faz8-iter8-6-living-alert-design.md`.
- **Migration YOK** — tüm değişiklikler mevcut `anomalies` kolonlarına UPDATE.
- **Değişmez kontratlar:** `Anomaly` (write dataclass), `fuse_anomalies`, `Detector` ABC, `band_position_score`, skor `[0,1]`, gözlem modu (yalnız `telemetry` oku / `anomalies` yaz), ACK yaşam döngüsü (`can_transition`, `acknowledge_alert`, `resolve_open_alerts`).
- **Severity eşikleri config-driven** (hand-picked sabit yok): global `severity_bands: {high_cutoff, critical_cutoff}`. Defaults `0.40` / `0.75` (dataclass'ta tek kaynak; example/demo YAML otoritatif).
- **Sensör-sağlığı muaf:** `VALIDITY_RULES = {"sensor_out_of_range", "sensor_frozen"}` band'dan türetilmez (config severity korur).
- **Tip ipuçları zorunlu** (mypy strict), **docstring zorunlu** (Google stili), `loguru` (print yok).
- **Test komutu:** `.venv/bin/python -m pytest <path> -v`. Tam suite: `.venv/bin/python -m pytest`. Lint: `mypy src/... tests/...` (.venv) + `ruff check src/... tests/...` (**ruff = homebrew PATH**, `.venv/bin/python -m ruff` YOK).
- **Yürütme ortamı gerçeği:** subagent'lar Bash/Write izinsiz → controller-inline implement + salt-okunur reviewer (8.4/8.5 hibrit).

---

## Dosya Haritası

| Dosya | Sorumluluk | Değişim |
|---|---|---|
| `src/detectors/scoring.py` | band → severity saf eşleme | +`severity_from_band` |
| `src/detectors/fusion.py` | severity rank tek kaynak | `_SEVERITY_RANK` → public `SEVERITY_RANK` |
| `src/detectors/config.py` | `severity_bands` config | +`SeverityBands` + `DetectorConfig.severity_bands` + loader |
| `src/detectors/service.py` | reconciliation + severity uygulama | +`VALIDITY_RULES`,`apply_band_severity`,`_reconcile_status`; `_detect_once` rework; `run()` wire |
| `src/storage/repository.py` | açık-uyarı okuma + in-place update | +`fetch_open_alerts`,`update_alert`,`resolve_alert_by_id`; −`fetch_open_fingerprints` |
| `config/detectors.yaml.example`, `config/detectors.demo.yaml` | severity_bands bloğu | +global blok |
| tests | TDD | yeni + 8.5 fingerprint testleri dönüştürülür |

---

### Task 1: `severity_from_band` saf fonksiyon

**Files:**
- Modify: `src/detectors/scoring.py`
- Test: `tests/unit/detectors/test_scoring.py`

**Interfaces:**
- Produces: `severity_from_band(score: float, high_cutoff: float, critical_cutoff: float) -> str` (`"warning"|"high"|"critical"`).

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/detectors/test_scoring.py`)

```python
from detectors.scoring import band_position_score, severity_from_band  # mevcut importu genişlet


def test_severity_below_high_cutoff_is_warning() -> None:
    assert severity_from_band(0.0, high_cutoff=0.40, critical_cutoff=0.75) == "warning"
    assert severity_from_band(0.39, high_cutoff=0.40, critical_cutoff=0.75) == "warning"


def test_severity_at_high_cutoff_is_high() -> None:
    assert severity_from_band(0.40, high_cutoff=0.40, critical_cutoff=0.75) == "high"
    assert severity_from_band(0.74, high_cutoff=0.40, critical_cutoff=0.75) == "high"


def test_severity_at_critical_cutoff_is_critical() -> None:
    assert severity_from_band(0.75, high_cutoff=0.40, critical_cutoff=0.75) == "critical"
    assert severity_from_band(1.0, high_cutoff=0.40, critical_cutoff=0.75) == "critical"


def test_severity_invalid_cutoffs_raises() -> None:
    import pytest
    with pytest.raises(ValueError, match="cutoff"):
        severity_from_band(0.5, high_cutoff=0.75, critical_cutoff=0.40)  # high >= critical
    with pytest.raises(ValueError, match="cutoff"):
        severity_from_band(0.5, high_cutoff=0.0, critical_cutoff=0.75)   # 0 < high gerekir
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_scoring.py -v`
Expected: FAIL (`cannot import name 'severity_from_band'`).

- [ ] **Step 3: Implement** (append to `src/detectors/scoring.py`)

```python
def severity_from_band(score: float, high_cutoff: float, critical_cutoff: float) -> str:
    """Band-pozisyon skorunu (`0..1`) severity etiketine eşler.

    `0` = alarm bölgesine yeni girdi (en az "warning"), `1` = kritik (trip). Eşikler ISO 20816
    zone mantığı + sim kalibrasyonu (config-driven, hand-picked sabit yok — spec § 6).

    Args:
        score: Band-pozisyon skoru `[0, 1]`.
        high_cutoff: `>= high_cutoff` → en az "high".
        critical_cutoff: `>= critical_cutoff` → "critical".

    Returns:
        `"warning" | "high" | "critical"`.

    Raises:
        ValueError: `0 < high_cutoff < critical_cutoff < 1` değilse.
    """
    if not (0.0 < high_cutoff < critical_cutoff < 1.0):
        raise ValueError(
            f"severity_from_band: 0 < high_cutoff ({high_cutoff}) < "
            f"critical_cutoff ({critical_cutoff}) < 1 olmalı"
        )
    if score >= critical_cutoff:
        return "critical"
    if score >= high_cutoff:
        return "high"
    return "warning"
```

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_scoring.py -v`
Expected: PASS (mevcut + 4 yeni).

- [ ] **Step 5: Commit**

```bash
git add src/detectors/scoring.py tests/unit/detectors/test_scoring.py
git commit -m "feat(detectors): severity_from_band band→severity eşlemesi (Faz 8 Iter 8.6 (4))"
```

---

### Task 2: Repository — `fetch_open_alerts` + `update_alert` + `resolve_alert_by_id` (additive)

**Files:**
- Modify: `src/storage/repository.py`
- Test: `tests/unit/test_storage_alert_repository.py`

**Interfaces:**
- Consumes: `Alert` (alerts.models), `ACTIVE/ACKNOWLEDGED/RESOLVED` (alerts.lifecycle), `anomalies` (storage.schema).
- Produces:
  - `fetch_open_alerts() -> dict[str, list[Alert]]` — açık (active|acknowledged) uyarılar, device_id'ye gruplu, her liste created_at ASC.
  - `update_alert(alert_id: int, *, severity: str, score: float, value: float, window_end: str, rule_set: str, description: str, status: str, acknowledged_at: str | None) -> bool` — id ile satırı günceller; rowcount>0.
  - `resolve_alert_by_id(alert_id: int, resolved_at: str) -> bool` — tek satırı resolved yapar (WHERE id AND status!=resolved).

> NOT: `fetch_open_fingerprints` bu task'ta KALIR (service hâlâ kullanır → suite yeşil). Task 6'da silinir.

- [ ] **Step 1: Write failing tests** (append to `tests/unit/test_storage_alert_repository.py`)

```python
def test_fetch_open_alerts_groups_by_device(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(device="d1", rule="motor_current_high"), "2026-06-03T10:00:00.000Z", "motor_current_high")
    repo.insert_anomaly(_anom(device="d1", rule="fused(2)"), "2026-06-03T10:00:01.000Z", "motor_current_high,vibration_elevated")
    repo.insert_anomaly(_anom(device="d2"), "2026-06-03T10:00:02.000Z", "motor_current_high")
    repo.resolve_open_alerts("d2", "2026-06-03T10:01:00.000Z")  # d2 kapanır → görünmez

    open_alerts = repo.fetch_open_alerts()
    assert set(open_alerts.keys()) == {"d1"}
    assert len(open_alerts["d1"]) == 2
    assert [a.created_at for a in open_alerts["d1"]] == sorted(a.created_at for a in open_alerts["d1"])  # ASC


def test_update_alert_changes_fields(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id

    ok = repo.update_alert(
        alert_id, severity="critical", score=0.9, value=12.5,
        window_end="2026-06-03T10:05:00.000Z", rule_set="motor_current_high,vibration_elevated",
        description="updated", status="active", acknowledged_at=None,
    )
    assert ok is True
    a = repo.fetch_alerts(None, limit=10)[0]
    assert (a.severity, a.score, a.value, a.window_end, a.description) == (
        "critical", 0.9, 12.5, "2026-06-03T10:05:00.000Z", "updated")
    assert a.created_at == "2026-06-03T10:00:00.000Z"  # created_at DOKUNULMAZ


def test_update_alert_reactivates(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id
    repo.acknowledge_alert(alert_id, "2026-06-03T10:01:00.000Z")

    repo.update_alert(alert_id, severity="critical", score=0.9, value=12.5,
                      window_end="w", rule_set="motor_current_high", description="d",
                      status="active", acknowledged_at=None)
    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "active" and a.acknowledged_at is None


def test_resolve_alert_by_id(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id

    assert repo.resolve_alert_by_id(alert_id, "2026-06-03T10:02:00.000Z") is True
    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "resolved" and a.resolved_at == "2026-06-03T10:02:00.000Z"
    assert repo.resolve_alert_by_id(alert_id, "2026-06-03T10:03:00.000Z") is False  # zaten resolved
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_alert_repository.py -v`
Expected: FAIL (`AttributeError: ... 'fetch_open_alerts'`).

- [ ] **Step 3: Implement** (add methods to `TelemetryRepository` in `src/storage/repository.py`, near `fetch_open_fingerprints`)

```python
    def fetch_open_alerts(self) -> dict[str, list[Alert]]:
        """Açık (active|acknowledged) uyarıları cihaz başına liste olarak döndürür (Iter 8.6).

        Reconciliation kaynağı: detector her poll bunu okur, cihaz-seviyesi tek-incident kararı
        verir (DB tek hakikat). Her liste created_at ASC; resolved hariç.

        Returns:
            device_id → o cihazın açık Alert'leri (created_at ASC).

        Raises:
            sqlalchemy.exc.OperationalError: SQLite IO/lock hatası (çağıran yakalar).
        """
        stmt = (
            select(anomalies)
            .where(anomalies.c.status.in_((ACTIVE, ACKNOWLEDGED)))
            .order_by(anomalies.c.created_at.asc())
        )
        result: dict[str, list[Alert]] = {}
        with self._engine.connect() as conn:
            for row in conn.execute(stmt).all():
                result.setdefault(row.device_id, []).append(self._row_to_alert(row))
        return result

    def update_alert(
        self,
        alert_id: int,
        *,
        severity: str,
        score: float,
        value: float,
        window_end: str,
        rule_set: str,
        description: str,
        status: str,
        acknowledged_at: str | None,
    ) -> bool:
        """Açık bir uyarıyı yerinde günceller (yaşayan uyarı, Iter 8.6).

        `created_at`/`window_start`/`resolved_at` DOKUNULMAZ (olay başlangıcı + çözüm zamanı sabit).
        Severity/score/value/window_end/rule_set/description + (re-activate için) status/acknowledged_at güncellenir.

        Args:
            alert_id: Güncellenecek satır id'si.
            severity, score, value, window_end, rule_set, description: En güncel fused alanları.
            status: Yeni durum (active veya korunan acknowledged).
            acknowledged_at: Re-activate'te None; aksi halde korunan değer.

        Returns:
            Satır güncellendiyse True; id bulunamazsa False.
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update()
                .where(anomalies.c.id == alert_id)
                .values(
                    severity=severity, score=score, value=value, window_end=window_end,
                    rule_set=rule_set, description=description, status=status,
                    acknowledged_at=acknowledged_at,
                )
            )
        return result.rowcount > 0

    def resolve_alert_by_id(self, alert_id: int, resolved_at: str) -> bool:
        """Tek bir açık uyarıyı resolved yapar (legacy çoklu-açık yakınsaması, Iter 8.6).

        Args:
            alert_id: Kapatılacak satır id'si.
            resolved_at: ISO 8601 ms zaman damgası.

        Returns:
            Kapatıldıysa True; zaten resolved / yoksa False.
        """
        with self._engine.begin() as conn:
            result = conn.execute(
                anomalies.update()
                .where(anomalies.c.id == alert_id, anomalies.c.status != RESOLVED)
                .values(status=RESOLVED, resolved_at=resolved_at)
            )
        return result.rowcount > 0
```

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_alert_repository.py -v`
Expected: PASS (4 yeni + mevcutlar).

- [ ] **Step 5: Commit**

```bash
git add src/storage/repository.py tests/unit/test_storage_alert_repository.py
git commit -m "feat(storage): fetch_open_alerts + update_alert + resolve_alert_by_id (Faz 8 Iter 8.6)"
```

---

### Task 3: Config — `SeverityBands` global blok

**Files:**
- Modify: `src/detectors/config.py`
- Modify: `config/detectors.yaml.example`, `config/detectors.demo.yaml`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces:
  - `SeverityBands(high_cutoff: float = 0.40, critical_cutoff: float = 0.75)` frozen dataclass.
  - `DetectorConfig.severity_bands: SeverityBands = SeverityBands()` (yeni alan, default → geriye-uyumlu).
  - `load_detector_config` `severity_bands` bloğunu parse eder (yoksa default).

- [ ] **Step 1: Write failing tests** (append to `tests/unit/test_config.py`)

```python
def test_load_severity_bands_from_yaml(tmp_path: Path) -> None:
    from detectors.config import load_detector_config
    p = tmp_path / "d.yaml"
    p.write_text(
        "detectors:\n  poll_interval_s: 5.0\n  window_s: 120\n  rules: []\n"
        "severity_bands:\n  high_cutoff: 0.30\n  critical_cutoff: 0.80\n",
        encoding="utf-8",
    )
    cfg = load_detector_config(p)
    assert cfg.severity_bands.high_cutoff == 0.30
    assert cfg.severity_bands.critical_cutoff == 0.80


def test_severity_bands_defaults_when_absent(tmp_path: Path) -> None:
    from detectors.config import load_detector_config
    p = tmp_path / "d.yaml"
    p.write_text("detectors:\n  poll_interval_s: 5.0\n  window_s: 120\n  rules: []\n", encoding="utf-8")
    cfg = load_detector_config(p)
    assert cfg.severity_bands.high_cutoff == 0.40
    assert cfg.severity_bands.critical_cutoff == 0.75
```

> `Path` importu test dosyasında zaten varsa tekrar ekleme; yoksa `from pathlib import Path`.

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -k severity_bands -v`
Expected: FAIL (`AttributeError: ... 'severity_bands'`).

- [ ] **Step 3a: Implement dataclass + field** (`src/detectors/config.py`)

`@dataclass(frozen=True) class RuleConfig` bloğunun ÜSTÜNE ekle:

```python
@dataclass(frozen=True)
class SeverityBands:
    """Band-pozisyon skorunu severity'ye eşleyen global eşikler (Faz 8 Iter 8.6 (4), spec § 6).

    Defaults ISO 20816 zone mantığı + sim kalibrasyonu için başlangıç; canlı smoke'ta doğrulanır.
    """

    high_cutoff: float = 0.40
    critical_cutoff: float = 0.75
```

`DetectorConfig`'e alan ekle (statistical'dan sonra, default'lu):

```python
    statistical: StatisticalConfig | None = None
    severity_bands: SeverityBands = SeverityBands()
```

- [ ] **Step 3b: Implement loader parse** (`load_detector_config`, `return DetectorConfig(...)`'tan önce)

```python
        sb = data.get("severity_bands") or {}
        severity_bands = SeverityBands(
            high_cutoff=float(sb.get("high_cutoff", 0.40)),
            critical_cutoff=float(sb.get("critical_cutoff", 0.75)),
        )
        return DetectorConfig(
            poll_interval_s=float(det["poll_interval_s"]),
            window_s=int(det["window_s"]),
            rules=rules,
            statistical=statistical,
            severity_bands=severity_bands,
        )
```

- [ ] **Step 3c: Add global block to both YAML configs**

`config/detectors.yaml.example` ve `config/detectors.demo.yaml` sonuna (top-level, `statistical` ile kardeş):

```yaml
# Severity band eşikleri (Faz 8 Iter 8.6): band skoru (0..1) → severity.
# 0..high_cutoff = warning, ..critical_cutoff = high, .. = critical. ISO 20816 zone mantığı.
severity_bands:
  high_cutoff: 0.40
  critical_cutoff: 0.75
```

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -v`
Expected: PASS (mevcut config testleri + 2 yeni; default sayesinde mevcut testler kırılmaz).

- [ ] **Step 5: Commit**

```bash
git add src/detectors/config.py config/detectors.yaml.example config/detectors.demo.yaml tests/unit/test_config.py
git commit -m "feat(detectors): severity_bands config global blok (Faz 8 Iter 8.6 (4))"
```

---

### Task 4: Service saf yardımcılar — `apply_band_severity`, `_reconcile_status`, `VALIDITY_RULES`

**Files:**
- Modify: `src/detectors/fusion.py` (`_SEVERITY_RANK` → public `SEVERITY_RANK`)
- Modify: `src/detectors/service.py` (yardımcılar; `_detect_once` HENÜZ değişmez)
- Test: `tests/unit/detectors/test_service_helpers.py` (yeni)

**Interfaces:**
- Consumes: `severity_from_band` (Task 1), `SeverityBands` (Task 3), `SEVERITY_RANK` (fusion), `Anomaly`, `Alert`, `ACTIVE/ACKNOWLEDGED`.
- Produces:
  - `VALIDITY_RULES: frozenset[str]` = `{"sensor_out_of_range", "sensor_frozen"}`.
  - `apply_band_severity(anomaly: Anomaly, severity_bands: SeverityBands) -> Anomaly` — band-rule'a türetilmiş severity'li YENİ Anomaly; validity-rule değişmeden döner.
  - `_reconcile_status(primary: Alert, new_severity: str) -> tuple[str, str | None]` — ack + band-yukarı → `(ACTIVE, None)`; aksi → `(primary.status, primary.acknowledged_at)`.

- [ ] **Step 1a: Make `SEVERITY_RANK` public** (`src/detectors/fusion.py`)

`_SEVERITY_RANK` adını `SEVERITY_RANK` yap (tanım satırı + `_rank` içindeki kullanım — 2 yer). Tek kaynak; service import edecek.

- [ ] **Step 1b: Write failing tests** (`tests/unit/detectors/test_service_helpers.py`)

```python
"""service saf yardımcıları: apply_band_severity + _reconcile_status (Faz 8 Iter 8.6, spec § 6/§ 7)."""
from __future__ import annotations

from alerts.models import Alert
from detectors.base import Anomaly
from detectors.config import SeverityBands
from detectors.service import _reconcile_status, apply_band_severity

_BANDS = SeverityBands(high_cutoff=0.40, critical_cutoff=0.75)


def _anom(rule: str, score: float, severity: str = "warning") -> Anomaly:
    return Anomaly(device_id="d", rule_name=rule, sensor="s", severity=severity, score=score,
                   window_start="a", window_end="b", value=1.0, description="x")


def _alert(status: str, severity: str, ack: str | None) -> Alert:
    return Alert(id=1, device_id="d", rule_name="r", sensor="s", severity=severity, score=0.5,
                 window_start="a", window_end="b", value=1.0, description="x",
                 created_at="c", status=status, acknowledged_at=ack, resolved_at=None)


def test_apply_band_severity_derives_for_band_rule() -> None:
    assert apply_band_severity(_anom("motor_current_high", 0.10), _BANDS).severity == "warning"
    assert apply_band_severity(_anom("motor_current_high", 0.50), _BANDS).severity == "high"
    assert apply_band_severity(_anom("motor_current_high", 0.90), _BANDS).severity == "critical"


def test_apply_band_severity_exempts_validity_rules() -> None:
    a = _anom("sensor_out_of_range", 1.0, severity="high")
    assert apply_band_severity(a, _BANDS) is a  # değişmeden döner (config severity korunur)
    f = _anom("sensor_frozen", 1.0, severity="warning")
    assert apply_band_severity(f, _BANDS).severity == "warning"


def test_reconcile_status_reactivates_acknowledged_on_band_up() -> None:
    assert _reconcile_status(_alert("acknowledged", "high", "t"), "critical") == ("active", None)


def test_reconcile_status_keeps_acknowledged_within_band() -> None:
    assert _reconcile_status(_alert("acknowledged", "high", "t"), "high") == ("acknowledged", "t")
    assert _reconcile_status(_alert("acknowledged", "critical", "t"), "high") == ("acknowledged", "t")


def test_reconcile_status_active_stays_active() -> None:
    assert _reconcile_status(_alert("active", "warning", None), "critical") == ("active", None)
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_helpers.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement** (`src/detectors/service.py` — importlar + yardımcılar; `_detect_once` üstüne)

Importlara ekle:
```python
from dataclasses import replace

from alerts.lifecycle import ACKNOWLEDGED, ACTIVE
from alerts.models import Alert
from detectors.config import SeverityBands
from detectors.fusion import SEVERITY_RANK, fuse_anomalies  # fuse_anomalies importunu birleştir
from detectors.scoring import severity_from_band
```

Yardımcılar:
```python
# Sensör-sağlığı (veri-kalitesi) kuralları: skoru ikili validity bayrağı (1.0), band konumu DEĞİL
# → severity banttan türetilmez, config severity'leri korunur (spec § 6; ayrı eksen Iter 8.7).
VALIDITY_RULES: frozenset[str] = frozenset({"sensor_out_of_range", "sensor_frozen"})


def apply_band_severity(anomaly: Anomaly, severity_bands: SeverityBands) -> Anomaly:
    """Band-skorlu bir anomaliye severity'sini band'dan türeterek atar (Iter 8.6 (4)).

    Validity-rule (`VALIDITY_RULES`) anomalileri değişmeden döner (config severity korunur).
    `Anomaly` frozen → türetme gerektiğinde `replace` ile YENİ nesne döner.

    Args:
        anomaly: Bir dedektörün ürettiği anomali.
        severity_bands: high/critical eşikleri.

    Returns:
        Severity'si türetilmiş yeni Anomaly; validity-rule ise aynı nesne.
    """
    if anomaly.rule_name in VALIDITY_RULES:
        return anomaly
    new_sev = severity_from_band(
        anomaly.score, severity_bands.high_cutoff, severity_bands.critical_cutoff
    )
    return replace(anomaly, severity=new_sev)


def _reconcile_status(primary: Alert, new_severity: str) -> tuple[str, str | None]:
    """Açık bir uyarının yeni severity karşısında durumunu/ack zamanını belirler (Iter 8.6).

    Ack'lenmiş bir uyarı severity bir ÜST banda geçerse re-activate olur (acknowledged_at temizlenir);
    aksi halde durum/ack korunur (active zaten active kalır, aynı/düşük band ack korur).

    Args:
        primary: Cihazın mevcut açık uyarısı (birincil).
        new_severity: Bu poll'da türetilen fused severity.

    Returns:
        (yeni_status, yeni_acknowledged_at).
    """
    if primary.status == ACKNOWLEDGED and SEVERITY_RANK.get(new_severity, 0) > SEVERITY_RANK.get(
        primary.severity, 0
    ):
        return (ACTIVE, None)
    return (primary.status, primary.acknowledged_at)
```

> `from detectors.fusion import fuse_anomalies` zaten vardı → tek satıra birleştir (yukarıda).

- [ ] **Step 4: Run to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_helpers.py tests/unit/detectors/test_fusion.py -v`
Expected: PASS (yeni yardımcılar + fusion regresyon — SEVERITY_RANK rename'i kırmadı).

- [ ] **Step 5: Commit**

```bash
git add src/detectors/fusion.py src/detectors/service.py tests/unit/detectors/test_service_helpers.py
git commit -m "feat(detectors): apply_band_severity + _reconcile_status saf yardımcıları (Faz 8 Iter 8.6)"
```

---

### Task 5: `_detect_once` cihaz-seviyesi rework + `run()` wire + test/call-site güncelleme (ATOMİK)

**Files:**
- Modify: `src/detectors/service.py` (`_detect_once` gövde + imza, `run()`)
- Rewrite: `tests/unit/detectors/test_service_detect_once.py`
- Modify (assertion'lar): `tests/integration/test_statistical_detector.py`, `tests/integration/test_detector_config_driven.py`, `tests/scenarios/test_statistical_overlap.py` (severity türetildiği için gerekirse)

**Interfaces:**
- Consumes: `fetch_open_alerts`, `update_alert`, `resolve_alert_by_id`, `resolve_open_alerts`, `insert_anomaly` (repo); `apply_band_severity`, `_reconcile_status`, `fuse_anomalies`, `SeverityBands`.
- Produces: `_detect_once(repository, detector_groups, now, severity_bands: SeverityBands = SeverityBands()) -> None` (yeni opsiyonel param; cihaz-seviyesi reconciliation).

- [ ] **Step 1: Rewrite test file** `tests/unit/detectors/test_service_detect_once.py`

Mevcut dosyayı tümüyle aşağıdakiyle değiştir (importlar + helper'lar korunur; assertion'lar fetch_open_alerts/fetch_alerts'e taşınır; yeni davranış testleri eklenir):

```python
"""service._detect_once cihaz-seviyesi reconciliation: in-place update + skor refresh + eskalasyon
+ severity banttan + re-activate (Faz 8 Iter 8.6, spec § 4-7)."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine, text

from detectors.base import Anomaly, Detector
from detectors.config import SeverityBands
from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.rules.motor_voltage_erratic import MotorVoltageErratic
from detectors.service import _detect_once
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository

_BIG_WINDOW_S = 1_000_000_000
_NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
_BANDS = SeverityBands(high_cutoff=0.40, critical_cutoff=0.75)


def _reading(sensor: str, ts: str, value: float, state: str = "holding", device: str = "device_001") -> IngestedReading:
    return IngestedReading(device_id=device, sensor=sensor, timestamp=ts, state=state, value=value, unit="x")


def _temp_detectors() -> list[Detector]:
    # warn=80, trip=130 → band(95)=0.30 warning, band(100)=0.40 high, band(120)=0.80 critical.
    return [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]


def _active(repo: TelemetryRepository) -> list:
    return repo.fetch_alerts(("active", "acknowledged"), limit=20)


class _FailingDetector(Detector):
    @property
    def name(self) -> str:
        return "always_fails"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        raise ValueError("kasıtlı test hatası")


def test_first_detection_inserts_one(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1 and stored[0].rule_name == "motor_temperature_high"
    assert stored[0].severity == "warning"  # band(95)=0.30 → türetilmiş


def test_refreshes_score_and_severity_in_place(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 100.0))  # band 0.40 → high
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    a1 = _active(repo)
    assert len(a1) == 1 and a1[0].severity == "high"
    first_id = a1[0].id

    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 120.0 WHERE sensor='motor_temperature'"))  # band 0.80
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)

    a2 = _active(repo)
    assert len(a2) == 1 and a2[0].id == first_id  # AYNI satır (yeni değil)
    assert a2[0].severity == "critical" and a2[0].value == 120.0  # refresh (donma yok)


def test_escalation_updates_in_place_single_row(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [
        MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0),
        MotorVoltageErratic(std_threshold_v=1.0, min_samples=10, trip_std_v=5.0),
    ]
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW, _BANDS)
    assert len(_active(repo)) == 1  # yalnız sıcaklık

    for i, v in enumerate([24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]):
        repo.insert(_reading("motor_voltage", f"2026-05-30T00:01:{i:02d}.000Z", v))
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW, _BANDS)

    open_now = _active(repo)
    assert len(open_now) == 1  # eskalasyon AYNI satırda (yeni satır yok)
    assert open_now[0].rule_name == "fused(2)"


def test_auto_resolves_on_clear(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 25.0 WHERE sensor='motor_temperature'"))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    assert _active(repo) == []
    assert len(repo.fetch_alerts(("resolved",), limit=10)) == 1


def test_resolves_preexisting_open_on_clean_device(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))  # temiz
    repo.insert_anomaly(
        Anomaly(device_id="device_001", rule_name="x", sensor="s", severity="warning", score=0.1,
                window_start="a", window_end="b", value=1.0, description="d"),
        "2026-05-30T00:00:00.000Z", "x")
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    assert _active(repo) == []


def test_restart_persisting_fault_updates_no_duplicate(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    repo.insert_anomaly(
        Anomaly(device_id="device_001", rule_name="motor_temperature_high", sensor="motor_temperature",
                severity="critical", score=0.5, window_start="a", window_end="b", value=95.0, description="d"),
        "2026-05-30T00:00:00.000Z", "motor_temperature_high")
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)  # soğuk başlangıç
    assert len(repo.fetch_recent_anomalies(limit=10)) == 1  # duplikat değil → update


def test_converges_legacy_multiple_open(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    for ts, rs in [("2026-05-30T00:00:00.000Z", "a"), ("2026-05-30T00:00:01.000Z", "b")]:  # iki açık (legacy)
        repo.insert_anomaly(
            Anomaly(device_id="device_001", rule_name=rs, sensor="s", severity="warning", score=0.1,
                    window_start="a", window_end="b", value=1.0, description="d"), ts, rs)
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    assert len(_active(repo)) == 1  # biri güncellendi, fazlalık resolve
    assert len(repo.fetch_alerts(("resolved",), limit=10)) == 1


def test_reactivates_acknowledged_on_escalation(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 100.0))  # band 0.40 high
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    alert_id = _active(repo)[0].id
    repo.acknowledge_alert(alert_id, "2026-05-30T00:00:30.000Z")

    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 125.0 WHERE sensor='motor_temperature'"))  # band 0.90 critical
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)

    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "active" and a.acknowledged_at is None and a.severity == "critical"


def test_keeps_acknowledged_within_band(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 100.0))  # high
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    repo.acknowledge_alert(_active(repo)[0].id, "2026-05-30T00:00:30.000Z")
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)  # aynı değer → band değişmez
    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "acknowledged" and a.acknowledged_at == "2026-05-30T00:00:30.000Z"


def test_below_threshold_writes_nothing(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))
    _detect_once(repo, [(_temp_detectors(), _BIG_WINDOW_S)], _NOW, _BANDS)
    assert repo.fetch_recent_anomalies(limit=10) == [] and _active(repo) == []


def test_failing_rule_does_not_block_others(migrated_engine: Engine) -> None:
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    _detect_once(repo, [([_FailingDetector(), *_temp_detectors()], _BIG_WINDOW_S)], _NOW, _BANDS)
    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1 and stored[0].rule_name == "motor_temperature_high"
```

- [ ] **Step 2: Run to verify FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -v`
Expected: FAIL (yeni davranış henüz yok — eski `_detect_once` fingerprint mantığı).

- [ ] **Step 3: Rewrite `_detect_once` + docstring** (`src/detectors/service.py`)

`_detect_once`'ı tümüyle değiştir (imza + gövde):

```python
def _detect_once(
    repository: TelemetryRepository,
    detector_groups: list[tuple[list[Detector], int]],
    now: datetime,
    severity_bands: SeverityBands = SeverityBands(),
) -> None:
    """Tek poll turu: her cihaz × dedektör-grubu → severity türet → fusion → cihaz-seviyesi reconciliation.

    Kimlik CİHAZ seviyesidir (Iter 8.6): bir cihazın açık en fazla TEK uyarısı olur ("olay"). Diff:
    cihaz temiz + açık → auto-resolve; firing + açık VAR → o satırı in-place UPDATE (skor/severity refresh
    + eskalasyon birleşik; ack→band-yukarı ise re-activate); firing + açık YOK → yeni uyarı. Severity
    fusion'dan ÖNCE band'dan türetilir (validity-rule muaf). DB tek hakikat (in-memory yok); restart =
    normal yol. Legacy çoklu-açık → en yeni güncellenir, fazlalık resolve (yakınsama).
    """
    created_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    open_alerts = repository.fetch_open_alerts()

    for device_id in repository.list_devices():
        device_anomalies: list[Anomaly] = []
        window_cache: dict[int, pd.DataFrame] = {}
        for detectors, window_s in detector_groups:
            window = window_cache.get(window_s)
            if window is None:
                window = build_window(repository, device_id, SENSORS, _since_cutoff(now, window_s))
                window_cache[window_s] = window
            if window.empty:  # pragma: no cover - list_devices yalnız telemetri'si olan cihazları döndürür
                continue
            for detector in detectors:
                try:
                    device_anomalies.extend(detector.detect(window))
                except (KeyError, ValueError) as e:
                    logger.error("Dedektör '{}' hata verdi, atlandı: {}", detector.name, e)
                    continue

        # (4) severity'yi band'dan türet (validity-rule muaf) — fusion'dan ÖNCE.
        device_anomalies = [apply_band_severity(a, severity_bands) for a in device_anomalies]
        rule_set = frozenset(a.rule_name for a in device_anomalies)
        open_list = open_alerts.get(device_id, [])

        if not rule_set:  # cihaz temiz
            if open_list:
                try:
                    closed = repository.resolve_open_alerts(device_id, created_at)
                    if closed:
                        logger.info("Auto-resolve: device={} kapatılan={}", device_id, closed)
                except OperationalError as e:
                    logger.error("Auto-resolve yazılamadı (atlandı): {}", e)
            continue

        fused = fuse_anomalies(device_anomalies)
        if fused is None:  # pragma: no cover - rule_set boş değilse fused None olamaz
            continue
        rule_set_str = ",".join(sorted(rule_set))

        if not open_list:  # firing + açık yok → ilk tespit
            try:
                repository.insert_anomaly(fused, created_at, rule_set_str)
            except OperationalError as e:
                logger.error("Anomali yazılamadı (atlandı): {}", e)
                continue
            logger.info("Alert (yeni): device={} rules={} sev={}", device_id, sorted(rule_set), fused.severity)
            continue

        # firing + açık VAR → in-place UPDATE (skor refresh + eskalasyon + re-activate)
        primary = max(open_list, key=lambda a: a.created_at)
        try:
            for extra in open_list:  # legacy çoklu-açık → fazlalıkları kapat (yakınsama)
                if extra.id != primary.id:
                    repository.resolve_alert_by_id(extra.id, created_at)
            new_status, new_ack = _reconcile_status(primary, fused.severity)
            repository.update_alert(
                primary.id, severity=fused.severity, score=fused.score, value=fused.value,
                window_end=fused.window_end, rule_set=rule_set_str, description=fused.description,
                status=new_status, acknowledged_at=new_ack,
            )
        except OperationalError as e:
            logger.error("Uyarı güncellenemedi (atlandı): {}", e)
            continue
        if new_status == ACTIVE and primary.status == ACKNOWLEDGED:
            logger.info("Re-activate: device={} sev={} (eskalasyon)", device_id, fused.severity)
```

- [ ] **Step 4: Wire `run()`** (`src/detectors/service.py`)

Poll çağrısını güncelle:
```python
                _detect_once(repository, detector_groups, datetime.now(UTC), detector_config.severity_bands)
```

- [ ] **Step 5: Run service unit tests to verify PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -v`
Expected: PASS (tüm yeni davranış testleri).

- [ ] **Step 6: Fix integration/scenario severity assertions (full suite)**

Run: `.venv/bin/python -m pytest tests/integration tests/scenarios -v`
Beklenen kırılma noktaları + düzeltme: severity artık türetildiği için `test_detector_config_driven.py` / `test_statistical_detector.py` / `test_statistical_overlap.py` içinde **statik severity beklentisi** (örn. `severity == "warning"`) varsa, türetilen değere göre düzelt (band skorunu ölç: gerçek değeri assertion'a yaz; varlık/sayı assertion'larına dokunma). `_detect_once` çağrıları `severity_bands` vermez → default (0.40/0.75) kullanılır, imza değişmez.

- [ ] **Step 7: Full suite + lint**

Run:
```
.venv/bin/python -m pytest
.venv/bin/python -m mypy src/detectors src/storage tests/unit tests/integration tests/scenarios
ruff check src/detectors src/storage tests/unit tests/integration tests/scenarios
```
Expected: tümü temiz (fetch_open_fingerprints HÂLÂ var → 8.5 repo testleri + onu kullanan kalan testler yeşil; Task 6'da silinecek).

- [ ] **Step 8: Commit**

```bash
git add src/detectors/service.py tests/unit/detectors/test_service_detect_once.py tests/integration tests/scenarios
git commit -m "feat(detectors): _detect_once cihaz-seviyesi in-place reconciliation + severity banttan + re-activate (Faz 8 Iter 8.6 (1)(2)(4))"
```

---

### Task 6: `fetch_open_fingerprints` ölü kodunu kaldır

**Files:**
- Modify: `src/storage/repository.py` (metodu sil)
- Modify: `tests/unit/test_storage_alert_repository.py` (2 fingerprint testini sil)

**Interfaces:** Yok (kaldırma). Üretim artık `fetch_open_alerts` kullanır (Task 5).

- [ ] **Step 1: Grep ile son kullanım kontrolü**

Run: `grep -rn "fetch_open_fingerprints" src tests | grep -v __pycache__`
Expected: yalnız `src/storage/repository.py` tanımı + `tests/unit/test_storage_alert_repository.py` 2 test. (service.py + service testleri Task 5'te temizlendi.)

- [ ] **Step 2: Sil**

- `src/storage/repository.py`: `fetch_open_fingerprints` metodunu tümüyle kaldır.
- `tests/unit/test_storage_alert_repository.py`: `test_fetch_open_fingerprints_groups_by_device` ve `test_fetch_open_fingerprints_includes_acknowledged_and_null_safe` testlerini sil (NULL-rule_set güvenliği `fetch_open_alerts` üzerinden hâlâ önemliyse Task 2 testine taşımayı düşün; ancak karar artık fingerprint kullanmadığı için NULL rule_set update yolunu etkilemez → silmek yeterli).

- [ ] **Step 3: Full suite + lint**

Run:
```
.venv/bin/python -m pytest
.venv/bin/python -m mypy src/detectors src/storage tests/unit tests/integration tests/scenarios
ruff check src/detectors src/storage tests/unit tests/integration tests/scenarios
```
Expected: tümü yeşil; `fetch_open_fingerprints` referansı kalmadı.

- [ ] **Step 4: Commit**

```bash
git add src/storage/repository.py tests/unit/test_storage_alert_repository.py
git commit -m "refactor(storage): fetch_open_fingerprints ölü kodu kaldırıldı (Faz 8 Iter 8.6, fetch_open_alerts ikamesi)"
```

---

### Task 7: Closure — canlı 6-cihaz demo smoke + severity kalibrasyon + docs/memory

> **Controller-run (TDD task değil):** Bu task subagent değil, controller (sen) tarafından yürütülür.

- [ ] **Step 1: Tam suite + mypy + ruff (final)** — hepsi yeşil, 384 → ~+15 test artışı beklenir.

- [ ] **Step 2: Canlı demo smoke** (`./scripts/demo_up.sh`, gerçek Mosquitto + 6 cihaz)

Doğrula (spec § 10):
- device_001 temiz → **0 FP**.
- device_005 (sıcaklık aşımı) → tek uyarı; skor zamanla **tırmanır** (donma yok); severity warning→high→critical geçişi gözlenir.
- device_002 (mekanik aşınma) → eskalasyon **tek satırda** (yığın yok), rule_set genişler.
- Bir uyarıyı dashboard'dan **ack'le**, arızanın kritikleşmesini bekle → **re-activate** (status active'e döner).
- Arıza bitince → resolve. Detector restart → orphan/duplikat yok.
- **Severity eşiklerini kalibre et:** demo'da geçişler erken/geç ise `high_cutoff`/`critical_cutoff`'u gerçek band skorlarına göre ayarla (detectors.demo.yaml + example), tekrar smoke. (8.4 dersi: ölçerek kalibre.)

- [ ] **Step 3: Docs güncelle** — `CLAUDE.md` "Mevcut Faz" + Faz 8 bölümüne Iter 8.6 closure özeti; `docs/ROADMAP.md` gerekirse.

- [ ] **Step 4: Memory güncelle** — `project_active_phase.md`: Iter 8.6 ✅ DONE runtime contract + HANDOFF'u Iter 8.7'ye (3 hysteresis + 5 sensör-sağlığı ayrı eksen) güncelle.

- [ ] **Step 5: Final whole-iteration review** (salt-okunur reviewer subagent) → fix loop.

- [ ] **Step 6:** Kullanıcı onayıyla PR/merge (push proaktif YAPMA).

---

## Self-Review (yazar kontrolü)

**1. Spec coverage:**
- §3 cihaz-seviyesi kimlik → Task 5. §4 reconciliation algoritması → Task 5. §5 skor refresh → Task 5 (`test_refreshes_score_and_severity_in_place`). §6 severity banttan + validity muaf + config eşik → Task 1+3+4 (`apply_band_severity`, `severity_from_band`, `SeverityBands`). §7 re-activate → Task 4 (`_reconcile_status`) + Task 5 (`test_reactivates...`). §8 repository (fetch_open_alerts/update_alert/resolve_alert_by_id, fetch_open_fingerprints kaldırma) → Task 2 + Task 6. §9 dashboard yapısal değişiklik yok → task yok (doğru). §10 test+smoke → her task TDD + Task 7. §11 değişmez kontratlar → Global Constraints + hiçbir task Anomaly/fuse_anomalies/migration'a dokunmaz. ✓ Boşluk yok.

**2. Placeholder scan:** Tüm kod blokları tam; "TBD/TODO/handle edge cases" yok. ✓

**3. Type consistency:** `severity_from_band(score, high_cutoff, critical_cutoff)` (Task 1) ↔ `apply_band_severity` çağrısı (Task 4) ↔ `SeverityBands.high_cutoff/critical_cutoff` (Task 3) tutarlı. `update_alert(... keyword-only ...)` imzası (Task 2) ↔ `_detect_once` çağrısı (Task 5) tutarlı. `SEVERITY_RANK` (Task 4 rename) ↔ `_reconcile_status` kullanımı tutarlı. `fetch_open_alerts -> dict[str, list[Alert]]` (Task 2) ↔ `_detect_once` `open_list = open_alerts.get(...)` (Task 5) tutarlı. ✓

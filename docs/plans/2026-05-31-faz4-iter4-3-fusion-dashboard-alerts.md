# Faz 4 — Iterasyon 4.3: Minimal Fusion + Dashboard Alerts Paneli + FP Doğrulama Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aynı cihazda aynı poll turunda tetiklenen çoklu kuralı tek temsilci `anomalies` satırına birleştirmek (write-side fusion) + persisting fault'u her poll'da yeniden yazmamak (epizot-bazlı debounce), ve dashboard'a `fetch_recent_anomalies` okuyan "Aktif Uyarılar" panelini eklemek.

**Architecture:** Saf `fuse_anomalies(list[Anomaly]) -> Anomaly | None` füzyon fonksiyonu (`src/detectors/fusion.py`): boş→None, tek→kendisi, çoklu→en yüksek (severity, score) baz alan "fused(N)" temsilci (skor=max, severity=en yüksek, açıklamada katkıda bulunan kurallar). `_detect_once` yeniden yazılır: cihaz başına tüm dedektörlerin anomalilerini toplar → fusion → **epizot debounce** (`active: dict[device→frozenset[rule]]`: aynı kural-seti süregelirse yazma; set değişirse/yeni epizotta yaz; fault temizlenince re-arm). Dashboard `app.py`'ye `fetch_recent_anomalies` okuyan fragment panel + saf `anomalies_to_frame` transform. Gözlem modu korunur (yalnız `telemetry` oku, yalnız `anomalies` yaz). Yeni tablo/migration YOK — `anomalies` tablosu yeniden kullanılır (spec § 7 "yazımdan önce birleştirir").

**Tech Stack:** Python 3.11, pandas, SQLAlchemy, Streamlit 1.36 (`st.experimental_fragment`), loguru, pytest. Yeni bağımlılık YOK.

---

## Tasarım Kararı (kullanıcı onayı 2026-05-31)

**Fusion modeli = anomalies tablosunu yeniden kullan (Option A).** Detector yazımdan önce birleştirir: cihaz başına TEK temsilci satır (`rule_name="fused(N)"` çoklu kuralda; tek kuralda kendi adı), en yüksek severity/score baz alınır, açıklama katkıda bulunan kuralları listeler. Dashboard mevcut `fetch_recent_anomalies`'i okur. Yeni `alerts` tablosu YOK (o Faz 5 alerts servisi; kapsam dışı). Spec § 5/§ 7 ile birebir.

**Gürültü azaltma iki katman:**
1. **Cross-rule fusion:** aynı cihaz+pencere çoklu kural → tek satır.
2. **Epizot debounce:** persisting fault (aynı kural-seti) her 5s poll'da değil, epizot başına bir kez yazılır. Kural-seti değişirse (eskalasyon) yeni satır; fault temizlenince re-arm (tekrar oluşursa yeni satır).

Bu, Iter 4.2 canlı smoke'unda gözlenen "tek kaçak 24× yazıldı" gürültüsünü çözer (epizot başına ~1 satır).

---

## Spec Hizalama Notları

- **`Anomaly` şeması değişmez.** Fused satır mevcut 9-alanlı `Anomaly`'e sığar: `rule_name="fused(N)"`, `sensor`/`value`/`severity` top katkıdan, `score=max`, `window_start=min`, `window_end=max`, `description` katkı listesi. `insert_anomaly` aynen kullanılır.
- **`_detect_once` imzası değişir:** `seen: set[tuple[str,str,str]]` → `active: dict[str, frozenset[str]]` (epizot durumu). Bu Iter 4.1/4.2 davranışının evrimi; `test_service_detect_once.py` + `test_detector_config_driven.py` güncellenir.
- **Dashboard `app.py` ince presentation (unit-test YOK).** Panel wiring manuel/boot smoke ile; saf `anomalies_to_frame` birim test edilir (Faz 3 deseni).
- **FP doğrulama (kabul kriteri 4):** kod task'ı değil — controller closure'da canlı clean-smoke (normal cihaz N dk → saatte birkaç adetten az). Iter 4.2 clean imza testi + hydraulic FP fix zaten per-window FP'yi kanıtlıyor; bu iterasyon epizot-debounce ile gürültüyü de azaltır.

**Test/lint komutu (her task sonunda; `.venv/bin/python`):**
```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/dashboard tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion src/storage src/detectors src/dashboard tests/unit tests/integration tests/scenarios
```

---

## Dosya Yapısı

**Oluşturulacak:**
- `src/detectors/fusion.py` — `fuse_anomalies` saf füzyon fonksiyonu
- `tests/unit/detectors/test_fusion.py` — fusion birim testleri
- `tests/unit/test_dashboard_alerts_transform.py` — `anomalies_to_frame` birim testleri

**Değiştirilecek:**
- `src/detectors/service.py` — `_detect_once` (fusion + epizot debounce), `run()` (`active` dict)
- `tests/unit/detectors/test_service_detect_once.py` — `seen`→`active`, +fusion/debounce testleri
- `tests/integration/test_detector_config_driven.py` — fused satır assertion'ı + `active`
- `src/dashboard/transform.py` — `anomalies_to_frame`
- `src/dashboard/app.py` — "Aktif Uyarılar" fragment paneli

---

## Task 1: fuse_anomalies saf füzyon fonksiyonu

**Files:**
- Create: `src/detectors/fusion.py`
- Test: `tests/unit/detectors/test_fusion.py`

- [ ] **Step 1: Failing test** — `tests/unit/detectors/test_fusion.py`

```python
"""detectors.fusion: çoklu anomaliyi tek temsilci Anomaly'e birleştirme (Faz 4 Iter 4.3, spec § 5/§ 7)."""
from __future__ import annotations

from detectors.base import Anomaly
from detectors.fusion import fuse_anomalies


def _anom(
    *,
    rule_name: str,
    severity: str = "warning",
    score: float = 0.5,
    sensor: str = "motor_current",
    value: float = 1.0,
    window_start: str = "2026-05-30T00:00:00.000Z",
    window_end: str = "2026-05-30T00:01:00.000Z",
    device_id: str = "device_001",
) -> Anomaly:
    return Anomaly(
        device_id=device_id,
        rule_name=rule_name,
        sensor=sensor,
        severity=severity,
        score=score,
        window_start=window_start,
        window_end=window_end,
        value=value,
        description=f"{rule_name} desc",
    )


def test_empty_returns_none() -> None:
    assert fuse_anomalies([]) is None


def test_single_returns_same_anomaly_unchanged() -> None:
    """Tek anomali füzyona girmez — kendi rule_name'iyle aynen döner."""
    a = _anom(rule_name="motor_current_high", severity="high", score=0.4)
    fused = fuse_anomalies([a])
    assert fused is a


def test_multiple_fuses_into_representative() -> None:
    """Çoklu → 'fused(N)'; en yüksek severity baz; skor=max; pencere min/max; açıklama katkılar."""
    a1 = _anom(
        rule_name="motor_current_high", severity="high", score=0.4,
        sensor="motor_current", value=10.0,
        window_start="2026-05-30T00:00:05.000Z", window_end="2026-05-30T00:00:50.000Z",
    )
    a2 = _anom(
        rule_name="vibration_elevated", severity="warning", score=0.9,
        sensor="vibration", value=0.45,
        window_start="2026-05-30T00:00:00.000Z", window_end="2026-05-30T00:01:00.000Z",
    )
    fused = fuse_anomalies([a1, a2])
    assert fused is not None
    assert fused.rule_name == "fused(2)"
    assert fused.device_id == "device_001"
    assert fused.severity == "high"          # en yüksek severity (a1)
    assert fused.sensor == "motor_current"   # top katkının sensörü (a1, severity yüksek)
    assert fused.value == 10.0               # top katkının değeri
    assert fused.score == 0.9                # max skor (a2)
    assert fused.window_start == "2026-05-30T00:00:00.000Z"  # min
    assert fused.window_end == "2026-05-30T00:01:00.000Z"    # max
    assert "motor_current_high" in fused.description
    assert "vibration_elevated" in fused.description


def test_top_chosen_by_severity_then_score() -> None:
    """severity eşitse skor belirler; severity farklıysa severity baskın (skor düşük olsa da)."""
    crit_low = _anom(rule_name="motor_temperature_high", severity="critical", score=0.1, sensor="motor_temperature", value=95.0)
    warn_high = _anom(rule_name="motor_voltage_erratic", severity="warning", score=1.0, sensor="motor_voltage", value=18.0)
    fused = fuse_anomalies([warn_high, crit_low])
    assert fused is not None
    assert fused.severity == "critical"          # severity baskın
    assert fused.sensor == "motor_temperature"   # critical olan top
    assert fused.value == 95.0
    assert fused.score == 1.0                     # ama skor yine max (warn_high)
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_fusion.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'detectors.fusion'`

- [ ] **Step 3: Implement** — `src/detectors/fusion.py`

```python
"""Anomali füzyonu: aynı cihaz+pencerede çoklu kuralı tek temsilci Anomaly'e birleştirir.

Spec § 5/§ 7 (minimal fusion, write-side). Detector poll turunda bir cihazın tüm
anomalilerini toplar ve `fuse_anomalies` ile tek satıra indirir (gürültü azaltma).
Gelişmiş (ağırlıklı/çok-katmanlı) fusion Faz 6.
"""
from __future__ import annotations

from detectors.base import Anomaly

# Severity sıralaması (yüksekten düşüğe karşılaştırma için).
_SEVERITY_RANK: dict[str, int] = {"critical": 3, "high": 2, "warning": 1, "info": 0}


def _rank(anomaly: Anomaly) -> tuple[int, float]:
    """Önem anahtarı: önce severity, sonra score (max ile 'top' seçimi için)."""
    return (_SEVERITY_RANK.get(anomaly.severity, 0), anomaly.score)


def fuse_anomalies(anomalies: list[Anomaly]) -> Anomaly | None:
    """Tek cihazın bir poll turundaki anomalilerini tek temsilci Anomaly'e birleştirir.

    Args:
        anomalies: Aynı cihaza ait, bir poll turunda tetiklenen anomaliler.

    Returns:
        Boş liste → None. Tek anomali → kendisi (değişmez). Çoklu → "fused(N)" temsilci:
        en yüksek (severity, score) anomali baz alınır (device_id, sensor, value, severity
        ondan); score = max; window_start = min, window_end = max; description katkıda
        bulunan kuralları (önemden düşüğe) listeler.
    """
    if not anomalies:
        return None
    top = max(anomalies, key=_rank)
    if len(anomalies) == 1:
        return top
    contributors = sorted(anomalies, key=_rank, reverse=True)
    description = " + ".join(f"{a.rule_name}({a.value:.2f})" for a in contributors)
    return Anomaly(
        device_id=top.device_id,
        rule_name=f"fused({len(anomalies)})",
        sensor=top.sensor,
        severity=top.severity,
        score=max(a.score for a in anomalies),
        window_start=min(a.window_start for a in anomalies),
        window_end=max(a.window_end for a in anomalies),
        value=top.value,
        description=description,
    )
```

- [ ] **Step 4: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_fusion.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint**

Run: `.venv/bin/python -m mypy src/detectors tests/unit/detectors && ruff check src/detectors tests/unit/detectors`
Expected: temiz

- [ ] **Step 6: Commit**

```bash
git add src/detectors/fusion.py tests/unit/detectors/test_fusion.py
git commit -m "feat(detectors): fuse_anomalies saf füzyon fonksiyonu (Faz 4 Iter 4.3)"
```

---

## Task 2: _detect_once fusion + epizot debounce + run() + test güncellemeleri

**Files:**
- Modify: `src/detectors/service.py`
- Modify: `tests/unit/detectors/test_service_detect_once.py`
- Modify: `tests/integration/test_detector_config_driven.py`

- [ ] **Step 1: `test_service_detect_once.py`'yi yeni davranışa güncelle** (TÜM dosyayı bununla değiştir)

`seen: set` → `active: dict[str, frozenset[str]]`; +fusion (çoklu kural → fused(2)) ve debounce-rearm testleri.

```python
"""service._detect_once fusion + epizot debounce + per-rule error-swallow (Faz 4 Iter 4.3, spec § 5/§ 7/§ 8)."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine, text

from detectors.base import Anomaly, Detector
from detectors.rules.motor_temperature_high import MotorTemperatureHigh
from detectors.rules.motor_voltage_erratic import MotorVoltageErratic
from detectors.service import _detect_once
from ingestion.message_parser import IngestedReading
from storage.repository import TelemetryRepository

# Cutoff'u geçmişte bırakıp seed edilen 2026 timestamp'lerinin tümünü pencereye almak için.
_BIG_WINDOW_S = 1_000_000_000
_NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)


def _reading(
    sensor: str, ts: str, value: float, state: str = "holding", device: str = "device_001"
) -> IngestedReading:
    return IngestedReading(
        device_id=device, sensor=sensor, timestamp=ts, state=state, value=value, unit="x"
    )


class _FailingDetector(Detector):
    """detect() her zaman ValueError fırlatır — error-swallow davranışını test eder."""

    @property
    def name(self) -> str:
        return "always_fails"

    def detect(self, window: pd.DataFrame) -> list[Anomaly]:
        raise ValueError("kasıtlı test hatası")


def test_detect_once_persists_single_anomaly(migrated_engine: Engine) -> None:
    """Tek kural tetiklenince fused değil kendi rule_name'iyle yazılır; active güncellenir."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    active: dict[str, frozenset[str]] = {}

    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)

    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1
    assert stored[0].rule_name == "motor_temperature_high"
    assert stored[0].value == 95.0
    assert active == {"device_001": frozenset({"motor_temperature_high"})}


def test_detect_once_fuses_multiple_rules(migrated_engine: Engine) -> None:
    """Aynı cihazda iki kural tetiklenince TEK fused(2) satır yazılır."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    for i, v in enumerate([24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]):
        repo.insert(_reading("motor_voltage", f"2026-05-30T00:01:{i:02d}.000Z", v))
    detectors: list[Detector] = [
        MotorTemperatureHigh(critical_threshold_c=80.0),
        MotorVoltageErratic(std_threshold_v=1.0, min_samples=10),
    ]
    active: dict[str, frozenset[str]] = {}

    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)

    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1
    assert stored[0].rule_name == "fused(2)"
    assert stored[0].severity == "critical"  # temp en yüksek severity
    assert "motor_temperature_high" in stored[0].description
    assert "motor_voltage_erratic" in stored[0].description
    assert active == {
        "device_001": frozenset({"motor_temperature_high", "motor_voltage_erratic"})
    }


def test_detect_once_debounces_persisting_fault(migrated_engine: Engine) -> None:
    """Aynı kural-seti iki ardışık turda süregelirse yalnız bir kez yazılır (epizot debounce)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    active: dict[str, frozenset[str]] = {}

    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)
    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)

    assert len(repo.fetch_recent_anomalies(limit=10)) == 1


def test_detect_once_rearms_after_fault_clears(migrated_engine: Engine) -> None:
    """Fault temizlenince active'ten düşer; tekrar oluşursa YENİ satır yazılır (re-arm)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    active: dict[str, frozenset[str]] = {}

    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)  # tur 1: yazar
    # Fault temizlenir (değer eşik altına): cihaz hâlâ telemetri'ye sahip ama kural tetiklemez.
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 25.0 WHERE sensor = 'motor_temperature'"))
    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)  # tur 2: tetik yok → re-arm
    assert active == {}
    # Fault geri döner:
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 95.0 WHERE sensor = 'motor_temperature'"))
    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)  # tur 3: yeniden yazar

    assert len(repo.fetch_recent_anomalies(limit=10)) == 2  # tur 1 + tur 3


def test_detect_once_below_threshold_writes_nothing(migrated_engine: Engine) -> None:
    """Eşik altı → hiçbir anomali yazılmaz, active boş kalır."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0)]
    active: dict[str, frozenset[str]] = {}

    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)

    assert repo.fetch_recent_anomalies(limit=10) == []
    assert active == {}


def test_detect_once_failing_rule_does_not_block_others(migrated_engine: Engine) -> None:
    """Bir kural ValueError fırlatsa bile diğer kurallar çalışır + servis çökmez (spec § 8)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [
        _FailingDetector(),
        MotorTemperatureHigh(critical_threshold_c=80.0),
    ]
    active: dict[str, frozenset[str]] = {}

    _detect_once(repo, detectors, _BIG_WINDOW_S, active, _NOW)  # exception fırlamamalı

    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1
    assert stored[0].rule_name == "motor_temperature_high"
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -q`
Expected: FAIL — eski `_detect_once` 4. argümanı `seen: set` bekler ama test `active: dict` geçer; eski gövde `seen.add(key)` çağırınca **`AttributeError: 'dict' object has no attribute 'add'`** fırlar (gerçek kırmızı, sessiz mis-pass değil). Yeni gövde (Step 3) yazılınca yeşile döner.

- [ ] **Step 3: `_detect_once`'u fusion + epizot debounce ile yeniden yaz** — `src/detectors/service.py`

Önce import ekle (mevcut `from detectors.config import ...` satırının altına):
```python
from detectors.fusion import fuse_anomalies
```

`_detect_once` fonksiyonunu TÜMÜYLE değiştir (mevcut 83-124 satırları):
```python
def _detect_once(
    repository: TelemetryRepository,
    detectors: list[Detector],
    window_s: int,
    active: dict[str, frozenset[str]],
    now: datetime,
) -> None:
    """Tek poll turu: her cihaz × tüm dedektörler → fusion → epizot debounce → insert_anomaly.

    Cihaz başına tüm anomaliler toplanır, `fuse_anomalies` ile tek temsilci satıra indirilir
    (spec § 5/§ 7 write-side fusion). `active`: device_id → son yazılan katkıda-bulunan kural-seti
    (epizot debounce): aynı kural-seti süregelirse tekrar yazılmaz; set değişirse (eskalasyon) yeni
    satır; fault temizlenince active'ten düşer (re-arm). `now` dışarıdan enjekte edilir (deterministik test).
    """
    since = _since_cutoff(now, window_s)
    created_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    for device_id in repository.list_devices():
        window = build_window(repository, device_id, SENSORS, since)
        if window.empty:  # pragma: no cover - list_devices yalnız telemetri'si olan cihazları döndürür (savunmacı)
            continue
        device_anomalies: list[Anomaly] = []
        for detector in detectors:
            try:
                device_anomalies.extend(detector.detect(window))
            except (KeyError, ValueError) as e:
                logger.error("Kural '{}' hata verdi, atlandı: {}", detector.name, e)
                continue

        rule_set = frozenset(a.rule_name for a in device_anomalies)
        if not rule_set:
            active.pop(device_id, None)  # fault temizlendi → re-arm
            continue
        # NOT: list_devices() append-only telemetry'den DISTINCT okur → cihaz asla "düşmez";
        # her poll ziyaret edilir, bu yüzden ayrı stale-active temizliği gerekmez.
        if active.get(device_id) == rule_set:
            continue  # aynı kural-seti süregeliyor → debounce (yeniden yazma)

        fused = fuse_anomalies(device_anomalies)
        if fused is None:  # pragma: no cover - rule_set boş değilse fused None olamaz
            continue
        try:
            repository.insert_anomaly(fused, created_at)
        except OperationalError as e:
            logger.error("Anomali yazılamadı (atlandı): {}", e)
            continue
        active[device_id] = rule_set
        logger.info(
            "Alert: device={} rules={} value={:.2f} sev={}",
            fused.device_id,
            sorted(rule_set),
            fused.value,
            fused.severity,
        )
```

- [ ] **Step 4: `run()`'da `seen` → `active`** — `src/detectors/service.py`

`run()` içinde `seen: set[tuple[str, str, str]] = set()` satırını değiştir:
```python
        active: dict[str, frozenset[str]] = {}
```
Ve loop'taki `_detect_once(...)` çağrısında `seen` yerine `active` geç:
```python
                _detect_once(
                    repository, detectors, detector_config.window_s, active, datetime.now(UTC)
                )
```

- [ ] **Step 5: Run unit, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/detectors/test_service_detect_once.py -q`
Expected: PASS (6 passed)

- [ ] **Step 6: Iter 4.2 integration testini fused davranışa güncelle** — `tests/integration/test_detector_config_driven.py`

`test_config_driven_detectors_persist_anomalies`'i değiştir: `seen: set` → `active: dict`, ve assertion'ı fused satıra çevir (temp+voltage aynı cihaz aynı tur → tek fused(2) satır).

`from detectors.service import _detect_once, run` importu aynı kalır. Fonksiyon gövdesini değiştir:
```python
def test_config_driven_detectors_persist_anomalies(tmp_path: Path) -> None:
    cfg_path = tmp_path / "detectors.yaml"
    cfg_path.write_text(_CONFIG, encoding="utf-8")
    db_path = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db_path)
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        # Eşik-üstü sıcaklık (temp_high) + erratik voltaj (voltage_erratic) — aynı cihaz, aynı tur.
        repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
        for i, v in enumerate([24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]):
            repo.insert(_reading("motor_voltage", f"2026-05-30T00:01:{i:02d}.000Z", v))

        config = load_detector_config(cfg_path)
        detectors = build_detectors(config)
        active: dict[str, frozenset[str]] = {}
        _detect_once(repo, detectors, config.window_s, active, datetime(2026, 5, 30, 1, 0, 0, tzinfo=UTC))

        stored = repo.fetch_recent_anomalies(limit=10)
        # İki kural aynı cihazda → TEK fused satır (write-side fusion, Iter 4.3).
        assert len(stored) == 1
        assert stored[0].rule_name == "fused(2)"
        assert "motor_temperature_high" in stored[0].description
        assert "motor_voltage_erratic" in stored[0].description
    finally:
        engine.dispose()
```

- [ ] **Step 7: Full suite + lint**

Run:
```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/detectors tests/unit tests/integration
ruff check src/detectors tests/unit tests/integration
```
Expected: tüm testler PASS (1 smoke skipped); `test_service_build_window.py` + `test_detector_persistence.py` (Iter 4.1) hâlâ geçer (build_window/rule.detect/insert_anomaly değişmedi; integration tek-kural seed → tek satır, fused değil). mypy + ruff temiz.

> NOT: `tests/integration/test_detector_persistence.py` (Iter 4.1) `build_window` + `rule.detect` + `insert_anomaly`'yi DOĞRUDAN çağırır (`_detect_once` kullanmaz) → fusion değişiminden ETKİLENMEZ, aynen geçer.

- [ ] **Step 8: Commit**

```bash
git add src/detectors/service.py tests/unit/detectors/test_service_detect_once.py tests/integration/test_detector_config_driven.py
git commit -m "feat(detectors): write-side fusion + epizot debounce _detect_once (Faz 4 Iter 4.3)"
```

---

## Task 3: anomalies_to_frame dashboard transform

**Files:**
- Modify: `src/dashboard/transform.py`
- Test: `tests/unit/test_dashboard_alerts_transform.py`

- [ ] **Step 1: Failing test** — `tests/unit/test_dashboard_alerts_transform.py`

```python
"""dashboard.transform.anomalies_to_frame birim testi (Faz 4 Iter 4.3)."""
from __future__ import annotations

from detectors.base import Anomaly
from dashboard.transform import anomalies_to_frame


def _anom(rule_name: str = "motor_current_high", device: str = "device_001") -> Anomaly:
    return Anomaly(
        device_id=device,
        rule_name=rule_name,
        sensor="motor_current",
        severity="high",
        score=0.87,
        window_start="2026-05-30T00:00:00.000Z",
        window_end="2026-05-30T00:01:00.000Z",
        value=10.5,
        description=f"{rule_name} açıklaması",
    )


def test_empty_returns_correct_schema() -> None:
    """Boş liste → 0 satırlı ama doğru kolonlu DataFrame."""
    frame = anomalies_to_frame([])
    assert list(frame.columns) == ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "açıklama"]
    assert len(frame) == 0


def test_maps_fields_to_columns() -> None:
    """Her Anomaly alanı doğru kolona eşlenir; skor 2 ondalığa yuvarlanır."""
    frame = anomalies_to_frame([_anom()])
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["zaman"] == "2026-05-30T00:01:00.000Z"  # window_end
    assert row["cihaz"] == "device_001"
    assert row["severity"] == "high"
    assert row["sensör"] == "motor_current"
    assert row["kural"] == "motor_current_high"
    assert row["skor"] == 0.87
    assert row["açıklama"] == "motor_current_high açıklaması"


def test_preserves_order() -> None:
    """Girdi sırası (repository created_at DESC) korunur."""
    frame = anomalies_to_frame([_anom(rule_name="a"), _anom(rule_name="b")])
    assert list(frame["kural"]) == ["a", "b"]
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_alerts_transform.py -q`
Expected: FAIL — `ImportError: cannot import name 'anomalies_to_frame'`

- [ ] **Step 3: Implement** — `src/dashboard/transform.py`'ye ekle

Import bölümüne ekle (mevcut `from ingestion.message_parser import IngestedReading` satırının yanına, alfabetik: `detectors` önce gelir):
```python
from detectors.base import Anomaly
```

Dosyanın sonuna ekle:
```python
_ALERT_COLUMNS = ["zaman", "cihaz", "severity", "sensör", "kural", "skor", "açıklama"]


def anomalies_to_frame(anomalies: list[Anomaly]) -> pd.DataFrame:
    """Anomaly listesini "Aktif Uyarılar" tablosu için DataFrame'e çevirir (spec § 3 Iter 4.3).

    Args:
        anomalies: fetch_recent_anomalies çıktısı (created_at DESC sıralı; boş olabilir).

    Returns:
        [zaman, cihaz, severity, sensör, kural, skor, açıklama] kolonlu DataFrame; girdi
        sırasını korur. `zaman` = window_end (tespit anı), `skor` 2 ondalığa yuvarlanır.
        Boş girdi → 0 satırlı ama doğru-şemalı DataFrame.
    """
    return pd.DataFrame(
        {
            "zaman": [a.window_end for a in anomalies],
            "cihaz": [a.device_id for a in anomalies],
            "severity": [a.severity for a in anomalies],
            "sensör": [a.sensor for a in anomalies],
            "kural": [a.rule_name for a in anomalies],
            "skor": [round(a.score, 2) for a in anomalies],
            "açıklama": [a.description for a in anomalies],
        },
        columns=_ALERT_COLUMNS,
    )
```

- [ ] **Step 4: Run, confirm PASS**

Run: `.venv/bin/python -m pytest tests/unit/test_dashboard_alerts_transform.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint**

Run: `.venv/bin/python -m mypy src/dashboard tests/unit/test_dashboard_alerts_transform.py && ruff check src/dashboard tests/unit/test_dashboard_alerts_transform.py`
Expected: temiz

- [ ] **Step 6: Commit**

```bash
git add src/dashboard/transform.py tests/unit/test_dashboard_alerts_transform.py
git commit -m "feat(dashboard): anomalies_to_frame transform (Faz 4 Iter 4.3)"
```

---

## Task 4: Dashboard "Aktif Uyarılar" paneli

**Files:**
- Modify: `src/dashboard/app.py`

- [ ] **Step 1: Import güncelle** — `src/dashboard/app.py`

`from dashboard.transform import (...)` bloğuna `anomalies_to_frame` ekle:
```python
from dashboard.transform import (  # noqa: E402
    WINDOW_OPTIONS,
    anomalies_to_frame,
    readings_to_frame,
    window_to_since,
)
```

- [ ] **Step 2: `_render_alerts` fragment'ını ekle** — `src/dashboard/app.py`

`_render_charts` fonksiyonunun ÜSTÜNE (veya altına) ekle:
```python
@st.experimental_fragment(run_every="5s")
def _render_alerts(repository: TelemetryRepository) -> None:
    """Filo geneli son anomalileri (fused alert'ler) tablo olarak gösterir; 5s'de bir yenilenir.

    Gözlem modu: yalnız fetch_recent_anomalies okur. anomalies tablosu yoksa (detector hiç
    çalışmadı) bilgilendirir; çökmez (spec § 7 hata yönetimi deseni).
    """
    st.subheader("🚨 Aktif Uyarılar")
    try:
        anomalies = repository.fetch_recent_anomalies(limit=20)
    except OperationalError as e:
        logger.info("anomalies tablosu henüz yok: {}", e)
        st.info("Henüz anomali yok — detector servisi (`python -m detectors`) çalıştı mı?")
        return
    if not anomalies:
        st.caption("Aktif uyarı yok.")
        return
    st.dataframe(anomalies_to_frame(anomalies), use_container_width=True, hide_index=True)
```

- [ ] **Step 3: `main()`'de paneli çağır** — `src/dashboard/app.py`

`main()` içinde, `if not devices: ... return` bloğundan SONRA, `device_id = st.sidebar.selectbox(...)` satırından ÖNCE ekle:
```python
    _render_alerts(repository)
    st.divider()
```
(Panel filo geneli — cihaz seçiminden bağımsız, en üstte; altında per-cihaz grafikler.)

- [ ] **Step 4: mypy + ruff (app.py)**

Run: `.venv/bin/python -m mypy src/dashboard && ruff check src/dashboard`
Expected: temiz. (app.py unit-test YOK — ince presentation, Faz 3 deseni.)

- [ ] **Step 5: Headless boot smoke (çökmüyor mu)**

`app.py`'nin import + parse hatası vermediğini doğrula (Faz 3 boot-smoke deseni; AppTest fragment timeout gotcha'sı için boş-DB ile):
```bash
DASHBOARD_DB_PATH=/tmp/empty_dash.db PYTHONPATH=src .venv/bin/python - <<'PY'
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("src/dashboard/app.py", default_timeout=10)
at.run()
assert not at.exception, at.exception
print("dashboard boot OK (no exception)")
PY
```
Expected: "dashboard boot OK" — boş/eksik DB'de main() **telemetry `list_devices()` OperationalError guard'ında** (app.py'deki `st.info`+`return`) erken döner; `_render_alerts`'e VE `run_every` fragment'ine HİÇ ulaşmaz → fragment timeout gotcha'sı tetiklenmez, çökme yok.

> NOT: Bu boot-smoke import + erken-dönüş yolunu doğrular (fragment çalışmaz çünkü main() ondan önce return eder). Fragment'in canlı görsel doğrulaması (gerçek anomalili DB ile) controller manuel smoke'ta.

- [ ] **Step 6: Commit**

```bash
git add src/dashboard/app.py
git commit -m "feat(dashboard): Aktif Uyarılar paneli (fetch_recent_anomalies, Faz 4 Iter 4.3)"
```

---

## Controller Closure (subagent task'larından SONRA — sen yaparsın)

1. **Canlı uçtan-uca smoke + FP doğrulama (kabul kriteri 3 + 4):**
   - `cp config/detectors.yaml.example config/detectors.yaml`; simulator + ingestion + detectors paralel (devices.yaml device_002 mechanical_wear, device_003 hydraulic_leak+electrical_fault).
   - `streamlit run src/dashboard/app.py` → "Aktif Uyarılar" paneli fused alert'leri gösteriyor (cihaz/severity/sensör/zaman).
   - **Fusion + debounce doğrula:** persisting kaçak artık her poll'da değil epizot başına ~1 satır (Iter 4.2'de 24×'ti). `sqlite3 data/telemetry.db "SELECT rule_name, COUNT(*) FROM anomalies GROUP BY rule_name"` — fused(N) satırları + tekil kurallar.
   - **FP-oranı:** clean device_001 birkaç dakika izlenir → saatte birkaç adetten az anomali (kabul kriteri 4). Temizlik: `sqlite3 ... "DELETE FROM anomalies; DELETE FROM telemetry"` (gitignored dev DB).
2. **Doküman:** CLAUDE.md "Mevcut Faz" → Iter 4.3 closure (fusion + debounce + dashboard paneli); **Faz 4 TAMAMLANDI** bloğu (4 iterasyon, kabul kriteri 1-5). ROADMAP § Faz 4 → tüm iterasyonlar ✅ + kriter 3 (dashboard) karşılandı; Sıradaki Faz 5.
3. **Memory:** `project_active_phase` → Faz 4 DONE, Faz 5 (istatistiksel dedektör) next; fusion/debounce runtime contract.
4. **Final whole-iteration review** (spec-compliance + code-quality).
5. **Push YAPMA** — kullanıcı onayı al.

---

## Self-Review (writing-plans)

**Spec coverage (Iter 4.3 maddeleri, spec § 3):**
- Minimal fusion (aynı device+pencere çoklu kural → tek skorlu alert + katkı listesi + maks skor) → Task 1 (`fuse_anomalies`) + Task 2 (`_detect_once` entegrasyon) ✅
- Dashboard "Aktif Uyarılar" paneli (`fetch_recent_anomalies`; cihaz/severity/sensör/zaman) → Task 3 (transform) + Task 4 (panel) ✅
- FP-oranı doğrulama (saatte birkaç adetten az) → Controller closure (canlı smoke) + epizot debounce gürültü azaltma ✅
- Gözlem modu korunur → `_detect_once` yalnız `insert_anomaly` yazar; dashboard yalnız okur ✅

**Tip/imza tutarlılığı:** `fuse_anomalies(list[Anomaly]) -> Anomaly | None` (Task 1) → Task 2 `_detect_once` kullanır. `_detect_once(repo, detectors, window_s, active: dict[str, frozenset[str]], now)` (Task 2) → `run()` + her iki test dosyası aynı imzayı kullanır. `anomalies_to_frame(list[Anomaly]) -> pd.DataFrame` kolonları `_ALERT_COLUMNS` (Task 3) → Task 4 `st.dataframe` ile gösterir. `Anomaly` 9 alan (mevcut) değişmez.

**Placeholder taraması:** Her kod adımı tam içerik; "TODO/uygun hata yönetimi" yok. Re-arm testi raw SQL UPDATE ile deterministik (seed yok). app.py boot-smoke gotcha (fragment timeout) açıkça not edildi.

**Bağımlılık sırası:** Task 1 (fusion) → Task 2 (service entegrasyon, fusion'a bağlı) → Task 3 (transform) → Task 4 (panel, transform'a bağlı). Doğru. Detector track (1-2) + dashboard track (3-4) bağımsız ama sıralı yürütülür.

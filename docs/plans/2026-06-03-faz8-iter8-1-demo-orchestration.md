# Faz 8 Iter 8.1 — Demo Orkestrasyon + Senaryolar + Runbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tek komutla (`./scripts/demo_up.sh`) güvenilir, tekrarlanabilir bir 15-dakikalık demo: 5 süreç (mosquitto + ingestion + detectors + simulator + dashboard) başlar, choreographed demo filosu ≥3 arızayı (kural + istatistik canlı) gösterir, alert lifecycle (manuel ack/resolve + auto-resolve) sergilenir; `demo_down.sh` temiz kapatır.

**Architecture:** Mevcut servisler/giriş noktaları DEĞİŞMEZ. İnce bir bash launcher + temiz-baseline pre-seed (istatistik canlı tetiklensin) + demo-özel config'ler (`devices.demo.yaml`/`detectors.demo.yaml`) + `docs/DEMO.md` runbook eklenir. Kesin demo zamanlamaları (onset/duration/baseline_window_s/seed) **canlı çalıştırmayla kalibre edilir** (Faz 5 dersi).

**Tech Stack:** bash (launcher), Python 3.11 (seed script, storage reuse), pytest (config-load testleri), mevcut servisler (`python -m simulator|ingestion|detectors`, `streamlit run`). Venv: `.venv/bin/python`; ruff = homebrew `ruff` (PATH).

---

## Spec Referansı
Tek hakem: `docs/specs/2026-06-03-faz8-iter8-1-demo-orchestration-design.md`. Choreography § 4, pre-seed § 5, launcher § 6, config § 7, docs § 8, test § 9, kabul § 10.

## Önemli Mevcut Kontratlar (koddan doğrulandı)
- `simulator.config.load_devices(path: Path) -> list[DeviceConfig]`; `DeviceConfig.id`, `.scenarios: list[ScenarioWindow]`; `ScenarioWindow(name, start_after_s, duration_s, params)`.
- `detectors.config.load_detector_config(path: Path) -> DetectorConfig`; `.statistical: StatisticalConfig | None` (`.baseline_window_s`, `.current_window_s`, `.detectors`), `.rules`.
- `ingestion.message_parser.IngestedReading(device_id, sensor, timestamp, state, value, unit)` (frozen).
- `storage.repository.TelemetryRepository(engine)`; `.insert_batch(list[IngestedReading])`. `storage.engine.create_sqlite_engine(db_path)`; `storage.migrator.apply_migrations(engine, MIGRATIONS_DIR)`.
- Giriş noktaları CLI argümanı ALMAZ — default path: simulator `config/{mqtt,devices,simulator}.yaml`, ingestion `config/{mqtt,ingestion}.yaml`, detectors `config/{ingestion,detectors}.yaml`. → launcher demo config'lerini runtime path'lerine kopyalar.
- DeviceState değerleri: `idle`/`raising`/`holding`/`lowering` (StrEnum value'ları).

## Dosya Yapısı
**Yeni:** `config/devices.demo.yaml`, `config/detectors.demo.yaml`, `scripts/seed_demo_baseline.py`, `scripts/demo_up.sh`, `scripts/demo_down.sh`, `docs/DEMO.md`, `tests/unit/test_demo_configs.py`, `tests/unit/test_seed_demo_baseline.py`.
**Değişen:** `.claude/commands/run-simulation.md`, `README.md`.
**Değişmez:** `src/` altındaki TÜM üretim kodu (girdi kontratı).

---

### Task 1: Demo config dosyaları + config-load testleri

**Files:**
- Create: `config/devices.demo.yaml`, `config/detectors.demo.yaml`
- Test: `tests/unit/test_demo_configs.py`

- [ ] **Step 1: Failing test yaz** (`tests/unit/test_demo_configs.py`)
```python
"""Demo config'leri parse + içerik doğrular (Faz 8 Iter 8.1, spec § 9)."""
from __future__ import annotations

from pathlib import Path

from detectors.config import load_detector_config
from simulator.config import load_devices

_DEVICES_DEMO = Path("config/devices.demo.yaml")
_DETECTORS_DEMO = Path("config/detectors.demo.yaml")


def test_devices_demo_has_clean_and_three_faults() -> None:
    """4 cihaz: device_001 temiz (senaryosuz) + mechanical_wear + hydraulic_leak + electrical_fault."""
    devices = load_devices(_DEVICES_DEMO)
    assert len(devices) == 4
    by_id = {d.id: d for d in devices}
    assert by_id["device_001"].scenarios == []  # temiz kontrol
    scenario_names = {s.name for d in devices for s in d.scenarios}
    assert {"mechanical_wear", "hydraulic_leak", "electrical_fault"} <= scenario_names


def test_devices_demo_has_short_clearing_fault() -> None:
    """En az bir arıza KISA süreli (biter → auto-resolve demo beat'i): duration_s <= 300."""
    devices = load_devices(_DEVICES_DEMO)
    durations = [s.duration_s for d in devices for s in d.scenarios]
    assert any(dur <= 300 for dur in durations), f"kısa-süreli arıza yok: {durations}"


def test_devices_demo_fast_onset() -> None:
    """Arızalar demo-zamanında başlar (onset <= 180s) — 15-dk demoya sığsın."""
    devices = load_devices(_DEVICES_DEMO)
    onsets = [s.start_after_s for d in devices for s in d.scenarios]
    assert onsets and max(onsets) <= 180, f"geç onset: {onsets}"


def test_detectors_demo_reduced_baseline_and_rules_present() -> None:
    """detectors.demo: istatistik baseline_window_s < 3600 (demo'da canlı tetiklensin) + kural seti dolu."""
    config = load_detector_config(_DETECTORS_DEMO)
    assert config.statistical is not None
    assert config.statistical.baseline_window_s < 3600
    assert len(config.rules) >= 5  # üretim kural seti korunur
```

- [ ] **Step 2: Testi koştur, fail doğrula**
Run: `.venv/bin/python -m pytest tests/unit/test_demo_configs.py -v`
Expected: FAIL — `FileNotFoundError` (config/devices.demo.yaml yok).

- [ ] **Step 3: `config/devices.demo.yaml` yaz**

> **Kalibrasyon notu:** Aşağıdaki süreler tasarım hedefi BAŞLANGIÇ değerleridir; Task 5 canlı smoke'ta ölçülerek ayarlanır (istatistik baseline-sonrası tetikleniyor + hydraulic slope rule yeterli HOLDING örneği görüyor + mechanical kısa-arıza temizlenip auto-resolve oluyor mu). hydraulic_leak cihazı UZUN holding ister (slope kuralı min_samples 60); mechanical/electrical orta cycling.

```yaml
# Demo filosu (Faz 8 Iter 8.1): temiz kontrol + A/B/C choreographed.
# demo_up.sh bunu config/devices.yaml'a kopyalar. Süreler Task 5 canlı smoke ile kalibre edilir.
devices:
  # device_001: temiz kontrol — hiç arıza, hiç uyarı (kontrast + FP yok kanıtı).
  - id: device_001
    type: telescopic_mast_v1
    seed: 42
    target_height_mm: 5000
    state_durations:
      idle:     [3, 3]
      raising:  [15, 15]
      holding:  [30, 30]
      lowering: [3, 3]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}

  # device_002: mechanical_wear — KISA süreli (biter → auto-resolve beat'i).
  # motor_current+vibration RAISING'de yükselir → kural (motor_current_high) + istatistik (three_sigma) overlap.
  - id: device_002
    type: telescopic_mast_v1
    seed: 7
    target_height_mm: 6000
    state_durations:
      idle:     [3, 3]
      raising:  [15, 15]
      holding:  [30, 30]
      lowering: [3, 3]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: mechanical_wear
        start_after_s: 60          # baseline (seed) hazır; ~1dk temiz izleme sonrası
        duration_s: 150            # KISA → ~t=210s'te biter → auto-resolve
        params: {severity: 0.25, ramp_up_s: 30}

  # device_003: hydraulic_leak — UZUN holding (slope kuralı min_samples 60 ister).
  - id: device_003
    type: telescopic_mast_v1
    seed: 123
    target_height_mm: 4500
    state_durations:
      idle:     [3, 3]
      raising:  [10, 10]
      holding:  [180, 180]
      lowering: [3, 3]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: hydraulic_leak
        start_after_s: 60
        duration_s: 1800
        params: {leak_rate_bar_per_min: 5.0, position_sag_mm: 2.0}

  # device_004: electrical_fault — varyans arızası (kural motor_voltage_erratic; istatistik sessiz = tamamlayıcı).
  - id: device_004
    type: telescopic_mast_v1
    seed: 99
    target_height_mm: 5500
    state_durations:
      idle:     [3, 3]
      raising:  [15, 15]
      holding:  [30, 30]
      lowering: [3, 3]
    sensors:
      - {name: motor_current,      unit: A,       baseline: 0.5,  noise_std: 0.1}
      - {name: motor_voltage,      unit: V,       baseline: 24.0, noise_std: 0.2}
      - {name: hydraulic_pressure, unit: bar,     baseline: 10,   noise_std: 2}
      - {name: motor_temperature,  unit: celsius, baseline: 25,   noise_std: 0.5}
      - {name: mast_position,      unit: mm,      baseline: 0,    noise_std: 1}
      - {name: vibration,          unit: g,       baseline: 0.05, noise_std: 0.01}
    scenarios:
      - name: electrical_fault
        start_after_s: 60
        duration_s: 1800
        params: {spike_prob: 0.05, voltage_jitter_std: 0.6}
```

- [ ] **Step 4: `config/detectors.demo.yaml` yaz**

`config/detectors.yaml.example` içeriğinin TAM kopyası, tek farkla: `statistical.baseline_window_s` 3600 → **300** ve `current_window_s` 60 (seed + reduced pencere ile istatistik demo süresinde tetiklensin). Kural bloğu birebir aynı (üretim eşik kalibrasyonu korunur). İçeriği `config/detectors.yaml.example`'dan kopyalayıp yalnız `statistical:` bloğunu şu hâle getir:
```yaml
statistical:
  baseline_window_s: 300      # DEMO: üretim 3600 yerine düşük → seed'li baseline ile canlı tetiklenir
  current_window_s: 60
  detectors:
    - name: three_sigma
      enabled: true
      severity: warning
      params: {sigma_k: 3.0, min_baseline: 20, min_current: 5}   # DEMO: 30→20 (kayan pencerede seed erimesine pay)
    - name: iqr
      enabled: true
      severity: warning
      params: {iqr_multiplier: 1.5, min_baseline: 20, min_current: 5}
```
(detectors bloğu = example'daki 6 kural aynen. `min_baseline` demo'da 20'ye düşürüldü çünkü seed kayan pencereden erir, B1; `baseline_window_s`/`min_baseline`/seed yoğunluğu Task 5 kalibrasyonunda ÖLÇÜLEREK ayarlanır.)

> **B1 — KRİTİK gerçek (plan-review):** İstatistik dedektör penceresi son `baseline_window_s` saniyedir ve `now` ile KAYAR. Seed bloğu zamanla pencereden ERİR; ayrıca arıza ilerledikçe baseline'a faulty veri sızıp **kontamine** olur (on-the-fly rolling'in doğası, Faz 5 § 12). Sonuç: **istatistik-overlap GEÇİCİdir** — arıza onset'inden kısa süre sonra (current fault-dominant + baseline hâlâ temiz) bir "fırsat penceresi"nde tetiklenir, alert bir kez kalkınca debounce ile kalır. **Demo'nun GARANTİ omurgası = kural-katmanı tespiti + lifecycle + auto-resolve (sağlam).** İstatistik-overlap = kalibre edilen, geçici bir beat; Task 5 onu ölçer + ayarlar; gösterilemezse DEMO.md fallback (reduced-baseline config'i + geçici doğası sözlü anlatılır). Bu dürüst çerçeve plana + DEMO.md'ye yazılır.

- [ ] **Step 5: Testi koştur, geç doğrula**
Run: `.venv/bin/python -m pytest tests/unit/test_demo_configs.py -v`
Expected: PASS (4 test).

- [ ] **Step 6: mypy + ruff + commit**
```bash
.venv/bin/python -m mypy tests/unit/test_demo_configs.py
ruff check tests/unit/test_demo_configs.py
git add config/devices.demo.yaml config/detectors.demo.yaml tests/unit/test_demo_configs.py
git commit -m "feat(demo): devices.demo + detectors.demo config'leri + load testleri (Faz 8 Iter 8.1)"
```

---

### Task 2: Temiz baseline seed script + test

**Files:**
- Create: `scripts/seed_demo_baseline.py`
- Test: `tests/unit/test_seed_demo_baseline.py`

Amaç: servisler başlamadan önce demo cihazları için **yakın-geçmiş temiz telemetri** yazmak → istatistik dedektör baseline'ı HAZIR (uzun gerçek-zamanlı warmup gerekmez, spec § 5). Ölçülen-temiz (Faz 5) per-(sensor,state) magnitüdleri kullanılır.

- [ ] **Step 1: Failing test yaz** (`tests/unit/test_seed_demo_baseline.py`)
```python
"""seed_demo_baseline: temiz baseline DB'ye yazılır, (sensor,state) başına ≥min_baseline (Faz 8 Iter 8.1)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import text

from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations

_SCRIPT = Path("scripts/seed_demo_baseline.py")


def _load_seed_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("seed_demo_baseline", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_writes_clean_baseline(tmp_path: Path) -> None:
    """seed_baseline temiz telemetri yazar; motor_current RAISING ≥30 örnek (statistical min_baseline)."""
    db = tmp_path / "telemetry.db"
    engine = create_sqlite_engine(db)
    apply_migrations(engine, MIGRATIONS_DIR)
    mod = _load_seed_module()
    # seed_baseline(db_path, devices, window_s, samples_per_state) — saf fonksiyon, now DI ile.
    mod.seed_baseline(db_path=db, device_ids=["device_002"], window_s=300, samples_per_state=40)
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM telemetry WHERE device_id='device_002' "
            "AND sensor='motor_current' AND state='raising'"
        )).scalar_one()
    assert n >= 30
    engine.dispose()
```

- [ ] **Step 2: Testi koştur, fail doğrula**
Run: `.venv/bin/python -m pytest tests/unit/test_seed_demo_baseline.py -v`
Expected: FAIL — `FileNotFoundError`/`spec is None` (script yok).

- [ ] **Step 3: `scripts/seed_demo_baseline.py` yaz**
```python
"""Demo temiz baseline seed (Faz 8 Iter 8.1, spec § 5).

Servisler başlamadan önce demo cihazları için yakın-geçmiş TEMİZ telemetri yazar →
istatistik dedektör (ThreeSigma/IQR) baseline'ı hazır olur, arıza ~60s'de başlayınca
canlı tetiklenir (uzun gerçek-zamanlı warmup gerekmez). Gözlem modu: yalnız telemetry yazar.

NOT (B1, kayan pencere): seed bloğu zamanla `baseline_window_s`'lik kayan pencereden ERİR →
istatistik-overlap GEÇİCİ bir fırsat penceresinde gösterilir (yoğunluk `samples_per_state` +
`min_baseline` Task 5'te ölçülerek ayarlanır). NOT (S3): `__main__` `config/ingestion.yaml`
ister — demo_up.sh seed'den ÖNCE config'leri kopyalar; standalone çalıştırırken önce
`cp config/ingestion.yaml.example config/ingestion.yaml`.

Per-(sensor,state) temiz magnitüdler Faz 5 ölçümlerinden (seed 42, üretim çıktısı).
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ingestion.message_parser import IngestedReading
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository

# Ölçülen temiz per-(sensor, state) ortalamalar (Faz 5) + makul std (σ>0 → fence degenere değil).
# Yalnız arızaların tezahür ettiği RAISING + HOLDING durumları (istatistik bu state'lerde tetiklenir).
_CLEAN: dict[str, dict[str, tuple[float, float]]] = {
    "motor_current":      {"raising": (8.0, 0.1),  "holding": (0.5, 0.1)},
    "vibration":          {"raising": (0.30, 0.01), "holding": (0.05, 0.01)},
    "hydraulic_pressure": {"raising": (150.0, 2.0), "holding": (80.0, 2.0)},
    "motor_voltage":      {"raising": (24.0, 0.2),  "holding": (24.0, 0.2)},
    "motor_temperature":  {"raising": (31.0, 1.5),  "holding": (34.0, 1.5)},
}

_UNITS = {
    "motor_current": "A", "vibration": "g", "hydraulic_pressure": "bar",
    "motor_voltage": "V", "motor_temperature": "celsius",
}


def _iso(now: datetime, back_s: float) -> str:
    return (now - timedelta(seconds=back_s)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed_baseline(
    db_path: Path,
    device_ids: list[str],
    window_s: int,
    samples_per_state: int,
    now: datetime | None = None,
) -> int:
    """Demo cihazları için temiz baseline telemetri yazar.

    Her (cihaz, sensör, state) için `samples_per_state` örnek, son `window_s` saniyeye yayılı,
    ölçülen temiz ortalama ± deterministik küçük salınım (σ>0). now DI ile (test edilebilir).

    Returns:
        Yazılan satır sayısı.
    """
    now = now or datetime.now(UTC)
    engine = create_sqlite_engine(db_path)
    rows: list[IngestedReading] = []
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        step = window_s / max(1, samples_per_state)
        for device_id in device_ids:
            for sensor, states in _CLEAN.items():
                for state, (mean, std) in states.items():
                    for i in range(samples_per_state):
                        # Deterministik üçlü salınım → σ>0 garanti (gauss gerekmez).
                        val = mean + std * ((i % 3) - 1)
                        back = window_s - i * step  # eski→yeni
                        rows.append(IngestedReading(
                            device_id=device_id, sensor=sensor, timestamp=_iso(now, back),
                            state=state, value=val, unit=_UNITS[sensor],
                        ))
        repo.insert_batch(rows)
        return len(rows)
    finally:
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    from ingestion.config import load_ingestion_config

    cfg = load_ingestion_config(Path("config/ingestion.yaml"))
    written = seed_baseline(
        db_path=Path(cfg.db_path),
        device_ids=["device_001", "device_002", "device_003", "device_004"],
        window_s=300,
        samples_per_state=80,  # yoğun: kayan pencerede erime + min_baseline=20 için pay (B1; Task 5 kalibre)
    )
    print(f"seed_demo_baseline: {written} temiz baseline satırı yazıldı", file=sys.stderr)
```

- [ ] **Step 4: Testi koştur, geç doğrula**
Run: `.venv/bin/python -m pytest tests/unit/test_seed_demo_baseline.py -v`
Expected: PASS (1 test; device_002 motor_current raising = 40 ≥ 30).

- [ ] **Step 5: mypy + ruff + commit**
```bash
.venv/bin/python -m mypy scripts/seed_demo_baseline.py tests/unit/test_seed_demo_baseline.py
ruff check scripts/seed_demo_baseline.py tests/unit/test_seed_demo_baseline.py
git add scripts/seed_demo_baseline.py tests/unit/test_seed_demo_baseline.py
git commit -m "feat(demo): temiz baseline seed script (istatistik canlı güvencesi) (Faz 8 Iter 8.1)"
```

---

### Task 3: Launcher script'leri (demo_up.sh + demo_down.sh)

**Files:**
- Create: `scripts/demo_up.sh`, `scripts/demo_down.sh`

Shell orkestrasyon — `bash -n` sözdizimiyle doğrulanır; fonksiyonel doğrulama Task 5 canlı smoke.

- [ ] **Step 1: `scripts/demo_down.sh` yaz** (önce teardown — demo_up onu çağırır)
```bash
#!/usr/bin/env bash
# Demo teardown (Faz 8 Iter 8.1): data/demo.pids'teki süreçleri temiz kapatır. Idempotent.
# Mosquitto'ya DOKUNMAZ (kullanıcının olabilir).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/data/demo.pids"

if [[ ! -f "$PIDFILE" ]]; then
  echo "demo_down: çalışan demo yok (pidfile yok)."
  exit 0
fi

pids=()
while read -r pid name; do
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "demo_down: $name (pid $pid) kapatılıyor..."
    kill -TERM "$pid" 2>/dev/null || true
    pids+=("$pid")
  fi
done < "$PIDFILE"

# Graceful shutdown'a kısa süre tanı (BatchWriter final flush + engine dispose) — S4.
for _ in 1 2 3 4 5; do
  alive=0
  for pid in "${pids[@]:-}"; do [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && alive=1; done
  [[ "$alive" -eq 0 ]] && break
  sleep 1
done

rm -f "$PIDFILE"
echo "demo_down: temiz kapandı."
```

- [ ] **Step 2: `scripts/demo_up.sh` yaz**
```bash
#!/usr/bin/env bash
# Demo launcher (Faz 8 Iter 8.1): tek komutla 5 süreç + temiz baseline seed.
# Kullanım: ./scripts/demo_up.sh   (kapatma: ./scripts/demo_down.sh)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
PIDFILE="$ROOT/data/demo.pids"
LOGDIR="$ROOT/logs/demo"

[[ -x "$PY" ]] || { echo "HATA: .venv yok ($PY). Önce: python3.11 -m venv .venv && pip install -r requirements.txt -e ."; exit 1; }

# 1) Cleanup-first: eski demo süreçlerini kapat (çift ingestion / client_id collision'ı önle).
bash "$ROOT/scripts/demo_down.sh" || true
mkdir -p "$ROOT/data" "$LOGDIR"

# 2) Mosquitto: çalışmıyorsa başlat (varsa dokunma).
if ! pgrep -x mosquitto >/dev/null 2>&1; then
  echo "demo_up: mosquitto başlatılıyor..."
  brew services start mosquitto >/dev/null 2>&1 || mosquitto -d || {
    echo "HATA: mosquitto başlatılamadı. Manuel başlatın."; exit 1; }
  sleep 1
fi

# 3) Config'ler: eksik runtime config'leri example'dan; devices/detectors'ı demo'dan (yedekle).
for ex in config/*.yaml.example; do
  rt="${ex%.example}"
  [[ -f "$rt" ]] || cp "$ex" "$rt"
done
for f in devices detectors; do
  [[ -f "config/$f.yaml" ]] && cp "config/$f.yaml" "config/$f.yaml.bak"
  cp "config/$f.demo.yaml" "config/$f.yaml"
done

# 4) DB temizliği: tekrarlanabilir demo (arşivle, sessiz silme yok).
if [[ -f data/telemetry.db ]]; then
  mv -f data/telemetry.db "data/telemetry.db.pre-demo"
  rm -f data/telemetry.db-wal data/telemetry.db-shm
fi

# 5) Temiz baseline seed (istatistik canlı tetiklensin).
echo "demo_up: temiz baseline seed'leniyor..."
PYTHONPATH=src "$PY" scripts/seed_demo_baseline.py

# 6) Servisleri sırayla başlat (arka planda); PID'leri kaydet.
: > "$PIDFILE"
start() {  # start <isim> <komut...>
  local name="$1"; shift
  echo "demo_up: $name başlatılıyor..."
  PYTHONPATH=src "$@" >"$LOGDIR/$name.log" 2>&1 &
  local pid=$!
  echo "$pid $name" >> "$PIDFILE"
  sleep 2
  # Liveness check: arka plan süreci hemen çökerse banner yalan söylemesin (B2).
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "HATA: $name başlatılamadı/çöktü. Son loglar:"
    tail -n 20 "$LOGDIR/$name.log" || true
    bash "$ROOT/scripts/demo_down.sh" || true
    exit 1
  fi
}
start ingestion "$PY" -m ingestion
start detectors "$PY" -m detectors
start simulator "$PY" -m simulator
start dashboard "$PY" -m streamlit run src/dashboard/app.py

echo ""
echo "demo_up: TÜM servisler çalışıyor. Dashboard → http://localhost:8501"
echo "demo_up: loglar → $LOGDIR/   | kapatmak için → ./scripts/demo_down.sh"
```

- [ ] **Step 3: Sözdizimi + executable + (varsa) shellcheck**
```bash
chmod +x scripts/demo_up.sh scripts/demo_down.sh
bash -n scripts/demo_up.sh && bash -n scripts/demo_down.sh && echo "syntax OK"
command -v shellcheck >/dev/null && shellcheck scripts/demo_up.sh scripts/demo_down.sh || echo "shellcheck yok — atlandı"
```
Expected: `syntax OK`. (shellcheck varsa uyarıları gözden geçir; kritik olanları düzelt, stilistikleri not et.)

- [ ] **Step 4: demo_down idempotency hızlı kontrol** (servis başlatmadan, güvenli)
```bash
rm -f data/demo.pids; bash scripts/demo_down.sh
```
Expected: `demo_down: çalışan demo yok (pidfile yok).` (exit 0, hata yok).

- [ ] **Step 5: Commit**
```bash
git add scripts/demo_up.sh scripts/demo_down.sh
git commit -m "feat(demo): demo_up/demo_down launcher (cleanup-first + seed + 5 süreç) (Faz 8 Iter 8.1)"
```

---

### Task 4: Dokümantasyon (DEMO.md + run-simulation düzeltme + README)

**Files:**
- Create: `docs/DEMO.md`
- Modify: `.claude/commands/run-simulation.md`, `README.md`

- [ ] **Step 1: `docs/DEMO.md` yaz**
```markdown
# Demo Runbook — Teleskopik Mast Anomali Tespiti (Faz 8)

15 dakikada uçtan-uca: 2-katmanlı tespit (kural + istatistik) + füzyon + yönetilebilir uyarı yaşam döngüsü.

## Önkoşullar
- Python venv: `python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt -e .`
- Mosquitto (macOS): `brew install mosquitto`
- Boş portlar: 1883 (MQTT), 8501 (dashboard).

## Tek Komutla Çalıştırma
```bash
./scripts/demo_up.sh          # 5 süreç + temiz baseline seed; mosquitto'yu gerekiyorsa başlatır
# Tarayıcı: http://localhost:8501
./scripts/demo_down.sh        # temiz kapat (mosquitto'ya dokunmaz)
```
`demo_up.sh` `config/devices.yaml` ve `config/detectors.yaml`'ı demo sürümleriyle DEĞİŞTİRİR (eskisini `.bak`'a yedekler) ve `data/telemetry.db`'yi `data/telemetry.db.pre-demo`'ya arşivler. Loglar: `logs/demo/`.

## 15 Dakikalık Akış (beat-by-beat)
1. **t≈0-60s — Temiz izleme:** Dashboard'da 6 sensör akar, "Uyarılar" boş. Mimariyi anlat: simulator → ingestion → SQLite → kural+istatistik dedektör → fusion → alert lifecycle → dashboard. (İstatistik baseline seed'den hazır.)
2. **t≈60-120s — Kural tespiti:** device_002 (mechanical_wear) → `motor_current_high` `active` uyarı. device_003 (hydraulic_leak) → `hydraulic_pressure_decline`. device_004 (electrical_fault) → `motor_voltage_erratic`. device_001 temiz kalır (FP yok).
3. **t≈120-180s — İki-katman overlap (GEÇİCİ fırsat penceresi):** device_002'de istatistik `three_sigma:motor_current` (+`iqr`) katılır → `fused(N)` (kural+istatistik aynı arızayı corroborate eder). **Not:** istatistik on-the-fly rolling baseline kullanır; arıza onset'inden kısa süre sonra (current fault-dominant, baseline hâlâ temiz) tetiklenir ve alert kalkınca debounce ile kalır — bu yüzden overlap'i arıza belirir belirmez gösterin. electrical_fault'ta istatistik SESSİZ — varyans arızası kural-katmanı işi (tamamlayıcılık). Overlap görünmezse: kural-katmanı tespiti zaten sağlam; istatistik üretimde ~1 saat baseline ile çalışır (bkz. Bilinen Sınırlar).
4. **Manuel yaşam döngüsü:** Dashboard'da bir uyarıyı **Gör (ack)**, başkasını **Çöz (resolve)** yap; durum filtresiyle açık/kapalı gez.
5. **t≈3-4dk — Auto-resolve:** device_002 mechanical_wear biter → detector arızanın temizlendiğini görür → uyarı **otomatik `resolved`** (durum filtresinde görünür).

## Bilinen Sınırlar
- **İstatistik üretimde ~1 saat baseline ister** — demo'da seed + reduced `baseline_window_s` (300s) ile canlı gösterilir.
- **Faz 6 (ML) atlandı** → Faz 9+ stretch (sentetik veride marjinal tespit değeri düşük).
- **Alert lifecycle (Faz 7 § 9):** süregelen arızayı manuel resolve → kural-seti değişene dek yeni uyarı açılmaz; detector restart / auto-resolve DB hatası → orphan açık uyarı (manuel kapat); eskalasyonda cihaz başına >1 açık uyarı.
- `demo_up.sh` runtime config'leri overwrite eder (`.bak`'tan geri al).

## Sorun Giderme
- **Port dolu (8501/1883):** önceki demo açık olabilir → `./scripts/demo_down.sh`; mosquitto: `brew services list`.
- **ImportError:** `.venv` aktif + `pip install -e .`; launcher zaten `PYTHONPATH=src` kullanır.
- **İki ingestion / mesaj kaybı:** aynı anda tek demo instance (client_id collision). `demo_up.sh` başta eskiyi kapatır.
- **Servis ayağa kalkmadı:** `logs/demo/<servis>.log`'a bak.
```

- [ ] **Step 2: `.claude/commands/run-simulation.md`'i gerçeğe göre düzelt**
Mevcut dosyadaki yanlış "Çalıştırma Sırası" bölümünü (özellikle `python -m src.alerts`, `python -m src.ingestion`, `python -m src.simulator --scenario`) şununla DEĞİŞTİR:
```markdown
## Çalıştırma Sırası

**En kolay yol — tek komut:** `./scripts/demo_up.sh` (bkz. `docs/DEMO.md`). Tüm servisleri + temiz baseline seed'i başlatır. Kapatma: `./scripts/demo_down.sh`.

**Manuel (ayrı terminaller, `PYTHONPATH=src` + `.venv`):**
1. **Mosquitto** (çalışmıyorsa): `brew services start mosquitto`
2. **Ingestion**: `PYTHONPATH=src .venv/bin/python -m ingestion`
3. **Detector**: `PYTHONPATH=src .venv/bin/python -m detectors`  (kural + istatistik katmanları; `alerts` ayrı servis DEĞİL — detector içinde yaşam döngüsü)
4. **Simulator** (en son): `PYTHONPATH=src .venv/bin/python -m simulator`  (senaryolar `config/devices.yaml`'da tanımlı; `--scenario` argümanı YOK)
5. **Dashboard**: `.venv/bin/python -m streamlit run src/dashboard/app.py`

> Not: önce `cp config/*.yaml.example config/*.yaml` (gitignored runtime config'ler). Demo için `demo_up.sh` bunu + demo config'lerini otomatik yapar.
```
(Dosyanın "Sorulacaklar"/"Önkoşullar"/"İzleme" bölümleri kalabilir; yalnız yanlış çağrıları düzelt.)

- [ ] **Step 3: `README.md` "Çalıştırma" bölümünü düzelt**
README'deki "Çalıştırma" bölümünü doğru komutlara güncelle + demo işaretçisi ekle:
```markdown
## Çalıştırma

**Demo (tek komut):**
```bash
./scripts/demo_up.sh      # tüm servisler + temiz baseline; http://localhost:8501
./scripts/demo_down.sh    # temiz kapat
```
15 dakikalık demo akışı ve sorun giderme: **`docs/DEMO.md`**.

**Manuel servisler** (ayrı terminaller, `PYTHONPATH=src` + `.venv`): `python -m ingestion`, `python -m detectors`, `python -m simulator`, `streamlit run src/dashboard/app.py`. (`alerts` ayrı servis değildir — uyarı yaşam döngüsü detector içinde.)
```
(Mevcut README'nin diğer bölümleri korunur; yalnız Çalıştırma bölümü doğrulanır/güncellenir.)

- [ ] **Step 4: Commit**
```bash
git add docs/DEMO.md .claude/commands/run-simulation.md README.md
git commit -m "docs(demo): DEMO.md runbook + run-simulation skill düzeltme + README (Faz 8 Iter 8.1)"
```

---

### Task 5: Kalibrasyon + canlı demo smoke + kapanış (controller)

Bu task subagent'a verilmez — controller (ana oturum) yürütür. **Asıl kabul gate'i: gerçek demo çalışıyor mu.** Faz 5 dersi: canlı smoke + ölçümle kalibrasyon şart.

- [ ] **Step 1: Tam suite + mypy + ruff**
Run: `.venv/bin/python -m pytest -q` (mevcut 309 + Task1 4 + Task2 1 = ~314 passed, 1 skipped; kesin sayı yürütmede doğrulanır).
Run: `.venv/bin/python -m mypy src/simulator src/ingestion src/storage src/detectors src/alerts src/dashboard scripts/seed_demo_baseline.py tests/unit tests/integration tests/scenarios`
Run: `ruff check src/... scripts/seed_demo_baseline.py tests/...` → temiz.

- [ ] **Step 2: Canlı demo smoke + KALİBRASYON**
1. `./scripts/demo_up.sh` çalıştır; ~3-4 dk gözle (veya `sleep` + sorgu).
2. Doğrula: 5 süreç up (`cat data/demo.pids`, `logs/demo/*.log` hatasız); dashboard erişilebilir (`curl -s localhost:8501 | head`).
3. `sqlite3 data/telemetry.db "SELECT device_id, rule_name, status FROM anomalies ORDER BY created_at"`:
   - device_002/003/004 → uyarı (kural); device_001 → uyarı YOK (FP yok).
   - **GARANTİ omurga (kabul kriteri 1-2):** device_002/003/004 kural uyarısı + device_001 FP yok + device_002 mechanical_wear bitince `resolved` (auto-resolve). Bunlar sağlam olmalı.
   - **İstatistik-overlap (geçici, B1):** device_002'de **`fused(...)`** içinde `three_sigma:motor_current` (+`iqr`) — onset'ten kısa süre sonra fırsat penceresinde. Ölçmek için arıza onset'i civarında birkaç poll'da `anomalies`'i izle. Bir kez `fused` kalktıysa debounce ile kalır (kanıt: description'da iki katman).
4. `./scripts/demo_down.sh` → temiz kapanış (`data/demo.pids` silinir, süreçler iner).
5. **Kalibrasyon (ölç, tahmin etme — [[feedback_domain_md_truth_source]]):**
   - **İstatistik-overlap tetiklenmiyorsa:** trigger anında baseline alt-penceresinde `(motor_current, raising)` temiz örnek sayısını ölç (`sqlite3 ... "SELECT COUNT(*) ... state='raising' AND created_at içinde [now-300,now-60]"` mantığı / logdan); `min_baseline`'ı (demo 20) ya da seed `samples_per_state`'i (80) ayarla; `current_window_s`'i küçült (baseline kontaminasyonunu geciktirir); onset'i `baseline_window_s` ile uyumla. **Yine de güvenilir gösterilemezse:** istatistik-overlap'i geçici/best-effort kabul et → DEMO.md fallback (reduced-baseline config + geçici doğa sözlü); GARANTİ omurga (kural+lifecycle+auto-resolve) demoyu taşır.
   - hydraulic rule tetiklenmiyorsa → device_003 holding süresini artır (slope min_samples 60). auto-resolve görünmüyorsa → device_002 `duration_s` kısalt. clean device FP veriyorsa → seed σ'sını gerçekçileştir / `min_baseline` artır.
   - Değişiklikleri ilgili config commit'ine ekle.

- [ ] **Step 3: Dokümanları güncelle (controller)**
- `CLAUDE.md` → "Mevcut Faz" + Faz 8 Iter 8.1 closure özeti (launcher + demo config + seed + kalibre değerler).
- `docs/ROADMAP.md` → Faz 8 Iter 8.1 ✅ (çalıştırma + ≥3 senaryo + runbook payı); Iter 8.2 (dashboard) next.
- Memory `project_active_phase.md` → Iter 8.1 DONE + demo runtime contract (demo_up/down, demo config'ler, seed) + kalibre değerler.

- [ ] **Step 4: Final whole-iteration review + closure commit**
Faz 5-7 deseni: tüm iterasyon diff'ine son review, sonra `docs(faz8): Iter 8.1 closure ...` commit. Push **proaktif yapılmaz** — kullanıcı onayı.

---

## Self-Review (yazım sonrası, spec karşılaştırması)

**Spec coverage:**
- § 3 dosya düzeni → Task 1-4 (configs, seed, scripts, docs) ✅
- § 4 choreography → devices.demo.yaml timing (Task 1) + DEMO.md beat-script (Task 4) + canlı kalibrasyon (Task 5) ✅
- § 5 pre-seed → Task 2 (`seed_demo_baseline.py`) ✅
- § 6 launcher (cleanup-first, mosquitto, config kopya+.bak, db arşiv, seed, 5 süreç, pidfile/log) → Task 3 demo_up/down ✅
- § 7 config (devices.demo 4 cihaz + kısa arıza; detectors.demo reduced baseline) → Task 1 ✅
- § 8 docs (DEMO.md + run-simulation fix + README) → Task 4 ✅
- § 9 test (config-load + seed + bash -n + canlı smoke) → Task 1/2/3 + Task 5 ✅
- § 10 kabul → Task 5 canlı smoke gate ✅
- § 12 `src/` değişmez → hiçbir task src/ üretim kodu değiştirmez (yalnız config/scripts/docs/tests) ✅

**Placeholder taraması:** "kalibrasyonla ayarlanır" = kasıtlı (gerçek-ölçüm gerektiren demo timing'i, spec § 2.5); her dosya tam başlangıç içeriğiyle verildi, soyut placeholder yok.

**Type/isim tutarlılığı:**
- `seed_baseline(db_path, device_ids, window_s, samples_per_state, now=None) -> int` — Task 2 tanımı ↔ test çağrısı ↔ `__main__` çağrısı tutarlı.
- `load_devices(path) -> list[DeviceConfig]` (`.id`, `.scenarios[].name/.start_after_s/.duration_s`) + `load_detector_config(path).statistical.baseline_window_s` — koddan doğrulandı, Task 1 testleri tutarlı.
- demo_up.sh ↔ demo_down.sh: ortak `data/demo.pids` formatı (`<pid> <name>` satırları) tutarlı.
- `IngestedReading(device_id, sensor, timestamp, state, value, unit)` — seed script kullanımı koddaki frozen dataclass ile tutarlı.

**YAGNI:** seed yalnız arıza-ilgili RAISING+HOLDING (mast_position non-stationary dışlandı; idle/lowering seyrek/gereksiz). Tek demo config seti; ayrı sunum slaytı yok (DEMO.md yeterli).

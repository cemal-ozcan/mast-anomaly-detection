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
    """Tek kural tetiklenince fused değil kendi rule_name'iyle yazılır; açık fingerprint oluşur."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]

    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)

    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1
    assert stored[0].rule_name == "motor_temperature_high"
    assert stored[0].value == 95.0
    assert repo.fetch_open_fingerprints() == {"device_001": {frozenset({"motor_temperature_high"})}}


def test_detect_once_fuses_multiple_rules(migrated_engine: Engine) -> None:
    """Aynı cihazda iki kural tetiklenince TEK fused(2) satır yazılır."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    for i, v in enumerate([24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]):
        repo.insert(_reading("motor_voltage", f"2026-05-30T00:01:{i:02d}.000Z", v))
    detectors: list[Detector] = [
        MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0),
        MotorVoltageErratic(std_threshold_v=1.0, min_samples=10, trip_std_v=5.0),
    ]

    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)

    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1
    assert stored[0].rule_name == "fused(2)"
    assert stored[0].severity == "critical"  # temp en yüksek severity
    assert "motor_temperature_high" in stored[0].description
    assert "motor_voltage_erratic" in stored[0].description
    assert repo.fetch_open_fingerprints() == {
        "device_001": {frozenset({"motor_temperature_high", "motor_voltage_erratic"})}
    }


def test_detect_once_debounces_persisting_fault(migrated_engine: Engine) -> None:
    """Aynı kural-seti iki ardışık turda süregelirse yalnız bir kez yazılır (epizot debounce)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]

    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)

    assert len(repo.fetch_recent_anomalies(limit=10)) == 1


def test_detect_once_rearms_after_fault_clears(migrated_engine: Engine) -> None:
    """Fault temizlenince açık uyarı auto-resolve olur; tekrar oluşursa YENİ satır yazılır (re-arm)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]

    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)  # tur 1: yazar
    # Fault temizlenir (değer eşik altına): cihaz hâlâ telemetri'ye sahip ama kural tetiklemez.
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 25.0 WHERE sensor = 'motor_temperature'"))
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)  # tur 2: tetik yok → re-arm
    assert repo.fetch_open_fingerprints() == {}
    # Fault geri döner:
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 95.0 WHERE sensor = 'motor_temperature'"))
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)  # tur 3: yeniden yazar

    assert len(repo.fetch_recent_anomalies(limit=10)) == 2  # tur 1 + tur 3


def test_detect_once_escalation_writes_new_row(migrated_engine: Engine) -> None:
    """Kural-seti büyürse (eskalasyon: 1 kural → 2 kural) debounce DEĞİL, YENİ fused satır yazılır."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [
        MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0),
        MotorVoltageErratic(std_threshold_v=1.0, min_samples=10, trip_std_v=5.0),
    ]

    # Tur 1: yalnız sıcaklık tetikler → tek kural satırı.
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)
    assert repo.fetch_open_fingerprints() == {"device_001": {frozenset({"motor_temperature_high"})}}

    # Erratik voltaj eklenir → ikinci kural da tetikler (eskalasyon).
    for i, v in enumerate([24.0, 4.0, 44.0, 24.0, -3.0, 49.0, 24.0, 10.0, 38.0, 24.0, 0.0, 48.0]):
        repo.insert(_reading("motor_voltage", f"2026-05-30T00:01:{i:02d}.000Z", v))
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)

    # İki satır: tur 1 (tek kural) + tur 2 (fused(2) eskalasyon).
    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 2
    rule_names = {a.rule_name for a in stored}
    assert "motor_temperature_high" in rule_names
    assert "fused(2)" in rule_names
    # Eskalasyon (limit 3 korunur): HER İKİ fingerprint de açık (cihaz temizlenmedi).
    assert repo.fetch_open_fingerprints() == {
        "device_001": {
            frozenset({"motor_temperature_high"}),
            frozenset({"motor_temperature_high", "motor_voltage_erratic"}),
        }
    }


def test_detect_once_below_threshold_writes_nothing(migrated_engine: Engine) -> None:
    """Eşik altı → hiçbir anomali yazılmaz, açık fingerprint yok."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]

    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)

    assert repo.fetch_recent_anomalies(limit=10) == []
    assert repo.fetch_open_fingerprints() == {}


def test_detect_once_failing_rule_does_not_block_others(migrated_engine: Engine) -> None:
    """Bir kural ValueError fırlatsa bile diğer kurallar çalışır + servis çökmez (spec § 8)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [
        _FailingDetector(),
        MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0),
    ]

    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)  # exception fırlamamalı

    stored = repo.fetch_recent_anomalies(limit=10)
    assert len(stored) == 1
    assert stored[0].rule_name == "motor_temperature_high"


def test_detect_once_auto_resolves_open_alert_on_clear(migrated_engine: Engine) -> None:
    """Arıza temizlenince (re-arm) cihazın açık uyarısı otomatik resolved olur (Faz 7)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]

    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)  # active uyarı yazılır
    assert [a.status for a in repo.fetch_alerts(None, limit=10)] == ["active"]

    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE telemetry SET value = 25.0 WHERE sensor = 'motor_temperature'"))
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)  # arıza temizlendi → auto-resolve

    resolved = repo.fetch_alerts(("resolved",), limit=10)
    assert len(resolved) == 1
    assert resolved[0].resolved_at is not None
    assert repo.fetch_open_fingerprints() == {}


def test_detect_once_resolves_preexisting_open_alert_on_clean_device(migrated_engine: Engine) -> None:
    """DB-tek-hakikat: clean cihazın ÖNCEDEN açık uyarısı (örn. restart öncesi) auto-resolve olur.

    In-memory 'active' guard'ı kalktı → reconciliation cihaz temizse cihazın TÜM açık uyarılarını
    resolve eder (kim açmış olursa olsun). Bu, restart orphan'ının çözümüdür (limit 2)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 25.0))  # eşik altı (temiz)
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]
    # "Önceki süreçten" kalma açık uyarı (in-memory durum taşınmadı):
    repo.insert_anomaly(
        Anomaly(device_id="device_001", rule_name="x", sensor="s", severity="warning",
                score=0.1, window_start="a", window_end="b", value=1.0, description="d"),
        "2026-05-30T00:00:00.000Z",
        "x",
    )
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)  # cihaz temiz → açık uyarı resolve
    assert [a.status for a in repo.fetch_alerts(None, limit=10)] == ["resolved"]
    assert repo.fetch_open_fingerprints() == {}


def test_detect_once_restart_persisting_fault_no_duplicate(migrated_engine: Engine) -> None:
    """Restart (in-memory durum yok) + süregelen arıza: eşleşen açık fingerprint → debounce, duplikat yok."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert(_reading("motor_temperature", "2026-05-30T00:00:00.000Z", 95.0))
    detectors: list[Detector] = [MotorTemperatureHigh(critical_threshold_c=80.0, trip_c=130.0)]
    # "Önceki süreç" arızayı zaten açmış (aynı fingerprint):
    repo.insert_anomaly(
        Anomaly(device_id="device_001", rule_name="motor_temperature_high", sensor="motor_temperature",
                severity="critical", score=0.5, window_start="a", window_end="b", value=95.0, description="d"),
        "2026-05-30T00:00:00.000Z",
        "motor_temperature_high",
    )
    _detect_once(repo, [(detectors, _BIG_WINDOW_S)], _NOW)  # soğuk başlangıç, arıza sürüyor → debounce
    assert len(repo.fetch_recent_anomalies(limit=10)) == 1  # duplikat yazılmadı

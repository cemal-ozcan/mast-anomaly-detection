"""Alert yaşam döngüsü: migration 003 + repository metotları (Faz 7 Iter 7.1, spec § 5/§ 7)."""
from __future__ import annotations

from sqlalchemy import Engine, text

from detectors.base import Anomaly
from storage.repository import TelemetryRepository

_CREATED = "2026-06-03T10:00:00.000Z"


def _anom(device: str = "device_001", rule: str = "motor_current_high") -> Anomaly:
    return Anomaly(
        device_id=device, rule_name=rule, sensor="motor_current", severity="high",
        score=0.9, window_start="2026-06-03T09:59:00.000Z", window_end="2026-06-03T10:00:00.000Z",
        value=10.0, description="test",
    )


def test_insert_anomaly_defaults_status_active(migrated_engine: Engine) -> None:
    """insert_anomaly status set etmez → DB DEFAULT 'active'; acknowledged_at/resolved_at NULL."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), _CREATED, "motor_current_high")
    with migrated_engine.connect() as conn:
        row = conn.execute(text("SELECT status, acknowledged_at, resolved_at FROM anomalies")).one()
    assert row.status == "active"
    assert row.acknowledged_at is None
    assert row.resolved_at is None


def test_acknowledge_alert(migrated_engine: Engine) -> None:
    """active→acknowledged geçişi acknowledged_at zaman damgasını yazar (P2: manuel resolve yok)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), _CREATED, "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id

    assert repo.acknowledge_alert(alert_id, "2026-06-03T10:01:00.000Z") is True
    acked = repo.fetch_alerts(("acknowledged",), limit=10)
    assert len(acked) == 1 and acked[0].acknowledged_at == "2026-06-03T10:01:00.000Z"


def test_acknowledge_resolved_alert_is_noop(migrated_engine: Engine) -> None:
    """resolved bir uyarı ack'lenemez (geçersiz geçiş → 0 satır → False).

    Kurulum: detector auto-resolve (resolve_open_alerts) ile resolved'a getir (P2: manuel resolve yok)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), _CREATED, "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id
    repo.resolve_open_alerts("device_001", "2026-06-03T10:02:00.000Z")
    assert repo.acknowledge_alert(alert_id, "2026-06-03T10:03:00.000Z") is False


def test_resolve_open_alerts_closes_all_non_resolved_for_device(migrated_engine: Engine) -> None:
    """resolve_open_alerts cihazın tüm açık (active+acknowledged) uyarılarını kapatır, resolved'a dokunmaz."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(rule="motor_current_high"), _CREATED, "motor_current_high")
    repo.insert_anomaly(_anom(rule="fused(2)"), "2026-06-03T10:00:05.000Z", "motor_current_high,vibration_elevated")
    repo.insert_anomaly(_anom(device="device_002"), _CREATED, "motor_current_high")  # başka cihaz — etkilenmemeli
    d1_first = repo.fetch_alerts(("active",), limit=10)
    repo.acknowledge_alert([a.id for a in d1_first if a.device_id == "device_001"][0],
                           "2026-06-03T10:01:00.000Z")

    closed = repo.resolve_open_alerts("device_001", "2026-06-03T10:05:00.000Z")
    assert closed == 2  # device_001'in iki açık satırı
    assert {a.device_id for a in repo.fetch_alerts(("resolved",), limit=10)} == {"device_001"}
    assert len(repo.fetch_alerts(("active",), limit=10)) == 1  # device_002 hâlâ açık


def test_fetch_alerts_status_filter_and_all(migrated_engine: Engine) -> None:
    """statuses=None tümünü; tuple verince IN filtreler; created_at DESC."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), _CREATED, "motor_current_high")
    repo.insert_anomaly(_anom(device="device_002"), "2026-06-03T10:00:05.000Z", "motor_current_high")
    repo.resolve_open_alerts("device_001", "2026-06-03T10:06:00.000Z")
    assert len(repo.fetch_alerts(None, limit=10)) == 2
    assert len(repo.fetch_alerts(("active", "acknowledged"), limit=10)) == 1
    assert len(repo.fetch_alerts(("resolved",), limit=10)) == 1


def test_fetch_open_fingerprints_groups_by_device(migrated_engine: Engine) -> None:
    """active+acknowledged uyarıların rule_set'leri cihaz başına kümelenir; resolved hariç (Iter 8.5)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(device="d1", rule="motor_current_high"), "2026-05-30T00:00:00.000Z", "motor_current_high")
    repo.insert_anomaly(_anom(device="d1", rule="fused(2)"), "2026-05-30T00:00:01.000Z", "motor_current_high,vibration_elevated")
    repo.insert_anomaly(_anom(device="d2", rule="iqr:motor_current"), "2026-05-30T00:00:02.000Z", "iqr:motor_current")
    # d2'nin uyarısını resolve et → fingerprints'te görünmemeli
    repo.resolve_open_alerts("d2", "2026-05-30T00:01:00.000Z")

    fps = repo.fetch_open_fingerprints()

    assert fps["d1"] == {frozenset({"motor_current_high"}), frozenset({"motor_current_high", "vibration_elevated"})}
    assert "d2" not in fps


def test_fetch_open_fingerprints_includes_acknowledged_and_null_safe(migrated_engine: Engine) -> None:
    """acknowledged uyarılar DAHİL; NULL rule_set (legacy satır) → boş frozenset (Iter 8.5)."""
    from storage.schema import anomalies

    repo = TelemetryRepository(migrated_engine)
    # d3: acknowledged uyarı → açık sayılır, dahil olmalı.
    repo.insert_anomaly(_anom(device="d3", rule="motor_current_high"), "2026-05-30T00:00:00.000Z", "motor_current_high")
    repo.acknowledge_alert(repo.fetch_alerts(("active",), limit=10)[-1].id, "2026-05-30T00:00:30.000Z")
    # d4: legacy NULL rule_set satırı (insert_anomaly'yi atlayıp doğrudan NULL yaz).
    with migrated_engine.begin() as conn:
        conn.execute(
            anomalies.insert().values(
                device_id="d4", rule_name="x", sensor="s", severity="warning", score=0.1,
                window_start="a", window_end="b", value=1.0, description="d",
                created_at="2026-05-30T00:00:02.000Z", status="active", rule_set=None,
            )
        )

    fps = repo.fetch_open_fingerprints()

    assert fps["d3"] == {frozenset({"motor_current_high"})}  # acknowledged dahil
    assert fps["d4"] == {frozenset()}  # NULL rule_set → boş frozenset (legacy-güvenli)

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


def test_fetch_open_alerts_groups_by_device(migrated_engine: Engine) -> None:
    """Açık (active|acknowledged) uyarılar cihaz başına liste; resolved hariç; created_at ASC;
    legacy NULL rule_set satırı da açık sayılır (cihaz-seviyesi kimlik rule_set parse etmez, Iter 8.6)."""
    from storage.schema import anomalies

    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(device="d1", rule="motor_current_high"), "2026-06-03T10:00:00.000Z", "motor_current_high")
    repo.insert_anomaly(_anom(device="d1", rule="fused(2)"), "2026-06-03T10:00:01.000Z", "motor_current_high,vibration_elevated")
    repo.insert_anomaly(_anom(device="d2"), "2026-06-03T10:00:02.000Z", "motor_current_high")
    repo.resolve_open_alerts("d2", "2026-06-03T10:01:00.000Z")  # d2 kapanır → görünmez
    # d3: legacy NULL rule_set satırı (insert_anomaly'yi atlayıp doğrudan NULL yaz) → yine de açık sayılır.
    with migrated_engine.begin() as conn:
        conn.execute(
            anomalies.insert().values(
                device_id="d3", rule_name="x", sensor="s", severity="warning", score=0.1,
                window_start="a", window_end="b", value=1.0, description="d",
                created_at="2026-06-03T10:00:03.000Z", status="active", rule_set=None,
            )
        )

    open_alerts = repo.fetch_open_alerts()
    assert set(open_alerts.keys()) == {"d1", "d3"}  # d2 resolved hariç; d3 NULL-rule_set dahil
    assert len(open_alerts["d1"]) == 2
    assert [a.created_at for a in open_alerts["d1"]] == sorted(a.created_at for a in open_alerts["d1"])  # ASC


def test_update_alert_changes_fields(migrated_engine: Engine) -> None:
    """update_alert severity/score/value/window_end/rule_set/description/status'u günceller; created_at sabit."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id

    ok = repo.update_alert(
        alert_id, rule_name="fused(2)", sensor="motor_voltage", severity="critical", score=0.9,
        value=12.5, window_end="2026-06-03T10:05:00.000Z",
        rule_set="motor_current_high,vibration_elevated", description="updated",
    )
    assert ok is True
    a = repo.fetch_alerts(None, limit=10)[0]
    assert (a.rule_name, a.sensor, a.severity, a.score, a.value, a.window_end, a.description) == (
        "fused(2)", "motor_voltage", "critical", 0.9, 12.5, "2026-06-03T10:05:00.000Z", "updated")
    assert a.created_at == "2026-06-03T10:00:00.000Z"  # created_at DOKUNULMAZ


def test_update_alert_preserves_operator_status(migrated_engine: Engine) -> None:
    """update_alert status/acknowledged_at'a DOKUNMAZ → eşzamanlı ack ezilmez (operatör-sahipli)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id
    repo.acknowledge_alert(alert_id, "2026-06-03T10:01:00.000Z")

    repo.update_alert(alert_id, rule_name="motor_current_high", sensor="motor_current",
                      severity="critical", score=0.9, value=12.5,
                      window_end="w", rule_set="motor_current_high", description="d")
    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "acknowledged" and a.acknowledged_at == "2026-06-03T10:01:00.000Z"  # ack korunur
    assert a.severity == "critical"  # ölçüm alanı yine de tazelendi


def test_reactivate_alert_only_flips_acknowledged(migrated_engine: Engine) -> None:
    """reactivate_alert yalnız acknowledged satırı active yapar (guard); active/resolved → False."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id

    assert repo.reactivate_alert(alert_id) is False  # active → guard no-op
    repo.acknowledge_alert(alert_id, "2026-06-03T10:01:00.000Z")
    assert repo.reactivate_alert(alert_id) is True   # acknowledged → active
    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "active" and a.acknowledged_at is None


def test_resolve_alert_by_id(migrated_engine: Engine) -> None:
    """resolve_alert_by_id tek satırı resolved yapar; zaten resolved → False (idempotent)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id

    assert repo.resolve_alert_by_id(alert_id, "2026-06-03T10:02:00.000Z") is True
    a = repo.fetch_alerts(None, limit=10)[0]
    assert a.status == "resolved" and a.resolved_at == "2026-06-03T10:02:00.000Z"
    assert repo.resolve_alert_by_id(alert_id, "2026-06-03T10:03:00.000Z") is False  # zaten resolved


def test_set_clean_streak(migrated_engine: Engine) -> None:
    """set_clean_streak sayacı yazar; fetch_open_alerts onu taşır (Iter 8.7)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id
    assert repo.set_clean_streak(alert_id, 2) is True
    assert repo.fetch_open_alerts()["device_001"][0].clean_streak == 2


def test_insert_anomaly_defaults_clean_streak_zero(migrated_engine: Engine) -> None:
    """insert_anomaly clean_streak set etmez → DB DEFAULT 0 (Iter 8.7)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    assert repo.fetch_open_alerts()["device_001"][0].clean_streak == 0


def test_update_alert_resets_clean_streak(migrated_engine: Engine) -> None:
    """update_alert (firing refresh) clean_streak'i 0'a çeker (Iter 8.7 anti-flap reset)."""
    repo = TelemetryRepository(migrated_engine)
    repo.insert_anomaly(_anom(), "2026-06-03T10:00:00.000Z", "motor_current_high")
    alert_id = repo.fetch_alerts(("active",), limit=10)[0].id
    repo.set_clean_streak(alert_id, 2)
    repo.update_alert(alert_id, rule_name="motor_current_high", sensor="motor_current",
                      severity="critical", score=0.9, value=12.5, window_end="w",
                      rule_set="motor_current_high", description="d")
    assert repo.fetch_open_alerts()["device_001"][0].clean_streak == 0

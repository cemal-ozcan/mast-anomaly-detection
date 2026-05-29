"""storage.schema Table + Index yapı testleri (Iter 2.2, spec § 5)."""
from __future__ import annotations


def test_telemetry_table_has_expected_columns() -> None:
    """telemetry tablosu spec § 5'teki 7 kolonu içerir, hepsi NOT NULL (id PK hariç)."""
    from storage.schema import telemetry

    assert telemetry.name == "telemetry"
    assert set(telemetry.c.keys()) == {
        "id", "device_id", "sensor", "timestamp", "state", "value", "unit"
    }
    assert telemetry.c.id.primary_key is True
    for name in ("device_id", "sensor", "timestamp", "state", "value", "unit"):
        assert telemetry.c[name].nullable is False, f"{name} NOT NULL olmalı"


def test_composite_index_defined_on_device_sensor_timestamp() -> None:
    """Composite index (device_id, sensor, timestamp) doğru ad + kolon sırasıyla tanımlı."""
    from storage.schema import telemetry

    indexes = {str(idx.name): idx for idx in telemetry.indexes}
    assert "idx_telemetry_device_sensor_ts" in indexes
    idx = indexes["idx_telemetry_device_sensor_ts"]
    assert [col.name for col in idx.columns] == ["device_id", "sensor", "timestamp"]

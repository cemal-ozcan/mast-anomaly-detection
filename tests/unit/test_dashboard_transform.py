"""dashboard.transform saf helper testleri (Faz 3, spec § 5)."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from dashboard.transform import readings_to_frame, window_to_since
from ingestion.message_parser import IngestedReading


def _reading(ts: str, value: float) -> IngestedReading:
    return IngestedReading(
        device_id="device_001", sensor="motor_current", timestamp=ts,
        state="idle", value=value, unit="A",
    )


def test_window_to_since_5min() -> None:
    now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
    assert window_to_since(now, "Son 5 dakika") == "2026-05-30T11:55:00.000Z"


def test_window_to_since_1hour() -> None:
    now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
    assert window_to_since(now, "Son 1 saat") == "2026-05-30T11:00:00.000Z"


def test_window_to_since_all_returns_none() -> None:
    assert window_to_since(datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC), "Tümü") is None


def test_window_to_since_unknown_returns_none() -> None:
    assert window_to_since(datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC), "bogus") is None


def test_window_to_since_format_matches_publisher() -> None:
    """Cutoff publisher formatında: YYYY-MM-DDTHH:MM:SS.sssZ (lexicographic karşılaştırılabilir)."""
    s = window_to_since(datetime(2026, 5, 30, 12, 0, 0, 123000, tzinfo=UTC), "Son 15 dakika")
    assert s is not None
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", s)


def test_readings_to_frame_empty() -> None:
    frame = readings_to_frame([])
    assert frame.index.name == "timestamp"
    assert list(frame.columns) == ["value"]
    assert len(frame) == 0


def test_window_to_since_naive_now_raises() -> None:
    """tz-naive now → ValueError (sessiz format bozulması yerine açık hata)."""
    import pytest

    with pytest.raises(ValueError, match="UTC-aware"):
        window_to_since(datetime(2026, 5, 30, 12, 0, 0), "Son 5 dakika")  # naive


def test_readings_to_frame_populated_preserves_order() -> None:
    readings = [
        _reading("2026-05-30T12:00:00.000Z", 1.0),
        _reading("2026-05-30T12:00:01.000Z", 2.0),
    ]
    frame = readings_to_frame(readings)
    assert frame.index.name == "timestamp"
    assert list(frame["value"]) == [1.0, 2.0]
    assert len(frame) == 2

"""dashboard.transform saf helper testleri (Faz 3, spec § 5)."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from dashboard.transform import window_to_since


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


def test_window_to_since_naive_now_raises() -> None:
    """tz-naive now → ValueError (sessiz format bozulması yerine açık hata)."""
    import pytest

    with pytest.raises(ValueError, match="UTC-aware"):
        window_to_since(datetime(2026, 5, 30, 12, 0, 0), "Son 5 dakika")  # naive


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

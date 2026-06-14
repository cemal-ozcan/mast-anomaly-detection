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

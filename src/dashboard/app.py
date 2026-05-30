"""Streamlit dashboard entry (Faz 3): streamlit run src/dashboard/app.py.

Cihaz + zaman-aralığı seçilir; 6 sensör line chart'ı st.experimental_fragment ile
2 saniyede bir otomatik yenilenir. SQLite'ı (ingestion'ın yazdığı data/telemetry.db)
read-only sorgular. Gözlem modu: hiçbir şey yazmaz.

db_path: DASHBOARD_DB_PATH env varsa o, yoksa config/ingestion.yaml db_path.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st
from sqlalchemy.exc import OperationalError

from dashboard.transform import WINDOW_OPTIONS, readings_to_frame, window_to_since
from ingestion.config import load_ingestion_config
from storage.engine import create_sqlite_engine
from storage.repository import TelemetryRepository

SIX_SENSORS = [
    "motor_current",
    "motor_voltage",
    "hydraulic_pressure",
    "motor_temperature",
    "mast_position",
    "vibration",
]


def _resolve_db_path() -> Path:
    """DASHBOARD_DB_PATH env override; yoksa ingestion.yaml db_path."""
    env = os.environ.get("DASHBOARD_DB_PATH")
    if env:
        return Path(env)
    return load_ingestion_config(Path("config/ingestion.yaml")).db_path


@st.cache_resource
def _get_repository() -> TelemetryRepository:
    """Engine + repository bir kez kurulur (her rerun'da yeniden açılmaz)."""
    engine = create_sqlite_engine(_resolve_db_path())
    return TelemetryRepository(engine)


@st.experimental_fragment(run_every="2s")
def _render_charts(repository: TelemetryRepository, device_id: str, window: str) -> None:
    """Seçili cihazın 6 sensörünü 2 kolonda çizer; her 2s otomatik yenilenir."""
    since = window_to_since(datetime.now(UTC), window)
    cols = st.columns(2)
    for i, sensor in enumerate(SIX_SENSORS):
        readings = repository.fetch_window(device_id, sensor, since)
        frame = readings_to_frame(readings)
        with cols[i % 2]:
            st.subheader(sensor)
            st.line_chart(frame, y="value")


def main() -> None:
    """Dashboard ana akışı."""
    st.set_page_config(page_title="Mast Telemetri Dashboard", layout="wide")
    st.title("Teleskopik Mast — Telemetri Dashboard")

    repository = _get_repository()
    assert isinstance(repository, TelemetryRepository)
    try:
        devices = repository.list_devices()
    except OperationalError:
        st.info(
            "Henüz veri yok — ingestion telemetry tablosunu oluşturmadı"
            " (simulator + ingestion çalışıyor mu?)"
        )
        return

    if not devices:
        st.info("Henüz veri yok — simulator + ingestion çalışıyor mu?")
        return

    device_id: str = st.sidebar.selectbox("Cihaz", devices) or devices[0]
    window: str = st.sidebar.selectbox("Zaman aralığı", list(WINDOW_OPTIONS.keys()), index=1) or list(WINDOW_OPTIONS.keys())[1]
    _render_charts(repository, device_id, window)


main()

"""Streamlit dashboard entry (Faz 3): streamlit run src/dashboard/app.py.

Cihaz + zaman-aralığı seçilir; 6 sensör line chart'ı st.experimental_fragment ile
2 saniyede bir otomatik yenilenir. SQLite'ı (ingestion'ın yazdığı data/telemetry.db)
read-only sorgular. Gözlem modu: hiçbir şey yazmaz.

db_path: DASHBOARD_DB_PATH env varsa o, yoksa config/ingestion.yaml db_path.
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# `streamlit run src/dashboard/app.py` yalnızca src/dashboard'ı sys.path'e ekler; top-level
# paketler (dashboard, ingestion, storage) için src/ kökünü ekle. Editable install .pth'i
# Python 3.11.15 hardening ile silent-skip edildiğinden bu bootstrap gerekir (env notu).
# tests/conftest.py aynı deseni pytest için kullanır.
_SRC_ROOT = Path(__file__).resolve().parent.parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

import streamlit as st  # noqa: E402
from loguru import logger  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from dashboard.transform import (  # noqa: E402
    WINDOW_OPTIONS,
    anomalies_to_frame,
    readings_to_frame,
    window_to_since,
)
from ingestion.config import load_ingestion_config  # noqa: E402
from storage.engine import create_sqlite_engine  # noqa: E402
from storage.repository import TelemetryRepository  # noqa: E402

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


@st.experimental_fragment(run_every="2s")
def _render_charts(repository: TelemetryRepository, device_id: str, window: str) -> None:
    """Seçili cihazın 6 sensörünü 2 kolonda çizer; her 2s otomatik yenilenir."""
    since = window_to_since(datetime.now(UTC), window)
    cols = st.columns(2)
    for i, sensor in enumerate(SIX_SENSORS):
        try:
            readings = repository.fetch_window(device_id, sensor, since)
        except OperationalError as e:
            logger.error("Okuma hatası device={} sensor={}: {}", device_id, sensor, e)
            with cols[i % 2]:
                st.error(f"{sensor}: okuma hatası")
            continue
        frame = readings_to_frame(readings)
        with cols[i % 2]:
            st.subheader(sensor)
            st.line_chart(frame, y="value")


def main() -> None:
    """Dashboard ana akışı."""
    st.set_page_config(page_title="Mast Telemetri Dashboard", layout="wide")
    st.title("Teleskopik Mast — Telemetri Dashboard")

    try:
        repository = _get_repository()
    except FileNotFoundError as e:
        logger.error("Yapılandırma/DB bulunamadı: {}", e)
        st.error(f"Yapılandırma/DB bulunamadı: {e} — config/ingestion.yaml var mı, ingestion çalıştı mı?")
        return

    try:
        devices = repository.list_devices()
    except OperationalError as e:
        logger.info("telemetry tablosu henüz yok: {}", e)
        st.info(
            "Henüz veri yok — ingestion telemetry tablosunu oluşturmadı"
            " (simulator + ingestion çalışıyor mu?)"
        )
        return

    if not devices:
        st.info("Henüz veri yok — simulator + ingestion çalışıyor mu?")
        return

    _render_alerts(repository)
    st.divider()

    device_id: str = st.sidebar.selectbox("Cihaz", devices) or devices[0]
    window: str = st.sidebar.selectbox("Zaman aralığı", list(WINDOW_OPTIONS.keys()), index=1) or list(WINDOW_OPTIONS.keys())[1]
    _render_charts(repository, device_id, window)


# Streamlit betiği yukarıdan aşağıya çalıştırır; __main__ guard yok.
# Bu modülü import ETME — main() import-time çalışır ve Streamlit runtime gerektirir.
main()

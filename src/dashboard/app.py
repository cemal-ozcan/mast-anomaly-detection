"""Streamlit dashboard entry (Faz 3): streamlit run src/dashboard/app.py.

Cihaz + zaman-aralığı seçilir; 6 sensör line chart'ı st.experimental_fragment ile
2 saniyede bir otomatik yenilenir. SQLite'ı (ingestion'ın yazdığı data/telemetry.db)
read-only sorgular. Gözlem modu: hiçbir şey yazmaz.

db_path: DASHBOARD_DB_PATH env varsa o, yoksa config/ingestion.yaml db_path.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
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

from alerts.lifecycle import ACKNOWLEDGED, RESOLVED, can_transition  # noqa: E402
from dashboard.transform import (  # noqa: E402
    WINDOW_OPTIONS,
    alerts_to_frame,
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


_STATUS_FILTERS: dict[str, tuple[str, ...] | None] = {
    "Açık": ("active", "acknowledged"),
    "Tümü": None,
    "active": ("active",),
    "acknowledged": ("acknowledged",),
    "resolved": ("resolved",),
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _apply_transition(fn: Callable[[int, str], bool], alert_id: int) -> None:
    """Geçiş metodunu çağırır; sonuca göre kullanıcıyı bilgilendirir (spec § 9)."""
    try:
        ok = fn(alert_id, _now_iso())
    except OperationalError as e:
        logger.error("Uyarı durumu yazılamadı: {}", e)
        st.error("Uyarı durumu güncellenemedi (DB hatası).")
        return
    if not ok:
        st.info("Uyarı durumu değişmiş olabilir — listeyi yenileyin.")


@st.experimental_fragment(run_every="5s")
def _render_alerts(repository: TelemetryRepository) -> None:
    """Filo geneli uyarı tablosunu durum kolonu + filtre ile gösterir; 5s'de bir yenilenir (spec § 8).

    SALT-GÖRÜNTÜ (auto-refresh). Yönetim (ack/resolve) butonları _render_alert_management'ta
    (main() içinde, fragment dışında — auto-rerun buton yarışını önler, S1). Gözlem modu: hiçbir
    şey yazmaz. anomalies tablosu yoksa bilgilendirir; çökmez (spec § 7/§ 9).
    """
    st.subheader("🚨 Uyarılar")
    choice = st.selectbox("Durum filtresi", list(_STATUS_FILTERS.keys()), index=0, key="alert_filter")
    statuses = _STATUS_FILTERS[choice or "Açık"]
    try:
        alerts = repository.fetch_alerts(statuses, limit=50)
    except OperationalError as e:
        logger.info("anomalies tablosu henüz yok: {}", e)
        st.info("Henüz anomali yok — detector servisi (`python -m detectors`) çalıştı mı?")
        return
    if not alerts:
        st.caption("Bu filtrede uyarı yok.")
        return
    st.dataframe(alerts_to_frame(alerts), use_container_width=True, hide_index=True)


def _render_alert_management(repository: TelemetryRepository) -> None:
    """Açık bir uyarı seçip ack/resolve eden yönetim kontrolü (main() içinde, fragment DIŞINDA, S1).

    Gözlem modu: yalnız uyarı DURUMU yazılır (telemetri değil, cihaz komutu değil). Buton tıklaması
    tam app rerun'ı tetikler → liste tazelenir.
    """
    try:
        open_alerts = repository.fetch_alerts(("active", "acknowledged"), limit=50)
    except OperationalError:
        return  # tablo yoksa _render_alerts zaten bilgilendirdi
    if not open_alerts:
        return
    options = {f"#{a.id} {a.device_id} · {a.rule_name} ({a.status})": a for a in open_alerts}
    label = st.selectbox("Uyarı yönet", list(options.keys()), key="alert_manage")
    selected = options.get(label) if label else None
    if selected is None:
        return
    cols = st.columns(2)
    if can_transition(selected.status, ACKNOWLEDGED) and cols[0].button("Gör (ack)", key="ack_btn"):
        _apply_transition(repository.acknowledge_alert, selected.id)
    if can_transition(selected.status, RESOLVED) and cols[1].button("Çöz (resolve)", key="resolve_btn"):
        _apply_transition(repository.resolve_alert, selected.id)


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
    _render_alert_management(repository)
    st.divider()

    device_id: str = st.sidebar.selectbox("Cihaz", devices) or devices[0]
    window: str = st.sidebar.selectbox("Zaman aralığı", list(WINDOW_OPTIONS.keys()), index=1) or list(WINDOW_OPTIONS.keys())[1]
    _render_charts(repository, device_id, window)


# Streamlit betiği yukarıdan aşağıya çalıştırır; __main__ guard yok.
# Bu modülü import ETME — main() import-time çalışır ve Streamlit runtime gerektirir.
main()

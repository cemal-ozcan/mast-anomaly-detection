"""Streamlit dashboard entry (Faz 8 Iter 8.2): streamlit run src/dashboard/app.py.

Tek sayfa komuta merkezi (spec § 3): KPI satırı → filo sağlık kartları → severity-stilli
uyarı akışı (cihaz-özeti varsayılan) → uyarı yönetimi → seçili cihazın 6 Altair grafiği
(anomali overlay'li). Üst blok 5s, grafikler 2s fragment; yönetim fragment DIŞI (S1).
SQLite'ı read-only sorgular; tek yazma yolu uyarı durumu geçişleri (gözlem modu).

db_path: DASHBOARD_DB_PATH env varsa o, yoksa config/ingestion.yaml db_path.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

# `streamlit run src/dashboard/app.py` yalnızca src/dashboard'ı sys.path'e ekler; top-level
# paketler (dashboard, ingestion, storage) için src/ kökünü ekle. Editable install .pth'i
# Python 3.11.15 hardening ile silent-skip edildiğinden bu bootstrap gerekir (env notu).
# tests/conftest.py aynı deseni pytest için kullanır.
_SRC_ROOT = Path(__file__).resolve().parent.parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

import altair as alt  # noqa: E402
import streamlit as st  # noqa: E402
from loguru import logger  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from alerts.lifecycle import ACKNOWLEDGED, can_transition  # noqa: E402
from alerts.models import Alert  # noqa: E402
from dashboard.charts import build_sensor_chart  # noqa: E402
from dashboard.fleet import (  # noqa: E402
    BADGE_CRITICAL,
    BADGE_OK,
    BADGE_WARNING,
    DeviceHealth,
    compute_kpis,
    derive_fleet,
)
from dashboard.transform import (  # noqa: E402
    OPEN_STATUSES,
    WINDOW_OPTIONS,
    alerts_to_frame,
    downsample_frame,
    latest_alert_per_device,
    readings_to_chart_frame,
    severity_row_style,
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

ALERTS_FETCH_LIMIT = 200  # spec § 6 — tek fetch, client-side türetim

_BADGE_LABELS = {
    BADGE_OK: "🟢 OK",
    BADGE_WARNING: "🟡 UYARI",
    BADGE_CRITICAL: "🔴 KRİTİK",
}

# Uyarı akışı görünümleri (spec § 3): cihaz özeti varsayılan; gerisi durum filtresi.
_VIEW_OPTIONS = ["Cihaz özeti", "Açık", "Tümü", "active", "acknowledged", "resolved"]


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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _apply_transition(fn: Callable[[int, str], bool], alert_id: int) -> None:
    """Geçiş metodunu çağırır; sonuca göre kullanıcıyı bilgilendirir (Faz 7 spec § 9)."""
    try:
        ok = fn(alert_id, _now_iso())
    except OperationalError as e:
        logger.error("Uyarı durumu yazılamadı: {}", e)
        st.error("Uyarı durumu güncellenemedi (DB hatası).")
        return
    if not ok:
        st.info("Uyarı durumu değişmiş olabilir — listeyi yenileyin.")


def _fetch_alerts_safe(repository: TelemetryRepository) -> tuple[list[Alert], bool]:
    """Uyarıları çeker; anomalies tablosu yoksa (boş, False) döner — üst blok degrade (spec § 9)."""
    try:
        return repository.fetch_alerts(None, ALERTS_FETCH_LIMIT), True
    except OperationalError as e:
        logger.info("anomalies tablosu henüz yok: {}", e)
        return [], False


def _filter_view(alerts: list[Alert], view: str) -> list[Alert]:
    """Uyarı akışı görünümünü tek fetch sonucundan client-side türetir (spec § 6)."""
    if view == "Cihaz özeti":
        return latest_alert_per_device(alerts)
    if view == "Açık":
        return [a for a in alerts if a.status in OPEN_STATUSES]
    if view == "Tümü":
        return alerts
    return [a for a in alerts if a.status == view]


def _render_fleet_cards(fleet_health: list[DeviceHealth]) -> None:
    """Filo sağlık kartlarını çizer (spec § 3 madde 3)."""
    if not fleet_health:
        return
    cols = st.columns(len(fleet_health))
    for col, health in zip(cols, fleet_health, strict=True):
        with col, st.container(border=True):
            st.markdown(f"**{health.device_id}** · {_BADGE_LABELS[health.badge]}")
            st.caption(f"state: {health.state}")
            lines = []
            for snap in health.snapshots:
                text = f"{snap.sensor}: {snap.value:.2f} {snap.unit}"
                # Bold renk köşeli parantezinin İÇİNDE — Streamlit'in dokümante deseni
                # (":red[**...**]"); dışarıda iç içe markdown 1.36'da kırılgan (plan review S2).
                lines.append(f":red[**{text}**]" if snap.highlighted else text)
            st.markdown("  \n".join(lines))
            if health.open_alert_count:
                st.caption(f"⚠ {health.open_alert_count} açık uyarı · {health.top_rule}")


@st.experimental_fragment(run_every="5s")
def _render_overview(repository: TelemetryRepository) -> None:
    """Üst blok: KPI satırı + filo kartları + uyarı akışı; 5s'de bir yenilenir (spec § 3).

    SALT-GÖRÜNTÜ (gözlem modu). Sorgu bütçesi: fetch_alerts + fetch_latest_readings (spec § 6).
    """
    alerts, alerts_available = _fetch_alerts_safe(repository)
    try:
        latest = repository.fetch_latest_readings()
    except OperationalError as e:
        logger.error("Son okumalar alınamadı: {}", e)
        st.error("Son okumalar alınamadı (DB hatası).")
        return
    devices = sorted({r.device_id for r in latest})
    now = datetime.now(UTC)

    kpis = compute_kpis(devices, alerts, now)
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Cihaz", kpis.device_count)
    kpi_cols[1].metric("Açık uyarı", kpis.open_alert_count)
    kpi_cols[2].metric("Kritik", kpis.critical_alert_count)
    kpi_cols[3].metric("Son tespit", kpis.last_detection)
    if not alerts_available:
        st.caption("Detector henüz çalışmadı — uyarı verisi yok (`python -m detectors`).")

    _render_fleet_cards(derive_fleet(devices, latest, alerts))

    st.subheader("🚨 Uyarılar")
    choice = st.selectbox("Görünüm", _VIEW_OPTIONS, index=0, key="alert_view")
    visible = _filter_view(alerts, choice or "Cihaz özeti")
    if not visible:
        st.caption("Bu görünümde uyarı yok.")
        return
    frame = alerts_to_frame(visible, now)
    st.dataframe(
        frame.style.apply(severity_row_style, axis=1),
        use_container_width=True,
        hide_index=True,
    )


def _render_alert_management(repository: TelemetryRepository) -> None:
    """Açık bir uyarıyı ACK eden yönetim kontrolü (main() içinde, fragment DIŞINDA, S1).

    P2 (Iter 8.5): manuel resolve YOK — çözümü detector sahiplenir (koşulun sahibi o; arıza sensörlerce
    temizlenince auto-resolve). Teknisyen yalnız ack'ler. Gözlem modu: yalnız uyarı DURUMU yazılır.
    """
    try:
        open_alerts = repository.fetch_alerts(OPEN_STATUSES, limit=50)
    except OperationalError:
        return  # tablo yoksa _render_overview zaten bilgilendirdi
    if not open_alerts:
        return
    options = {f"#{a.id} {a.device_id} · {a.rule_name} ({a.status})": a for a in open_alerts}
    label = st.selectbox("Uyarı yönet", list(options.keys()), key="alert_manage")
    selected = options.get(label) if label else None
    if selected is None:
        return
    if can_transition(selected.status, ACKNOWLEDGED) and st.button("Gör (ack)", key="ack_btn"):
        _apply_transition(repository.acknowledge_alert, selected.id)


@st.experimental_fragment(run_every="2s")
def _render_charts(repository: TelemetryRepository, device_id: str, window: str) -> None:
    """Seçili cihazın 6 sensörünü anomali overlay'li Altair grafikleriyle çizer (spec § 3/§ 5)."""
    since = window_to_since(datetime.now(UTC), window)
    alerts, _ = _fetch_alerts_safe(repository)
    device_alerts = [a for a in alerts if a.device_id == device_id]
    if since is not None:
        # Uyarı penceresi ∩ grafik zaman penceresi (lexicographic ISO karşılaştırma, spec § 6)
        device_alerts = [a for a in device_alerts if a.window_end >= since]
    cols = st.columns(2)
    for i, sensor in enumerate(SIX_SENSORS):
        try:
            readings = repository.fetch_window(device_id, sensor, since)
        except OperationalError as e:
            logger.error("Okuma hatası device={} sensor={}: {}", device_id, sensor, e)
            with cols[i % 2]:
                st.error(f"{sensor}: okuma hatası")
            continue
        frame = downsample_frame(readings_to_chart_frame(readings))
        unit = readings[-1].unit if readings else ""
        with cols[i % 2]:
            st.subheader(sensor)
            # build_sensor_chart döner LayerChart | Chart; st.altair_chart overloadu Chart
            # bekler — cast mypy'yi tatmin eder (runtime'da ikisi de Chart alt tipi).
            st.altair_chart(
                cast(alt.Chart, build_sensor_chart(frame, device_alerts, sensor, unit)),
                use_container_width=True,
                theme="streamlit",
            )


def main() -> None:
    """Dashboard ana akışı (spec § 3 sayfa yapısı)."""
    st.set_page_config(page_title="Mast Filo İzleme", layout="wide")
    st.title("Mast Filo İzleme")
    st.caption("Teleskopik mast filosu — gerçek zamanlı telemetri ve erken uyarı (gözlem modu)")

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

    _render_overview(repository)
    _render_alert_management(repository)
    st.divider()

    device_id: str = st.sidebar.selectbox("Cihaz", devices) or devices[0]
    window: str = st.sidebar.selectbox("Zaman aralığı", list(WINDOW_OPTIONS.keys()), index=1) or list(WINDOW_OPTIONS.keys())[1]
    _render_charts(repository, device_id, window)


# Streamlit betiği yukarıdan aşağıya çalıştırır; __main__ guard yok.
# Bu modülü import ETME — main() import-time çalışır ve Streamlit runtime gerektirir.
main()

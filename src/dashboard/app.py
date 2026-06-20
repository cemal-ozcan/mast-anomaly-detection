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
from datetime import UTC, datetime, timedelta
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
from dashboard.detection import catching_layer, watching_layers  # noqa: E402
from dashboard.fleet import (  # noqa: E402
    derive_fleet,
    representative_sensor,
    sensor_badge,
    sort_fleet_by_severity,
)
from dashboard.labels import device_label, sensor_label, sensor_status_label  # noqa: E402
from dashboard.overview import (  # noqa: E402
    coverage_html,
    coverage_stats,
    fleet_card_html,
    fleet_grid_html,
    hero_html,
    section_html,
    summarize_fleet,
    timeline_events,
    timeline_html,
)
from dashboard.styles import (  # noqa: E402
    APP_CSS,
    alerts_section_html,
    distance_gauge_html,
    header_html,
    layer_chips_html,
    panel_header_html,
)
from dashboard.thresholds import LevelBand, level_band  # noqa: E402
from dashboard.transform import (  # noqa: E402
    OPEN_STATUSES,
    WINDOW_OPTIONS,
    downsample_frame,
    readings_to_chart_frame,
    relative_time,
    split_alerts_by_axis,
    window_to_since,
)
from detectors.config import DetectorConfig, load_detector_config  # noqa: E402
from detectors.scoring import band_position_score  # noqa: E402
from ingestion.config import load_ingestion_config  # noqa: E402
from ingestion.message_parser import IngestedReading  # noqa: E402
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

FLEET_LABEL = "Filo Genel Bakış"  # sol-menü gezinme: filo sayfası seçimi

_DAY_S = 24 * 60 * 60
_SPARK_WINDOW_S = 60  # kart sparkline'ı: son 60s temsilci sensör (spec § 4)


def _resolve_db_path() -> Path:
    """DASHBOARD_DB_PATH env override; yoksa ingestion.yaml db_path."""
    env = os.environ.get("DASHBOARD_DB_PATH")
    if env:
        return Path(env)
    return load_ingestion_config(Path("config/ingestion.yaml")).db_path


def _resolve_detectors_config_path() -> Path:
    """DASHBOARD_DETECTORS_CONFIG env override; yoksa config/detectors.yaml."""
    return Path(os.environ.get("DASHBOARD_DETECTORS_CONFIG", "config/detectors.yaml"))


@st.cache_resource
def _get_detector_config() -> DetectorConfig | None:
    """detectors.yaml bir kez okunur (radar eşikleri için); okunamazsa None → bölgesiz grafik."""
    try:
        return load_detector_config(_resolve_detectors_config_path())
    except (FileNotFoundError, ValueError) as e:
        logger.info("detector config okunamadı (bölgesiz grafik): {}", e)
        return None


def _go_fleet() -> None:
    """Geri-dön butonu callback'i: sol-menü seçimini filoya çevirir (widget-state idiyomu)."""
    st.session_state["nav"] = FLEET_LABEL


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


def _freshness_str(latest: list[IngestedReading], now: datetime) -> str:
    """En yeni telemetrinin tazeliği ('2 sn önce'); veri yoksa '—'."""
    if not latest:
        return "—"
    newest = max(r.timestamp for r in latest)
    return relative_time(now, newest)


def _span_str(repository: TelemetryRepository, now: datetime) -> str:
    """İzleme süresi (en eski telemetriden bu yana, kabaca 'Ng Msa')."""
    try:
        earliest = repository.earliest_telemetry_timestamp()
    except OperationalError:
        return "—"
    if not earliest:
        return "—"
    try:
        start = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    secs = max(0, int((now - start).total_seconds()))
    days, rem = divmod(secs, _DAY_S)
    hours = rem // 3600
    if days:
        return f"{days}g {hours}sa"
    mins = (rem % 3600) // 60
    return f"{hours}sa {mins}dk" if hours else f"{mins} dk"


def _detections_24h(repository: TelemetryRepository, now: datetime) -> int:
    """Son 24 saatteki anomali tespiti sayısı (KPI)."""
    since = (now - timedelta(seconds=_DAY_S)).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    try:
        return repository.count_anomalies_since(since)
    except OperationalError:
        return 0


def _spark_values(
    repository: TelemetryRepository, device_id: str, sensor: str, since: str
) -> list[float]:
    """Bir cihaz+sensörün son penceredeki değerleri (kart sparkline'ı); hata→[]."""
    try:
        readings = repository.fetch_window(device_id, sensor, since)
    except OperationalError:
        return []
    return [r.value for r in readings]


@st.experimental_fragment(run_every="5s")
def _render_overview(repository: TelemetryRepository) -> None:
    """Operasyon Merkezi açılışı: hero + kapsam + sinyal-ızgara + 24s timeline (5s, salt-görüntü)."""
    alerts, alerts_available = _fetch_alerts_safe(repository)
    try:
        latest = repository.fetch_latest_readings()
    except OperationalError as e:
        logger.error("Son okumalar alınamadı: {}", e)
        st.error("Son okumalar alınamadı (DB hatası).")
        return
    devices = sorted({r.device_id for r in latest})
    now = datetime.now(UTC)

    fleet = derive_fleet(devices, latest, alerts)
    summary = summarize_fleet(fleet)
    sensor_count = len({(r.device_id, r.sensor) for r in latest})
    freshness = _freshness_str(latest, now)

    st.markdown(
        hero_html(summary, len(devices), sensor_count, freshness, _span_str(repository, now)),
        unsafe_allow_html=True,
    )
    st.markdown(
        coverage_html(coverage_stats(
            len(devices), sensor_count, len(devices) * 6, freshness,
            _detections_24h(repository, now),
        )),
        unsafe_allow_html=True,
    )
    if not alerts_available:
        st.caption("Detector henüz çalışmadı — uyarı verisi yok (`python -m detectors`).")

    st.markdown('<div class="mg-section">Mastlar — duruma göre sıralı</div>', unsafe_allow_html=True)
    since_spark = (now - timedelta(seconds=_SPARK_WINDOW_S)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    cards = []
    for h in sort_fleet_by_severity(fleet):
        sensor = representative_sensor(h)
        values = _spark_values(repository, h.device_id, sensor, since_spark)
        snap = next((s for s in h.snapshots if s.sensor == sensor), None)
        value_str = (
            f"{snap.value:.1f} {snap.unit}".strip() if (snap and h.open_alert_count) else ""
        )
        cards.append(fleet_card_html(h, values, value_str))
    st.markdown(fleet_grid_html(cards), unsafe_allow_html=True)

    st.markdown(
        section_html(
            "Son 24 saat — olay akışı",
            "Sistemin son 24 saatte yakaladığı olaylar. Bir değer anormale çıkınca uyarı açılır; "
            "değer kararlı şekilde normale dönünce 'çözüldü' olarak kapanır (çözümü sistem belirler).",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(timeline_html(timeline_events(alerts, now)), unsafe_allow_html=True)

    open_alerts = [a for a in alerts if a.status in OPEN_STATUSES]
    if open_alerts:
        faults, data_quality = split_alerts_by_axis(open_alerts)
        st.markdown('<div class="mg-section">Açık Uyarılar</div>', unsafe_allow_html=True)
        if faults:
            st.markdown(
                alerts_section_html("Arıza Uyarıları", faults, now, ""), unsafe_allow_html=True
            )
        if data_quality:
            st.markdown(
                alerts_section_html("Veri Kalitesi / Sensör Sağlığı", data_quality, now, ""),
                unsafe_allow_html=True,
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


def _value_str(value: float | None, unit: str) -> str:
    """Güncel değeri okunur biçimde formatlar (yoksa '—'); küçük değerlerde basamak kaybetme.

    Büyüklüğe uyarlı: ≥100 → 0 basamak (mast_position 6000), ≥10 → 1 (sıcaklık/voltaj),
    <10 → 2 (titreşim 0.12 g, akım 8.30 A).
    """
    if value is None:
        return "—"
    mag = abs(value)
    decimals = 0 if mag >= 100 else (1 if mag >= 10 else 2)
    return f"{value:.{decimals}f} {unit}".strip()


def _meta_str(band: LevelBand | None, unit: str) -> str:
    """Panel meta satırı: seviye-bandı varsa eşikleri yaz; yoksa boş (sinyali çizgi+durum taşır)."""
    if band is None:
        return ""
    return f"Uyarı {band.warn:g} · Kritik {band.trip:g} {unit}".strip()


def _sensor_alert(device_alerts: list[Alert], sensor: str) -> Alert | None:
    """Bu sensöre ait en yüksek severity açık uyarı (yoksa None)."""
    matches = [a for a in device_alerts if a.sensor == sensor and a.status in OPEN_STATUSES]
    if not matches:
        return None
    rank = {"critical": 3, "high": 2, "warning": 1}
    return max(matches, key=lambda a: rank.get(a.severity, 0))


@st.experimental_fragment(run_every="2s")
def _render_device_detail(
    repository: TelemetryRepository, device_id: str, window: str,
    config: DetectorConfig | None,
) -> None:
    """Seçili cihazın 6 sensörünü radar paneli (durum + eşik-bölgeli grafik) olarak çizer (spec § 3)."""
    since = window_to_since(datetime.now(UTC), window)
    alerts, _ = _fetch_alerts_safe(repository)
    device_alerts = [a for a in alerts if a.device_id == device_id]
    if since is not None:
        # Uyarı penceresi ∩ grafik zaman penceresi (lexicographic ISO karşılaştırma, spec § 6)
        device_alerts = [a for a in device_alerts if a.window_end >= since]
    # Her sensör tam-genişlik bordürlü satır: solda durum, sağda geniş grafik (doğal hizalama).
    for sensor in SIX_SENSORS:
        try:
            readings = repository.fetch_window(device_id, sensor, since)
        except OperationalError as e:
            logger.error("Okuma hatası device={} sensor={}: {}", device_id, sensor, e)
            st.error(f"{sensor_label(sensor)}: okuma hatası")
            continue
        frame = downsample_frame(readings_to_chart_frame(readings))
        unit = readings[-1].unit if readings else ""
        last_val = readings[-1].value if readings else None
        badge = sensor_badge(device_alerts, sensor)
        band = level_band(config, sensor)
        alert = _sensor_alert(device_alerts, sensor)
        caught = catching_layer(alert.rule_name) if alert else None
        score = alert.score if alert else None
        watching = watching_layers(config, sensor)
        with st.container(border=True):
            left, right = st.columns([2, 5])
            with left:
                st.markdown(
                    panel_header_html(
                        sensor_label(sensor), sensor_status_label(badge), badge,
                        _value_str(last_val, unit), _meta_str(band, unit),
                    ),
                    unsafe_allow_html=True,
                )
                chips = layer_chips_html(watching, caught, score)
                if chips:
                    st.markdown(chips, unsafe_allow_html=True)
                if band is not None:
                    raw = score if score is not None else (
                        band_position_score(last_val, band.warn, band.trip)
                        if last_val is not None
                        else 0.0
                    )
                    st.markdown(
                        distance_gauge_html(round(raw * 100), badge), unsafe_allow_html=True
                    )
            with right:
                # build_sensor_chart döner LayerChart | Chart; st.altair_chart overloadu Chart
                # bekler — cast mypy'yi tatmin eder (runtime'da ikisi de Chart alt tipi).
                st.altair_chart(
                    cast(
                        alt.Chart,
                        build_sensor_chart(frame, device_alerts, sensor, unit, band=band),
                    ),
                    use_container_width=True,
                    theme=None,
                )


def main() -> None:
    """Dashboard ana akışı (spec § 3 sayfa yapısı)."""
    st.set_page_config(
        page_title="Mast İzleme", layout="wide", initial_sidebar_state="expanded"
    )
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(header_html(datetime.now(UTC).strftime("%H:%M:%S")), unsafe_allow_html=True)

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

    # Filo kartına tıklanınca ?dev=... ile gelir → sol-menü seçimini o cihaza çevir (drill-down).
    dev_param = st.query_params.get("dev")
    if dev_param and dev_param in devices:
        st.session_state["nav"] = device_label(dev_param)
        st.query_params.clear()

    config = _get_detector_config()
    nav_options = [FLEET_LABEL] + [device_label(d) for d in devices]
    label_to_device = {device_label(d): d for d in devices}
    # Gezinme dar sidebar'da (cihaz erişimi solda kalır).
    choice = st.sidebar.selectbox(
        "Sayfa", nav_options, key="nav", label_visibility="collapsed"
    )

    if not choice or choice == FLEET_LABEL:
        _render_overview(repository)
        _render_alert_management(repository)
        return

    device_id = label_to_device.get(choice, devices[0])
    st.sidebar.button("← Filoya dön", on_click=_go_fleet, key="back_btn")
    window = (
        st.sidebar.selectbox("Zaman aralığı", list(WINDOW_OPTIONS.keys()), index=1, key="win")
        or list(WINDOW_OPTIONS.keys())[1]
    )
    st.markdown(
        f'<div class="mg-section">{device_label(device_id)} · Sensör Durumu</div>',
        unsafe_allow_html=True,
    )
    _render_device_detail(repository, device_id, window, config)


# Streamlit betiği yukarıdan aşağıya çalıştırır; __main__ guard yok.
# Bu modülü import ETME — main() import-time çalışır ve Streamlit runtime gerektirir.
main()

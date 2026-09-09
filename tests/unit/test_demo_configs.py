"""Demo config'leri parse + içerik doğrular (Faz 8 Iter 8.1, spec § 9)."""
from __future__ import annotations

from pathlib import Path

from detectors.config import load_detector_config
from simulator.config import load_devices

_DEVICES_DEMO = Path("config/devices.demo.yaml")
_DETECTORS_DEMO = Path("config/detectors.demo.yaml")


def test_devices_demo_has_clean_and_three_faults() -> None:
    """6 cihaz: device_001 temiz (senaryosuz) + mechanical_wear + hydraulic_leak + electrical_fault + temperature_overshoot + sensor_fault."""
    devices = load_devices(_DEVICES_DEMO)
    assert len(devices) == 6
    by_id = {d.id: d for d in devices}
    assert by_id["device_001"].scenarios == []  # temiz kontrol
    scenario_names = {s.name for d in devices for s in d.scenarios}
    assert {"mechanical_wear", "hydraulic_leak", "electrical_fault", "temperature_overshoot", "sensor_fault"} <= scenario_names


def test_devices_demo_faults_are_persistent() -> None:
    """Tüm arızalar KALICI (uzun süreli): demo ne zaman başlatılırsa başlatılsın anomaliler
    ekranda kalır → sunum zamanlamasına bağımlı değil. Her arıza demo-üstü süreli (>= 3600s)."""
    devices = load_devices(_DEVICES_DEMO)
    durations = [s.duration_s for d in devices for s in d.scenarios]
    assert durations and all(dur >= 3600 for dur in durations), f"kalıcı olmayan arıza var: {durations}"


def test_devices_demo_fast_onset() -> None:
    """Arızalar demo-zamanında başlar (onset <= 180s) — 15-dk demoya sığsın."""
    devices = load_devices(_DEVICES_DEMO)
    onsets = [s.start_after_s for d in devices for s in d.scenarios]
    assert onsets and max(onsets) <= 180, f"geç onset: {onsets}"


def test_detectors_demo_reduced_baseline_and_rules_present() -> None:
    """detectors.demo: istatistik baseline_window_s < 3600 (demo'da canlı tetiklensin) + kural seti dolu."""
    config = load_detector_config(_DETECTORS_DEMO)
    assert config.statistical is not None
    assert config.statistical.baseline_window_s < 3600
    assert len(config.rules) >= 5  # üretim kural seti korunur

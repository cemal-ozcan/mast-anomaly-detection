"""YAML konfigürasyon yükleyicisi. Iterasyon 1: minimum şema."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MQTTConfig:
    host: str
    port: int
    client_id_prefix: str
    keepalive: int
    telemetry_prefix: str
    qos: int


@dataclass(frozen=True)
class SensorConfig:
    name: str
    unit: str
    baseline: float
    noise_std: float


class DeviceState(StrEnum):
    IDLE = "idle"
    RAISING = "raising"
    HOLDING = "holding"
    LOWERING = "lowering"


@dataclass(frozen=True)
class StateDurations:
    idle: tuple[float, float]      # (min_s, max_s)
    raising: tuple[float, float]
    holding: tuple[float, float]
    lowering: tuple[float, float]


@dataclass(frozen=True)
class ScenarioWindow:
    """Bir senaryo penceresi: kayıt anahtarı + zaman aralığı + parametreler.

    `start_after_s` ve `duration_s` cihazın spawn anından itibaren sayılır
    (engine_boot_at, spec § 5). `params` immutable bir Mapping olarak saklanır.
    """

    name: str  # SCENARIO_REGISTRY key
    start_after_s: float
    duration_s: float
    params: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceConfig:
    id: str
    type: str
    sensors: list[SensorConfig]
    state_durations: StateDurations
    target_height_mm: float
    seed: int | None = None
    scenarios: list[ScenarioWindow] = field(default_factory=list)


@dataclass(frozen=True)
class EngineConfig:
    tick_hz: float
    log_level: str


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config dosyası bulunamadı: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse hatası ({path}): {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"Beklenen sözlük, alınan {type(data).__name__} ({path})")
    return data


def load_mqtt_config(path: Path) -> MQTTConfig:
    """MQTT broker yapılandırmasını YAML dosyasından yükle.

    Args:
        path: mqtt.yaml dosyasının yolu.

    Returns:
        Broker, topic prefix'leri ve QoS bilgilerini içeren MQTTConfig.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: YAML bozuksa veya şema geçersizse.
    """
    data = _read_yaml(path)
    try:
        broker = data["broker"]
        topics = data["topics"]
        qos = data["qos"]
        return MQTTConfig(
            host=str(broker["host"]),
            port=int(broker["port"]),
            client_id_prefix=str(broker["client_id_prefix"]),
            keepalive=int(broker["keepalive"]),
            telemetry_prefix=str(topics["telemetry_prefix"]),
            qos=int(qos["telemetry"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"MQTT config geçersiz ({path}): {e}") from e


def load_devices(path: Path) -> list[DeviceConfig]:
    """Cihaz yapılandırmalarını YAML dosyasından yükle.

    Args:
        path: devices.yaml dosyasının yolu.

    Returns:
        DeviceConfig listesi.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: YAML bozuksa veya şema geçersizse (eksik state_durations,
            target_height_mm vb.).
    """
    data = _read_yaml(path)
    try:
        device_dicts = data["devices"]
        if not isinstance(device_dicts, list):
            raise ValueError("'devices' bir liste olmalı")
        devices: list[DeviceConfig] = []
        for d in device_dicts:
            sensors = [
                SensorConfig(
                    name=str(s["name"]),
                    unit=str(s["unit"]),
                    baseline=float(s["baseline"]),
                    noise_std=float(s["noise_std"]),
                )
                for s in d["sensors"]
            ]
            sd = d["state_durations"]
            state_durations = StateDurations(
                idle=(float(sd["idle"][0]), float(sd["idle"][1])),
                raising=(float(sd["raising"][0]), float(sd["raising"][1])),
                holding=(float(sd["holding"][0]), float(sd["holding"][1])),
                lowering=(float(sd["lowering"][0]), float(sd["lowering"][1])),
            )
            scenarios_raw = d.get("scenarios", []) or []
            scenarios: list[ScenarioWindow] = []
            for s in scenarios_raw:
                scenarios.append(
                    ScenarioWindow(
                        name=str(s["name"]),
                        start_after_s=float(s["start_after_s"]),
                        duration_s=float(s["duration_s"]),
                        params=dict(s.get("params") or {}),
                    )
                )
            devices.append(
                DeviceConfig(
                    id=str(d["id"]),
                    type=str(d["type"]),
                    sensors=sensors,
                    state_durations=state_durations,
                    target_height_mm=float(d["target_height_mm"]),
                    seed=int(d["seed"]) if "seed" in d else None,
                    scenarios=scenarios,
                )
            )
        return devices
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Devices config geçersiz ({path}): {e}") from e


def load_engine_config(path: Path) -> EngineConfig:
    """Simülatör motor yapılandırmasını YAML dosyasından yükle.

    Args:
        path: engine.yaml dosyasının yolu.

    Returns:
        Tick frekansı (Hz) ve log seviyesini içeren EngineConfig.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: YAML bozuksa veya şema geçersizse.
    """
    data = _read_yaml(path)
    try:
        engine = data["engine"]
        return EngineConfig(
            tick_hz=float(engine["tick_hz"]),
            log_level=str(engine["log_level"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Engine config geçersiz ({path}): {e}") from e

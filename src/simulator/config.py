"""YAML konfigürasyon yükleyicisi. Iterasyon 1: minimum şema."""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class DeviceConfig:
    id: str
    type: str
    sensors: list[SensorConfig]


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
            devices.append(
                DeviceConfig(
                    id=str(d["id"]),
                    type=str(d["type"]),
                    sensors=sensors,
                )
            )
        return devices
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Devices config geçersiz ({path}): {e}") from e


def load_engine_config(path: Path) -> EngineConfig:
    data = _read_yaml(path)
    try:
        engine = data["engine"]
        return EngineConfig(
            tick_hz=float(engine["tick_hz"]),
            log_level=str(engine["log_level"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Engine config geçersiz ({path}): {e}") from e

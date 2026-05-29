"""MQTT mesaj payload'ı → IngestedReading parse (spec § 5)."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestedReading:
    """MQTT mesajından parse edilmiş tek bir telemetri okuması.

    Spec § 5: Faz 1 publisher'ın TelemetryReading dataclass'ı ile contract
    uyumlu, ancak ham (timestamp str, state str — datetime/enum parse YAGNI;
    detector katmanı (Faz 4+) ihtiyaç duyarsa parse eder).

    Fields:
        device_id: Cihaz kimliği (`telemetry/{device_id}/...` topic'inden).
        sensor: Sensör adı (`motor_current`, `motor_voltage`, vb.).
        timestamp: ISO 8601 ms UTC string (`YYYY-MM-DDTHH:MM:SS.sssZ`).
        state: Cihaz state'i (`idle`/`raising`/`holding`/`lowering`).
        value: Sensör değeri (float).
        unit: Birim string'i (`A`, `V`, `bar`, vb.).
    """

    device_id: str
    sensor: str
    timestamp: str
    state: str
    value: float
    unit: str


def parse_message(payload: bytes) -> IngestedReading:
    """MQTT mesaj payload'ını IngestedReading'e parse eder.

    Args:
        payload: paho-mqtt mesajının ham bytes payload'ı (UTF-8 JSON beklenir).

    Returns:
        IngestedReading instance'ı.

    Raises:
        json.JSONDecodeError: Payload geçerli JSON değilse.
        KeyError: Beklenen field eksikse (device_id, timestamp, state, sensor,
            value, unit).
        ValueError: Value alanı float'a dönüşemiyorsa.
        TypeError: Bir field yanlış type'ta (örn. device_id list).
    """
    data = json.loads(payload.decode("utf-8"))
    return IngestedReading(
        device_id=str(data["device_id"]),
        sensor=str(data["sensor"]),
        timestamp=str(data["timestamp"]),
        state=str(data["state"]),
        value=float(data["value"]),
        unit=str(data["unit"]),
    )

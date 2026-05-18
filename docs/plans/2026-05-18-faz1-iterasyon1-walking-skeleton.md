# Faz 1 — Iterasyon 1: Walking Skeleton — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tek motor_current sensörünün 1 Hz frekansla MQTT'ye yayın yaptığı, çökmeyen, test edilebilir en küçük yaşayan simulator parçasını üretmek.

**Architecture:** Iterasyon 1 minimal kapsam: tek sensör (`MotorCurrentSensor`), tek cihaz, state machine YOK, senaryo YOK. Sensör `baseline + Gauss(0, noise_std)` üretir, publisher JSON payload'u QoS=1 ile broker'a basar, engine 1 Hz blocking loop. `DeviceRuntimeState` ve `BaseSensor` ABC Iterasyon 2'de gelecek — bu iterasyonda yok.

**Tech Stack:** Python 3.11+ (type hints zorunlu, mypy strict), paho-mqtt 2.1, PyYAML, Loguru, pytest + pytest-cov. Mosquitto broker lokal'de çalışıyor olmalı (`brew install mosquitto && brew services start mosquitto` macOS için).

**Referans:** `docs/specs/2026-05-18-faz1-simulator-design.md` § 3 Iterasyon 1, § 7 MQTT şeması, § 11 hata yönetimi.

---

## Önkoşul: Geliştirme Ortamı

Henüz yapılmadıysa, kullanıcı terminalinde bir kerelik:

```bash
cd /Users/cemalozcan/Desktop/mast-anomaly-detection
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Mosquitto kontrolü:
```bash
brew services list | grep mosquitto      # macOS
# yoksa: brew install mosquitto && brew services start mosquitto
```

Bu plan tüm pytest komutlarının `.venv` aktif iken çalıştırıldığını varsayar.

---

## Dosya Yapısı (Iterasyon 1 sonunda)

```
src/simulator/
├── __init__.py                       # boş (paket marker)
├── __main__.py                       # python -m simulator entry
├── config.py                         # YAML loader + dataclass'lar
├── publisher.py                      # MQTTPublisher
├── engine.py                         # 1 Hz loop
└── sensors/
    ├── __init__.py                   # boş
    └── motor_current.py              # MotorCurrentSensor

tests/
├── __init__.py
└── unit/
    ├── __init__.py
    ├── test_config.py
    ├── test_motor_current_sensor.py
    ├── test_mqtt_publisher.py
    └── test_engine.py

config/
├── mqtt.yaml.example                 # mevcut, gözden geçirilecek
├── devices.yaml.example              # mevcut, Iterasyon 1 için sadeleşecek
└── simulator.yaml.example            # YENİ

.gitignore                            # config/*.yaml ignore (example hariç) eklenecek
```

---

## Task 1: .gitignore + paket marker'lar + boş kabuk ✅ TAMAMLANDI (commit `2510b34`)

**Files:**
- Modify: `.gitignore` (sonuna ekleme)
- Create: `src/simulator/__init__.py`
- Create: `src/simulator/sensors/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`

- [x] **Step 1.1: `.gitignore`'a config dosyalarını ekle**

`.gitignore` dosyasının sonuna ekle:

```gitignore

# Local config (gerçek dosyalar; örnekler commitlenir)
config/*.yaml
!config/*.yaml.example
```

- [x] **Step 1.2: Paket marker dosyalarını oluştur**

Aşağıdaki dört dosyayı **boş** olarak oluştur:
- `src/simulator/__init__.py`
- `src/simulator/sensors/__init__.py`
- `tests/__init__.py`
- `tests/unit/__init__.py`

- [x] **Step 1.3: Commit**

```bash
git add .gitignore src/simulator/__init__.py src/simulator/sensors/__init__.py tests/__init__.py tests/unit/__init__.py
git commit -m "chore: scaffold simulator package and test tree

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Config Loader (TDD) ✅ TAMAMLANDI (commit `689118c` + fix `bbeeca1`)

Iterasyon 1'in minimum config sınıfları: `MQTTConfig`, `SensorConfig`, `DeviceConfig`, `EngineConfig`. Spec § 5'teki tam dataclass'ların bir alt kümesi — `StateDurations`, `ScenarioWindow`, `target_height_mm`, `seed` Iterasyon 2-4'te eklenir.

**Files:**
- Create: `src/simulator/config.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/fixtures/mqtt_minimal.yaml`
- Create: `tests/fixtures/devices_minimal.yaml`
- Create: `tests/fixtures/simulator_minimal.yaml`

- [x] **Step 2.1: Test fixture'larını oluştur**

`tests/fixtures/mqtt_minimal.yaml`:
```yaml
broker:
  host: localhost
  port: 1883
  client_id_prefix: mast-anomaly
  keepalive: 60
topics:
  telemetry_prefix: telemetry
qos:
  telemetry: 1
```

`tests/fixtures/devices_minimal.yaml`:
```yaml
devices:
  - id: device_001
    type: telescopic_mast_v1
    sensors:
      - name: motor_current
        unit: A
        baseline: 0.5
        noise_std: 0.1
```

`tests/fixtures/simulator_minimal.yaml`:
```yaml
engine:
  tick_hz: 1.0
  log_level: INFO
```

- [x] **Step 2.2: Başarısız testi yaz**

`tests/unit/test_config.py`:
```python
from pathlib import Path

import pytest

from src.simulator.config import (
    DeviceConfig,
    EngineConfig,
    MQTTConfig,
    SensorConfig,
    load_devices,
    load_engine_config,
    load_mqtt_config,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_load_mqtt_config() -> None:
    cfg = load_mqtt_config(FIXTURES / "mqtt_minimal.yaml")
    assert isinstance(cfg, MQTTConfig)
    assert cfg.host == "localhost"
    assert cfg.port == 1883
    assert cfg.client_id_prefix == "mast-anomaly"
    assert cfg.keepalive == 60
    assert cfg.telemetry_prefix == "telemetry"
    assert cfg.qos == 1


def test_load_devices_returns_list_of_device_configs() -> None:
    devices = load_devices(FIXTURES / "devices_minimal.yaml")
    assert len(devices) == 1
    device = devices[0]
    assert isinstance(device, DeviceConfig)
    assert device.id == "device_001"
    assert device.type == "telescopic_mast_v1"
    assert len(device.sensors) == 1
    sensor = device.sensors[0]
    assert isinstance(sensor, SensorConfig)
    assert sensor.name == "motor_current"
    assert sensor.unit == "A"
    assert sensor.baseline == 0.5
    assert sensor.noise_std == 0.1


def test_load_engine_config() -> None:
    cfg = load_engine_config(FIXTURES / "simulator_minimal.yaml")
    assert isinstance(cfg, EngineConfig)
    assert cfg.tick_hz == 1.0
    assert cfg.log_level == "INFO"


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_mqtt_config(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises_value_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("broker:\n  host: localhost\n  port: not_a_number\n")
    with pytest.raises(ValueError):
        load_mqtt_config(bad)
```

- [x] **Step 2.3: Testi başarısız olarak çalıştır**

```bash
pytest tests/unit/test_config.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'src.simulator.config'` veya `ImportError`.

- [x] **Step 2.4: `config.py` implementasyonunu yaz**

`src/simulator/config.py`:
```python
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
```

- [x] **Step 2.5: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_config.py -v
```
Beklenen: 5 test PASS.

- [x] **Step 2.6: Commit**

```bash
git add src/simulator/config.py tests/unit/test_config.py tests/fixtures/
git commit -m "feat(simulator): add YAML config loader with strict validation

Iterasyon 1 minimum scope: MQTTConfig, SensorConfig, DeviceConfig,
EngineConfig dataclass'ları + load_* fonksiyonları. Test fixture'lar
tests/fixtures altında.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: MotorCurrentSensor (TDD) ✅ TAMAMLANDI (commit `d4eccc1`)

Iterasyon 1 sözleşmesi minimal: sensör `sample() -> float` döndürür. `BaseSensor` ABC ve `compute(runtime, position)` Iterasyon 2'de eklenecek; bu iterasyonda DeviceRuntimeState yok.

**Files:**
- Create: `src/simulator/sensors/motor_current.py`
- Create: `tests/unit/test_motor_current_sensor.py`

- [x] **Step 3.1: Başarısız testi yaz**

`tests/unit/test_motor_current_sensor.py`:
```python
import random
import statistics

import pytest

from src.simulator.config import SensorConfig
from src.simulator.sensors.motor_current import MotorCurrentSensor


def _config(baseline: float = 0.5, noise_std: float = 0.1) -> SensorConfig:
    return SensorConfig(
        name="motor_current",
        unit="A",
        baseline=baseline,
        noise_std=noise_std,
    )


def test_sample_is_close_to_baseline_for_zero_noise() -> None:
    sensor = MotorCurrentSensor(_config(baseline=0.5, noise_std=0.0), random.Random(42))
    assert sensor.sample() == pytest.approx(0.5)


def test_sample_distribution_matches_gaussian_parameters() -> None:
    rng = random.Random(42)
    sensor = MotorCurrentSensor(_config(baseline=0.5, noise_std=0.1), rng)
    samples = [sensor.sample() for _ in range(2000)]
    mean = statistics.fmean(samples)
    stdev = statistics.stdev(samples)
    assert abs(mean - 0.5) < 0.02
    assert abs(stdev - 0.1) < 0.02


def test_deterministic_with_same_seed() -> None:
    s1 = MotorCurrentSensor(_config(), random.Random(123))
    s2 = MotorCurrentSensor(_config(), random.Random(123))
    assert [s1.sample() for _ in range(50)] == [s2.sample() for _ in range(50)]


def test_rejects_wrong_sensor_name() -> None:
    bad = SensorConfig(name="hydraulic_pressure", unit="bar", baseline=10.0, noise_std=2.0)
    with pytest.raises(ValueError, match="motor_current"):
        MotorCurrentSensor(bad, random.Random())
```

- [x] **Step 3.2: Testi başarısız çalıştır**

```bash
pytest tests/unit/test_motor_current_sensor.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'src.simulator.sensors.motor_current'`.

- [x] **Step 3.3: Sensör implementasyonunu yaz**

`src/simulator/sensors/motor_current.py`:
```python
"""Iterasyon 1: Minimal motor akımı sensörü. Sabit baseline + Gauss gürültü."""
from __future__ import annotations

import random

from src.simulator.config import SensorConfig


class MotorCurrentSensor:
    """Motor akımı (A) ölçer. Iterasyon 1'de state machine yok — sabit baseline."""

    def __init__(self, config: SensorConfig, rng: random.Random) -> None:
        if config.name != "motor_current":
            raise ValueError(
                f"MotorCurrentSensor sensör adı 'motor_current' bekler, alınan: {config.name!r}"
            )
        self.config = config
        self._rng = rng

    def sample(self) -> float:
        """Bu tick için (baseline + Gauss gürültü) değerini döndür."""
        return self.config.baseline + self._rng.gauss(0.0, self.config.noise_std)
```

- [x] **Step 3.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_motor_current_sensor.py -v
```
Beklenen: 4 test PASS.

- [x] **Step 3.5: Commit**

```bash
git add src/simulator/sensors/motor_current.py tests/unit/test_motor_current_sensor.py
git commit -m "feat(sensors): add MotorCurrentSensor with Gaussian noise

Iterasyon 1 minimal sözleşmesi: sample() -> float. BaseSensor ABC
ve compute(runtime, position) Iterasyon 2'de eklenecek.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: MQTTPublisher (TDD, paho mock'lu) ✅ TAMAMLANDI (commit `bc9fd30`)

Spec § 7 payload + topic + `_now_iso()` formatı. Test için paho-mqtt client'ı `unittest.mock.MagicMock` ile değiştiriyoruz — gerçek broker bağlantısı testlerde yok (CI flakiness'ı önlemek için).

**Files:**
- Create: `src/simulator/publisher.py`
- Create: `tests/unit/test_mqtt_publisher.py`

- [x] **Step 4.1: Başarısız testi yaz**

`tests/unit/test_mqtt_publisher.py`:
```python
import json
import re
from unittest.mock import MagicMock

import pytest

from src.simulator.config import MQTTConfig
from src.simulator.publisher import MQTTPublisher, _now_iso


def _config(qos: int = 1) -> MQTTConfig:
    return MQTTConfig(
        host="localhost",
        port=1883,
        client_id_prefix="test",
        keepalive=60,
        telemetry_prefix="telemetry",
        qos=qos,
    )


def test_now_iso_format() -> None:
    ts = _now_iso()
    # 2026-05-18T15:30:00.123Z formatı
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts)


def test_connect_calls_paho_connect_and_loop_start() -> None:
    mock_client = MagicMock()
    pub = MQTTPublisher(_config(), client=mock_client)
    pub.connect()
    mock_client.connect.assert_called_once_with("localhost", 1883, 60)
    mock_client.loop_start.assert_called_once()


def test_publish_reading_emits_correct_topic_and_payload() -> None:
    mock_client = MagicMock()
    pub = MQTTPublisher(_config(qos=1), client=mock_client)
    pub.publish_reading(
        device_id="device_001",
        sensor="motor_current",
        value=8.7,
        unit="A",
        state="idle",
    )
    mock_client.publish.assert_called_once()
    args, kwargs = mock_client.publish.call_args
    topic = args[0] if args else kwargs["topic"]
    payload_str = args[1] if len(args) > 1 else kwargs["payload"]
    qos = kwargs.get("qos") if "qos" in kwargs else (args[2] if len(args) > 2 else None)

    assert topic == "telemetry/device_001/motor_current"
    assert qos == 1
    payload = json.loads(payload_str)
    assert payload["device_id"] == "device_001"
    assert payload["sensor"] == "motor_current"
    assert payload["value"] == 8.7
    assert payload["unit"] == "A"
    assert payload["state"] == "idle"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", payload["timestamp"])


def test_close_stops_loop_and_disconnects() -> None:
    mock_client = MagicMock()
    pub = MQTTPublisher(_config(), client=mock_client)
    pub.connect()
    pub.close()
    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()


def test_close_is_safe_without_connect() -> None:
    mock_client = MagicMock()
    pub = MQTTPublisher(_config(), client=mock_client)
    pub.close()  # Bağlanmamışken close() patlamamalı
    mock_client.loop_stop.assert_not_called()
    mock_client.disconnect.assert_not_called()
```

- [x] **Step 4.2: Testi başarısız çalıştır**

```bash
pytest tests/unit/test_mqtt_publisher.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'src.simulator.publisher'`.

- [x] **Step 4.3: Publisher implementasyonunu yaz**

`src/simulator/publisher.py`:
```python
"""MQTT yayıncı — spec § 7 topic + payload sözleşmesi."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
from loguru import logger

from src.simulator.config import MQTTConfig


def _now_iso() -> str:
    """UTC ISO 8601, milisaniye çözünürlüklü, Z suffix.

    Format: YYYY-MM-DDTHH:MM:SS.sssZ (spec § 7).
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class MQTTPublisher:
    """paho-mqtt thin wrapper. Tek topic şeması: telemetry/{device_id}/{sensor}."""

    def __init__(self, config: MQTTConfig, client: Any | None = None) -> None:
        self.config = config
        self._client = client or mqtt.Client(client_id=f"{config.client_id_prefix}-publisher")
        self._connected = False

    def connect(self) -> None:
        logger.info("MQTT bağlanılıyor: {}:{}", self.config.host, self.config.port)
        self._client.connect(self.config.host, self.config.port, self.config.keepalive)
        self._client.loop_start()
        self._connected = True

    def publish_reading(
        self,
        device_id: str,
        sensor: str,
        value: float,
        unit: str,
        state: str = "idle",
    ) -> None:
        payload = {
            "device_id": device_id,
            "timestamp": _now_iso(),
            "state": state,
            "sensor": sensor,
            "value": value,
            "unit": unit,
        }
        topic = f"{self.config.telemetry_prefix}/{device_id}/{sensor}"
        self._client.publish(topic, json.dumps(payload), qos=self.config.qos)

    def close(self) -> None:
        if not self._connected:
            return
        logger.info("MQTT bağlantısı kapatılıyor")
        self._client.loop_stop()
        self._client.disconnect()
        self._connected = False
```

- [x] **Step 4.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_mqtt_publisher.py -v
```
Beklenen: 5 test PASS.

- [x] **Step 4.5: Commit**

```bash
git add src/simulator/publisher.py tests/unit/test_mqtt_publisher.py
git commit -m "feat(simulator): add MQTTPublisher with spec § 7 payload schema

Topic: telemetry/{device_id}/{sensor}. Payload JSON: device_id,
timestamp (UTC ISO 8601 + Z), state, sensor, value, unit. _now_iso()
yardımcısı tek üretim kaynağı. paho-mqtt mock'lanabilir client
parametresi ile test edilebilir.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Engine Loop (TDD) ✅ TAMAMLANDI (commit `31a5ab0`)

Iterasyon 1 engine: tek cihaz + tek sensör + tek publisher. Sonsuz döngü `stop` event'iyle kırılır (SIGINT/SIGTERM handler). Test edebilmek için döngü `max_iterations` parametresi alır — testlerde sınırlı, prod'da None.

**Files:**
- Create: `src/simulator/engine.py`
- Create: `tests/unit/test_engine.py`

- [x] **Step 5.1: Başarısız testi yaz**

`tests/unit/test_engine.py`:
```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.simulator.engine import run

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_run_publishes_configured_iteration_count(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_publisher = MagicMock()
    captured: dict[str, object] = {}

    def fake_publisher_factory(config: object) -> MagicMock:
        captured["config"] = config
        return mock_publisher

    monkeypatch.setattr("src.simulator.engine._make_publisher", fake_publisher_factory)
    monkeypatch.setattr("src.simulator.engine.time.sleep", lambda _: None)

    run(
        mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
        devices_path=FIXTURES / "devices_minimal.yaml",
        engine_config_path=FIXTURES / "simulator_minimal.yaml",
        max_iterations=3,
        seed=42,
    )

    assert mock_publisher.connect.call_count == 1
    assert mock_publisher.publish_reading.call_count == 3
    assert mock_publisher.close.call_count == 1

    for call in mock_publisher.publish_reading.call_args_list:
        kwargs = call.kwargs
        assert kwargs["device_id"] == "device_001"
        assert kwargs["sensor"] == "motor_current"
        assert kwargs["unit"] == "A"
        assert isinstance(kwargs["value"], float)


def test_run_rejects_multiple_devices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text(
        """
devices:
  - id: device_001
    type: telescopic_mast_v1
    sensors:
      - {name: motor_current, unit: A, baseline: 0.5, noise_std: 0.1}
  - id: device_002
    type: telescopic_mast_v1
    sensors:
      - {name: motor_current, unit: A, baseline: 0.5, noise_std: 0.1}
"""
    )
    monkeypatch.setattr("src.simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("src.simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="exactly 1 device"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )


def test_run_rejects_unsupported_sensor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    devices_yaml = tmp_path / "devices.yaml"
    devices_yaml.write_text(
        """
devices:
  - id: device_001
    type: telescopic_mast_v1
    sensors:
      - {name: hydraulic_pressure, unit: bar, baseline: 10, noise_std: 2}
"""
    )
    monkeypatch.setattr("src.simulator.engine._make_publisher", lambda c: MagicMock())
    monkeypatch.setattr("src.simulator.engine.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="motor_current"):
        run(
            mqtt_config_path=FIXTURES / "mqtt_minimal.yaml",
            devices_path=devices_yaml,
            engine_config_path=FIXTURES / "simulator_minimal.yaml",
            max_iterations=1,
        )
```

- [x] **Step 5.2: Testi başarısız çalıştır**

```bash
pytest tests/unit/test_engine.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'src.simulator.engine'`.

- [x] **Step 5.3: Engine implementasyonunu yaz**

`src/simulator/engine.py`:
```python
"""Iterasyon 1 engine: tek cihaz, tek sensör, 1 Hz blocking loop."""
from __future__ import annotations

import random
import signal
import time
from pathlib import Path
from types import FrameType

from loguru import logger

from src.simulator.config import (
    DeviceConfig,
    EngineConfig,
    MQTTConfig,
    load_devices,
    load_engine_config,
    load_mqtt_config,
)
from src.simulator.publisher import MQTTPublisher
from src.simulator.sensors.motor_current import MotorCurrentSensor


def _make_publisher(config: MQTTConfig) -> MQTTPublisher:
    """Test edilebilirlik için factory; monkeypatch ile değiştirilebilir."""
    return MQTTPublisher(config)


def _validate_iteration1_constraints(devices: list[DeviceConfig]) -> DeviceConfig:
    if len(devices) != 1:
        raise ValueError(
            f"Iterasyon 1 exactly 1 device destekliyor, alınan: {len(devices)}"
        )
    device = devices[0]
    if len(device.sensors) != 1 or device.sensors[0].name != "motor_current":
        raise ValueError(
            "Iterasyon 1: cihaz tam olarak bir 'motor_current' sensörü içermeli"
        )
    return device


def run(
    mqtt_config_path: Path = Path("config/mqtt.yaml"),
    devices_path: Path = Path("config/devices.yaml"),
    engine_config_path: Path = Path("config/simulator.yaml"),
    max_iterations: int | None = None,
    seed: int | None = None,
) -> None:
    """Engine'i başlatır. max_iterations=None → SIGINT/SIGTERM gelene dek sonsuz.

    seed verilirse RNG deterministik (test/regresyon için).
    """
    mqtt_config = load_mqtt_config(mqtt_config_path)
    devices = load_devices(devices_path)
    engine_config = load_engine_config(engine_config_path)
    logger.level(engine_config.log_level)

    device = _validate_iteration1_constraints(devices)
    sensor_config = device.sensors[0]
    rng = random.Random(seed) if seed is not None else random.Random()
    sensor = MotorCurrentSensor(sensor_config, rng)

    publisher = _make_publisher(mqtt_config)
    publisher.connect()

    stop = False

    def _shutdown(signum: int, _frame: FrameType | None) -> None:
        nonlocal stop
        logger.info("Shutdown sinyali alındı: {}", signum)
        stop = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    tick_interval = 1.0 / engine_config.tick_hz
    iterations = 0
    try:
        while not stop:
            value = sensor.sample()
            publisher.publish_reading(
                device_id=device.id,
                sensor=sensor_config.name,
                value=value,
                unit=sensor_config.unit,
                state="idle",
            )
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            time.sleep(tick_interval)
    finally:
        publisher.close()
```

- [x] **Step 5.4: Testleri yeşil çalıştır**

```bash
pytest tests/unit/test_engine.py -v
```
Beklenen: 3 test PASS.

- [x] **Step 5.5: Tüm unit testleri çalıştır + coverage**

```bash
pytest tests/unit/ --cov=src/simulator --cov-report=term-missing
```
Beklenen: 17 test PASS. `src/simulator/` kapsama %80+ olmalı (Iterasyon 1 için sade hedef; final %80 kapsama Faz 1 bitiminde değerlendirilecek).

- [x] **Step 5.6: Commit**

```bash
git add src/simulator/engine.py tests/unit/test_engine.py
git commit -m "feat(simulator): add 1 Hz blocking engine loop

Iterasyon 1 kapsamı: tek cihaz, tek sensör, sabit state='idle'.
SIGINT/SIGTERM ile graceful shutdown. max_iterations ve seed
parametreleri test/regresyon için.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `__main__.py` Entry Point + Config Örnekleri

**Files:**
- Create: `src/simulator/__main__.py`
- Modify: `config/devices.yaml.example` (Iterasyon 1 için sadeleştir)
- Modify: `config/mqtt.yaml.example` (gözden geçir, gerek yoksa dokunma)
- Create: `config/simulator.yaml.example`

- [ ] **Step 6.1: `__main__.py` oluştur**

`src/simulator/__main__.py`:
```python
"""`python -m simulator` entry point."""
from __future__ import annotations

import sys

from loguru import logger

from src.simulator.engine import run


def main() -> int:
    try:
        run()
        return 0
    except FileNotFoundError as e:
        logger.error("Config dosyası bulunamadı: {}", e)
        return 2
    except ValueError as e:
        logger.error("Config geçersiz: {}", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6.2: `config/devices.yaml.example`'ı Iterasyon 1'e uyacak şekilde sadeleştir**

Mevcut dosyanın tüm içeriğini şununla değiştir:

```yaml
# Simülasyon için cihaz tanımları örneği — Iterasyon 1 (walking skeleton)
# Gerçek devices.yaml dosyasını bu örnekten oluşturun: cp devices.yaml.example devices.yaml

devices:
  - id: device_001
    type: telescopic_mast_v1
    sensors:
      - name: motor_current
        unit: A
        baseline: 0.5
        noise_std: 0.1
```

İterasyon 2'de tüm sensörler ve state_durations eklenecek, example genişleyecek.

- [ ] **Step 6.3: `config/simulator.yaml.example`'ı oluştur**

```yaml
# Engine çalışma parametreleri
# Gerçek simulator.yaml dosyasını bu örnekten oluşturun: cp simulator.yaml.example simulator.yaml

engine:
  tick_hz: 1.0
  log_level: INFO
```

- [ ] **Step 6.4: `config/mqtt.yaml.example` gözden geçirme**

Mevcut içerik (`telemetry_prefix: telemetry`, `qos.telemetry: 1`) Iterasyon 1 için zaten yeterli. Eğer dosyada `alerts_prefix` gibi Iterasyon 1'de kullanılmayan alan varsa, kalmasında sakınca yok — config loader yalnızca kullandığı alanları okur. Dokunma gerekmeyebilir; bir bak ve değişiklik gerekiyorsa not düş.

- [ ] **Step 6.5: Commit**

```bash
git add src/simulator/__main__.py config/devices.yaml.example config/simulator.yaml.example
git commit -m "feat(simulator): add __main__ entry and simplify config examples for Iterasyon 1

python -m simulator entry'si engine.run() çağırır, FileNotFoundError
ve ValueError için exit 2. devices.yaml.example walking skeleton'a
(tek sensör) sadeleştirildi. simulator.yaml.example eklendi.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Uçtan Uca Manuel Doğrulama

Bu task **kullanıcı terminalinde** çalıştırılır (Mosquitto kurulu olmalı). Bir agent çalıştıramaz; kullanıcı yapar ve sonucu paylaşır.

- [ ] **Step 7.1: Mosquitto'nun çalıştığını doğrula**

```bash
brew services list | grep mosquitto
```
Beklenen: `mosquitto started`. Değilse: `brew services start mosquitto`.

- [ ] **Step 7.2: Lokal config dosyalarını oluştur**

```bash
cd /Users/cemalozcan/Desktop/mast-anomaly-detection
cp config/mqtt.yaml.example config/mqtt.yaml
cp config/devices.yaml.example config/devices.yaml
cp config/simulator.yaml.example config/simulator.yaml
```

- [ ] **Step 7.3: İki terminalde uçtan uca test**

Terminal A (subscriber, önce başlat):
```bash
mosquitto_sub -t 'telemetry/+/motor_current' -v
```

Terminal B (simulator):
```bash
cd /Users/cemalozcan/Desktop/mast-anomaly-detection
source .venv/bin/activate
python -m simulator
```

Beklenen: Terminal A'da ~her saniye bir mesaj görünür, örneğin:
```
telemetry/device_001/motor_current {"device_id": "device_001", "timestamp": "2026-05-18T15:30:00.123Z", "state": "idle", "sensor": "motor_current", "value": 0.487, "unit": "A"}
```

- [ ] **Step 7.4: Graceful shutdown doğrula**

Terminal B'de `Ctrl+C` bas. Beklenen Loguru çıktısı:
```
INFO     | Shutdown sinyali alındı: 2
INFO     | MQTT bağlantısı kapatılıyor
```
Process exit 0 ile çıkmalı.

- [ ] **Step 7.5: Iterasyon 1 kabul kriterleri kontrol listesi**

Spec § 3 Iterasyon 1 bitti kriterleri:
- [x] `python -m simulator` çalışır, çökmez. → Step 7.3
- [x] `mosquitto_sub -t telemetry/+/motor_current` ile mesajlar görülür. → Step 7.3
- [x] Mesaj formatı § 7'deki JSON şemasına uyar (device_id, timestamp ISO 8601 + Z, state, sensor, value, unit). → Step 7.3 çıktısı
- [x] `tests/unit/test_motor_current_sensor.py` ve `tests/unit/test_mqtt_publisher.py` yeşil. → Step 5.5

Hepsi onaylanırsa Iterasyon 1 kapanış commit'i:

```bash
git commit --allow-empty -m "milestone: Faz 1 Iterasyon 1 (walking skeleton) tamamlandı

Spec § 3 Iterasyon 1 kabul kriterleri karşılandı:
- python -m simulator MQTT'ye 1 Hz yayın yapıyor (sabit state=idle)
- Mesaj formatı § 7 JSON şemasına uyumlu
- Unit testler yeşil (test_motor_current_sensor, test_mqtt_publisher, test_engine, test_config)
- Graceful SIGINT/SIGTERM shutdown çalışıyor

Sıradaki: Iterasyon 2 (tüm sensörler + state machine).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notları

**Spec coverage (§ 3 Iterasyon 1):**
- Tek sensör `MotorCurrentSensor` → Task 3 ✓
- `MQTTPublisher` paho-mqtt wrapper → Task 4 ✓
- `engine.py` 1 Hz blocking loop → Task 5 ✓
- `__main__.py` entry → Task 6 ✓
- Minimum YAML config → Task 2 (loader) + Task 6 (example dosyaları) ✓
- Bitti kriteri 1-4 → Task 7 manuel doğrulama ✓

**Spec § 7 (timestamp) coverage:**
- `_now_iso()` fonksiyonu → Task 4, Step 4.3 ✓
- Test'te format regex → Task 4, Step 4.1 ✓

**Spec § 11 (hata yönetimi) Iterasyon 1 kapsamı:**
- Config dosyası yok → `_read_yaml` `FileNotFoundError` (Task 2, Step 2.4) ✓
- YAML parse hatası → `ValueError` raise (Task 2, Step 2.4) ✓
- Şema validation → `_validate_iteration1_constraints` (Task 5, Step 5.3) ✓
- SIGINT/SIGTERM graceful shutdown → `_shutdown` handler (Task 5, Step 5.3) ✓
- MQTT runtime disconnect / reconnect → Iterasyon 1 dışı (paho default reconnect davranışına bırakıldı; explicit `reconnect_delay_set` Iterasyon 3'te eklenir)

**Type tutarlılığı:**
- `SensorConfig`, `MQTTConfig`, `DeviceConfig`, `EngineConfig` → tek tanım (`config.py`), her yerde import ✓
- `_now_iso` → tek üretim (`publisher.py`), test ve publish_reading aynı fonksiyondan ✓
- `_make_publisher` factory → engine'de tanımlı, testte monkeypatch'lenebilir ✓

**Placeholder taraması:** "TBD", "TODO", "implement later" yok. Tüm code block'lar tam — kopyala-yapıştır çalışacak şekilde yazıldı.

**Bilinen sınırlamalar (planlı, Iterasyon 2+):**
- `BaseSensor` ABC yok — Iterasyon 2.
- `DeviceRuntimeState` yok, state="idle" sabit — Iterasyon 2.
- Tek sensör — Iterasyon 2'de hepsi.
- Tek cihaz — Iterasyon 3'te asyncio + çoklu cihaz.
- Senaryo desteği yok — Iterasyon 4.

# Faz 2 — Iterasyon 2.1: Ingestion Walking Skeleton — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task's final verification step MUST run FULL pytest suite + mypy + ruff over src AND ALL tests dirs.

**Goal:** `python -m ingestion` ile çalışan, Faz 1 simulator'ın MQTT yayınlarını subscribe edip her mesajı loguru ile console'a basan minimum servis. Henüz SQLite YOK (Iter 2.2'de) — sadece "broker'dan oku, parse et, log'la, temiz kapan" walking skeleton.

**Architecture:** `src/ingestion/` paketi 4 dosya: `config.py` (YAML loader), `message_parser.py` (JSON → frozen `IngestedReading` dataclass), `subscriber.py` (paho-mqtt wrapper, `loop_start` background thread + callable message handler), `__main__.py` (config + subscriber kurulumu + signal handler + main loop + log integration). Subscriber payload parsing'i bilmiyor — `__main__.py` parse'i çağırıp loguru'ya basıyor. Bozuk JSON / eksik field → ERROR log + skip (servis çökmemeli).

**Tech Stack:** Python 3.11+, paho-mqtt==2.1.0 (zaten yüklü, simulator publisher de kullanıyor), loguru, pytest, mypy strict, ruff, pyyaml. Yeni runtime dependency YOK.

**Referans:** `docs/specs/2026-05-29-faz2-ingestion-storage-design.md` (commit `88d7d8a`) § 3 Iter 2.1, § 5 IngestedReading + IngestionConfig, § 6 subscriber kontratı, § 11 hata yönetimi tablosu. Faz 1 contract: `docs/specs/2026-05-18-faz1-simulator-design.md` § 7 (topic + payload şeması).

---

## Önkoşul

`.venv` aktif, `pip install -e .` yapılmış, Faz 1 testleri (128 PASS) yeşil olmalı:

```bash
cd ~/mast-anomaly-detection
source .venv/bin/activate
pytest tests/ -q                                                    # 128 passed beklenir
mypy src/simulator tests/unit tests/integration tests/scenarios     # Success
ruff check src/simulator tests/unit tests/integration tests/scenarios   # All checks passed
```

`config/mqtt.yaml.example` mevcut (Faz 1'den) — ingestion da aynı broker config'ini okur.

---

## Dosya Yapısı (Iter 2.1 sonunda)

```
src/ingestion/
├── __init__.py                  # YENİ: boş package marker
├── __main__.py                  # YENİ: python -m ingestion entry
├── config.py                    # YENİ: IngestionConfig + load_ingestion_config
├── message_parser.py            # YENİ: IngestedReading dataclass + parse_message
└── subscriber.py                # YENİ: MQTTSubscriber paho wrapper

tests/unit/
├── test_ingestion_config.py     # YENİ: IngestionConfig YAML load testleri
├── test_ingestion_message_parser.py   # YENİ: parse_message + IngestedReading testleri
└── test_ingestion_subscriber.py # YENİ: paho mock + message callback testleri

config/
└── ingestion.yaml.example       # YENİ: subscribe topic pattern, log level

pyproject.toml                   # MODIFY: setuptools packages.find include "ingestion*" ekle
```

**Beklenen test sayısı:** 128 → ~141 (Faz 1 128 + 13 yeni: config 3 + parser 5 + subscriber 3 + main 2).
**Hedef coverage:** ingestion paketinde ≥%85 (toplam coverage Faz 1 %94'ten hafif düşebilir).

---

## Task 1: `IngestionConfig` Dataclass + YAML Loader + `ingestion.yaml.example`

`IngestionConfig` frozen dataclass + `load_ingestion_config(path)` YAML loader. `config/ingestion.yaml.example` ile birlikte. Faz 1 `config.py` pattern'i (load_mqtt_config benzeri).

**Files:**
- Create: `src/ingestion/__init__.py` (boş)
- Create: `src/ingestion/config.py`
- Create: `config/ingestion.yaml.example`
- Create: `tests/unit/test_ingestion_config.py`
- Modify: `pyproject.toml` (setuptools packages.find include "ingestion*")

- [x] **Step 1.1: `pyproject.toml`'da `packages.find` include genişlet**

Mevcut:
```toml
[tool.setuptools.packages.find]
where = ["src"]
include = ["simulator*"]
namespaces = false
```

Şununla değiştir:
```toml
[tool.setuptools.packages.find]
where = ["src"]
include = ["simulator*", "ingestion*", "storage*"]
namespaces = false
```

`storage*` Iter 2.2'de kullanılacak — şimdiden ekle ki sonradan reinstall gerekmesin.

- [x] **Step 1.2: `src/ingestion/__init__.py` boş dosya yarat**

```bash
mkdir -p src/ingestion
touch src/ingestion/__init__.py
```

- [x] **Step 1.3: `pip install -e .` yenile (yeni paketi tanı)**

```bash
pip install -e .
```
Beklenen: `Successfully installed mast-anomaly-detection-0.1.0` (yeni ingestion paketi tanınır).

- [x] **Step 1.4: `config/ingestion.yaml.example` yarat**

```yaml
ingestion:
  db_path: data/telemetry.db
  subscribe_topic_pattern: telemetry/+/+
  batch:
    max_size: 100
    flush_interval_s: 1.0
  log_level: INFO
```

`db_path` ve `batch` alanları Iter 2.1'de henüz kullanılmaz (Iter 2.2 + 2.3) ama config dosyası başından eksiksiz olsun ki sonraki iterasyonlarda örnek değişmesin.

- [x] **Step 1.5: `tests/unit/test_ingestion_config.py` failing testleri yaz**

```python
"""IngestionConfig YAML loader testleri (Iter 2.1)."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_load_ingestion_config_returns_dataclass(tmp_path: Path) -> None:
    """Geçerli YAML → IngestionConfig instance."""
    from ingestion.config import IngestionConfig, load_ingestion_config

    yaml_path = tmp_path / "ingestion.yaml"
    yaml_path.write_text("""
ingestion:
  db_path: data/telemetry.db
  subscribe_topic_pattern: telemetry/+/+
  batch:
    max_size: 100
    flush_interval_s: 1.0
  log_level: INFO
""")
    config = load_ingestion_config(yaml_path)
    assert isinstance(config, IngestionConfig)
    assert config.db_path == Path("data/telemetry.db")
    assert config.subscribe_topic_pattern == "telemetry/+/+"
    assert config.batch_max_size == 100
    assert config.batch_flush_interval_s == 1.0
    assert config.log_level == "INFO"


def test_load_ingestion_config_missing_file_raises(tmp_path: Path) -> None:
    """Dosya yoksa FileNotFoundError."""
    from ingestion.config import load_ingestion_config

    with pytest.raises(FileNotFoundError, match="ingestion.yaml"):
        load_ingestion_config(tmp_path / "nonexistent.yaml")


def test_load_ingestion_config_malformed_yaml_raises(tmp_path: Path) -> None:
    """Bozuk YAML → ValueError."""
    from ingestion.config import load_ingestion_config

    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("ingestion:\n  db_path: [unclosed")
    with pytest.raises(ValueError, match="ingestion config geçersiz"):
        load_ingestion_config(yaml_path)
```

- [x] **Step 1.6: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_ingestion_config.py -v
```
Beklenen: ImportError `ingestion.config` modülü yok.

- [x] **Step 1.7: `src/ingestion/config.py` yarat**

```python
"""Ingestion YAML konfigürasyon yükleyicisi (spec § 5)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class IngestionConfig:
    """ingestion.yaml'dan okunur. Iter 2.1 sadece subscribe_topic_pattern + log_level kullanır;
    db_path ve batch_* alanları Iter 2.2/2.3 için ileri-uyumlu (forward compat) eklendi.
    """
    db_path: Path
    subscribe_topic_pattern: str
    batch_max_size: int
    batch_flush_interval_s: float
    log_level: str


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Ingestion config dosyası bulunamadı: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"ingestion config geçersiz ({path}): YAML parse hatası: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(
            f"ingestion config geçersiz ({path}): kök sözlük olmalı, alınan {type(data).__name__}"
        )
    return data


def load_ingestion_config(path: Path) -> IngestionConfig:
    """ingestion.yaml dosyasından IngestionConfig döndürür.

    Args:
        path: ingestion.yaml dosyasının yolu.

    Returns:
        IngestionConfig.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: YAML bozuksa veya şema geçersizse.
    """
    data = _read_yaml(path)
    try:
        ing = data["ingestion"]
        batch = ing["batch"]
        return IngestionConfig(
            db_path=Path(str(ing["db_path"])),
            subscribe_topic_pattern=str(ing["subscribe_topic_pattern"]),
            batch_max_size=int(batch["max_size"]),
            batch_flush_interval_s=float(batch["flush_interval_s"]),
            log_level=str(ing["log_level"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"ingestion config geçersiz ({path}): {e}") from e
```

- [x] **Step 1.8: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_ingestion_config.py -v
```
Beklenen: 3 passed.

- [x] **Step 1.9: Tam suite + mypy + ruff yeşil**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion tests/unit tests/integration tests/scenarios
```
Beklenen: 128 + 3 = 131 passed, mypy clean, ruff clean. mypy/ruff'a `src/ingestion` eklendi.

- [x] **Step 1.10: Commit**

```bash
git add pyproject.toml \
        src/ingestion/__init__.py \
        src/ingestion/config.py \
        config/ingestion.yaml.example \
        tests/unit/test_ingestion_config.py
git commit -m "$(cat <<'EOF'
feat(ingestion): IngestionConfig dataclass + YAML loader + config/ingestion.yaml.example

Faz 2 walking skeleton ilk adım. IngestionConfig frozen dataclass (db_path,
subscribe_topic_pattern, batch_max_size, batch_flush_interval_s, log_level).
db_path + batch_* Iter 2.2/2.3 için ileri-uyumlu; Iter 2.1'de sadece
subscribe_topic_pattern + log_level kullanılır.

pyproject.toml packages.find include genişletildi: simulator + ingestion +
storage (storage Iter 2.2'de kullanılacak, şimdiden pip install -e . yenileme
maliyeti sonraya kalmasın).

3 unit test: valid YAML parse, missing file, malformed YAML.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `IngestedReading` Dataclass + `parse_message` Function

`IngestedReading` frozen dataclass (6 alan, spec § 5) + `parse_message(payload: bytes) -> IngestedReading`. Bozuk JSON / eksik field için spesifik exception raise eder; `__main__` bu exception'ları yakalayıp log + skip yapacak (Task 4).

**Files:**
- Create: `src/ingestion/message_parser.py`
- Create: `tests/unit/test_ingestion_message_parser.py`

- [x] **Step 2.1: `tests/unit/test_ingestion_message_parser.py` failing testleri yaz**

```python
"""IngestedReading + parse_message testleri (Iter 2.1)."""
from __future__ import annotations

import json

import pytest


def test_ingested_reading_is_frozen_dataclass() -> None:
    """IngestedReading frozen — mutate edilemez."""
    from dataclasses import FrozenInstanceError

    from ingestion.message_parser import IngestedReading

    reading = IngestedReading(
        device_id="device_001",
        sensor="motor_current",
        timestamp="2026-05-29T15:30:00.123Z",
        state="raising",
        value=8.5,
        unit="A",
    )
    with pytest.raises(FrozenInstanceError):
        reading.value = 9.0  # type: ignore[misc]


def test_parse_message_valid_payload_returns_reading() -> None:
    """Geçerli Faz 1 publisher payload'ı → IngestedReading."""
    from ingestion.message_parser import IngestedReading, parse_message

    payload = json.dumps({
        "device_id": "device_001",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "sensor": "motor_current",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")

    reading = parse_message(payload)
    assert reading == IngestedReading(
        device_id="device_001",
        sensor="motor_current",
        timestamp="2026-05-29T15:30:00.123Z",
        state="raising",
        value=8.7,
        unit="A",
    )


def test_parse_message_invalid_json_raises_json_decode_error() -> None:
    """Bozuk JSON → json.JSONDecodeError (spesifik exception)."""
    from ingestion.message_parser import parse_message

    with pytest.raises(json.JSONDecodeError):
        parse_message(b"{not valid json")


def test_parse_message_missing_field_raises_key_error() -> None:
    """Eksik field → KeyError."""
    from ingestion.message_parser import parse_message

    payload = json.dumps({
        "device_id": "device_001",
        # "timestamp" eksik
        "state": "raising",
        "sensor": "motor_current",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")

    with pytest.raises(KeyError, match="timestamp"):
        parse_message(payload)


def test_parse_message_wrong_value_type_raises_value_error_or_type_error() -> None:
    """value alanı non-numeric → ValueError veya TypeError."""
    from ingestion.message_parser import parse_message

    payload = json.dumps({
        "device_id": "device_001",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "sensor": "motor_current",
        "value": "not_a_number",
        "unit": "A",
    }).encode("utf-8")

    with pytest.raises((ValueError, TypeError)):
        parse_message(payload)
```

- [x] **Step 2.2: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_ingestion_message_parser.py -v
```
Beklenen: 5 yeni test ImportError ile FAIL.

- [x] **Step 2.3: `src/ingestion/message_parser.py` yarat**

```python
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
        KeyError: Beklenen field eksikse (device_id, timestamp, state, sensor, value, unit).
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
```

- [x] **Step 2.4: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_ingestion_message_parser.py -v
```
Beklenen: 5 passed.

- [x] **Step 2.5: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion tests/unit tests/integration tests/scenarios
```
Beklenen: 131 + 5 = 136 passed, mypy/ruff clean.

- [x] **Step 2.6: Commit**

```bash
git add src/ingestion/message_parser.py tests/unit/test_ingestion_message_parser.py
git commit -m "$(cat <<'EOF'
feat(ingestion): IngestedReading dataclass + parse_message JSON parser

Spec § 5: IngestedReading frozen dataclass (6 alan, Faz 1 publisher
TelemetryReading ile contract uyumlu). parse_message(payload: bytes) →
IngestedReading; bozuk JSON → JSONDecodeError, eksik field → KeyError,
yanlış type → ValueError/TypeError. Spesifik exception'lar __main__
tarafından yakalanıp log+skip ile handle edilecek (Task 4).

5 unit test: frozen invariant, valid roundtrip, JSON hatası, eksik field,
yanlış type.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `MQTTSubscriber` paho Wrapper

Subscriber class — paho-mqtt `Client.subscribe` + `loop_start` background thread + `on_message` callback delegasyonu. Payload parsing'i BİLMİYOR; callable `message_handler(client, userdata, msg)` parametresi alır ve paho callback'i ona iletir. `__main__` parse + log işini message_handler'da yapar.

**Files:**
- Create: `src/ingestion/subscriber.py`
- Create: `tests/unit/test_ingestion_subscriber.py`

- [x] **Step 3.1: `tests/unit/test_ingestion_subscriber.py` failing testleri yaz**

```python
"""MQTTSubscriber paho wrapper testleri (Iter 2.1)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_subscriber_connects_and_subscribes(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect_and_start broker'a bağlanır + topic'e subscribe eder + loop_start çağırır."""
    from simulator.config import MQTTConfig
    from ingestion.subscriber import MQTTSubscriber

    mock_client = MagicMock()
    config = MQTTConfig(
        host="localhost",
        port=1883,
        client_id_prefix="test-ingestion",
        keepalive=60,
        telemetry_prefix="telemetry",
        qos=1,
    )
    handler = MagicMock()

    subscriber = MQTTSubscriber(
        config=config,
        topic_pattern="telemetry/+/+",
        message_handler=handler,
        client=mock_client,
    )
    subscriber.connect_and_start()

    mock_client.connect.assert_called_once_with("localhost", 1883, 60)
    mock_client.subscribe.assert_called_once_with("telemetry/+/+", qos=1)
    mock_client.loop_start.assert_called_once()


def test_subscriber_routes_message_to_handler() -> None:
    """paho on_message callback ayarlanmış message_handler'ı çağırır."""
    from simulator.config import MQTTConfig
    from ingestion.subscriber import MQTTSubscriber

    mock_client = MagicMock()
    config = MQTTConfig(
        host="localhost", port=1883, client_id_prefix="test",
        keepalive=60, telemetry_prefix="telemetry", qos=1,
    )
    handler = MagicMock()

    subscriber = MQTTSubscriber(
        config=config, topic_pattern="telemetry/+/+",
        message_handler=handler, client=mock_client,
    )
    subscriber.connect_and_start()

    # paho `on_message` mock_client.on_message setter ile atanmış olmalı
    assert mock_client.on_message is not None

    # Callback'i manuel tetikle
    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = b'{"device_id":"device_001","sensor":"motor_current","timestamp":"2026-05-29T00:00:00.000Z","state":"idle","value":0.5,"unit":"A"}'
    mock_client.on_message(mock_client, None, fake_msg)

    handler.assert_called_once_with(fake_msg)


def test_subscriber_stop_disconnects_and_loop_stop() -> None:
    """stop() loop_stop + disconnect çağırır."""
    from simulator.config import MQTTConfig
    from ingestion.subscriber import MQTTSubscriber

    mock_client = MagicMock()
    config = MQTTConfig(
        host="localhost", port=1883, client_id_prefix="test",
        keepalive=60, telemetry_prefix="telemetry", qos=1,
    )

    subscriber = MQTTSubscriber(
        config=config, topic_pattern="telemetry/+/+",
        message_handler=MagicMock(), client=mock_client,
    )
    subscriber.stop()

    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()
```

- [x] **Step 3.2: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_ingestion_subscriber.py -v
```
Beklenen: 3 yeni test ImportError ile FAIL.

- [x] **Step 3.3: `src/ingestion/subscriber.py` yarat**

```python
"""MQTT subscriber (paho-mqtt wrapper) — spec § 6 kontratı."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt
from loguru import logger

from simulator.config import MQTTConfig

MessageHandler = Callable[[mqtt.MQTTMessage], None]
"""Callback signature: paho mesajını parse + log/save yapan dışsal handler."""


class MQTTSubscriber:
    """paho-mqtt thin wrapper. Subscribe + background loop. Payload parsing'i bilmiyor —
    message_handler callable'a ham mesajı iletir (separation of concerns).

    Spec § 6: topic pattern `telemetry/+/+`, QoS 1, loop_start background thread.
    """

    def __init__(
        self,
        config: MQTTConfig,
        topic_pattern: str,
        message_handler: MessageHandler,
        client: Any | None = None,
    ) -> None:
        """MQTT subscriber'ı başlat (henüz bağlanmaz).

        Args:
            config: MQTT broker bağlantı bilgileri (Faz 1 simulator ile aynı config).
            topic_pattern: Subscribe edilecek topic pattern (`telemetry/+/+`).
            message_handler: Her gelen mesaj için çağrılacak callable.
            client: paho-mqtt Client instance'ı (test için mock'lanabilir). None ise yeni client.
        """
        self.config = config
        self.topic_pattern = topic_pattern
        self.message_handler = message_handler
        self._client = client or mqtt.Client(
            client_id=f"{config.client_id_prefix}-subscriber"
        )

    def connect_and_start(self) -> None:
        """Broker'a bağlan, topic'e subscribe ol, background loop'u başlat.

        on_message callback'i `message_handler`'a delege eder.
        """
        logger.info("MQTT subscriber bağlanılıyor: {}:{}", self.config.host, self.config.port)

        def _on_message(_client: Any, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
            self.message_handler(msg)

        self._client.on_message = _on_message
        self._client.connect(self.config.host, self.config.port, self.config.keepalive)
        self._client.subscribe(self.topic_pattern, qos=self.config.qos)
        self._client.loop_start()
        logger.info("Subscribed: {} (QoS={})", self.topic_pattern, self.config.qos)

    def stop(self) -> None:
        """Background loop'u durdur, broker'dan ayrıl."""
        logger.info("MQTT subscriber kapatılıyor")
        self._client.loop_stop()
        self._client.disconnect()
```

`Callable` import için: `from collections.abc import Callable`. Mevcut.

- [x] **Step 3.4: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_ingestion_subscriber.py -v
```
Beklenen: 3 passed.

- [x] **Step 3.5: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion tests/unit tests/integration tests/scenarios
```
Beklenen: 136 + 3 = 139 passed, mypy/ruff clean.

- [x] **Step 3.6: Commit**

```bash
git add src/ingestion/subscriber.py tests/unit/test_ingestion_subscriber.py
git commit -m "$(cat <<'EOF'
feat(ingestion): MQTTSubscriber paho wrapper (spec § 6)

Subscriber class — paho.Client.subscribe + loop_start + on_message
delegasyonu. Payload parsing'i bilmiyor: message_handler callable
parametresi alır, paho mesajını ham olarak ona iletir (separation of
concerns — parse Task 2 message_parser.py'nin işi).

MQTTConfig (Faz 1 simulator ile aynı config) reuse — yeni config tipi yok.
QoS 1 (Faz 1 publisher ile uyumlu, broker queue garantisi).

3 unit test: connect+subscribe+loop_start çağrı zinciri, on_message →
handler routing, stop() loop_stop+disconnect.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `__main__.py` Entry — Config + Subscriber + Signal Handler + Log Pipeline

Üç önceki task'ı birleştir: config load → subscriber kur → message_handler içinde parse + log → SIGINT/SIGTERM bekle → graceful shutdown. `python -m ingestion` çalıştırılabilir hale gelir.

**Files:**
- Create: `src/ingestion/__main__.py`
- Create: `tests/unit/test_ingestion_main.py`

- [x] **Step 4.1: `tests/unit/test_ingestion_main.py` failing testleri yaz**

```python
"""Ingestion __main__ entry testleri (Iter 2.1)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_handle_message_parses_and_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """handle_message geçerli mesajı parse edip loguru INFO basar."""
    import logging

    from loguru import logger

    from ingestion.__main__ import _make_message_handler

    handler = _make_message_handler()
    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = json.dumps({
        "device_id": "device_001",
        "sensor": "motor_current",
        "timestamp": "2026-05-29T15:30:00.123Z",
        "state": "raising",
        "value": 8.7,
        "unit": "A",
    }).encode("utf-8")

    handler_id = logger.add(caplog.handler, level="INFO", format="{message}")
    try:
        with caplog.at_level(logging.INFO):
            handler(fake_msg)
    finally:
        logger.remove(handler_id)

    assert any("device_001" in r.message and "motor_current" in r.message
               for r in caplog.records)


def test_handle_message_bad_json_logs_error_and_skips(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Bozuk JSON payload → ERROR log + servis çökmez (exception bastırılır)."""
    import logging

    from loguru import logger

    from ingestion.__main__ import _make_message_handler

    handler = _make_message_handler()
    fake_msg = MagicMock()
    fake_msg.topic = "telemetry/device_001/motor_current"
    fake_msg.payload = b"{not_valid_json"

    handler_id = logger.add(caplog.handler, level="ERROR", format="{message}")
    try:
        with caplog.at_level(logging.ERROR):
            handler(fake_msg)  # raise etmemeli
    finally:
        logger.remove(handler_id)

    assert any("Bozuk mesaj" in r.message or "atlandı" in r.message
               for r in caplog.records)
```

- [x] **Step 4.2: Testleri koş, FAIL gör**

```bash
pytest tests/unit/test_ingestion_main.py -v
```
Beklenen: 2 yeni test ImportError ile FAIL.

- [x] **Step 4.3: `src/ingestion/__main__.py` yarat**

```python
"""Ingestion servisi entry: python -m ingestion (Iter 2.1 walking skeleton).

Faz 1 simulator MQTT yayınlarını subscribe eder, her mesajı parse edip
loguru INFO ile console'a basar. Henüz SQLite YOK (Iter 2.2'de eklenecek).

SIGINT/SIGTERM ile graceful shutdown: subscriber loop_stop + disconnect.
"""
from __future__ import annotations

import json
import signal
import threading
from collections.abc import Callable
from pathlib import Path
from types import FrameType

import paho.mqtt.client as mqtt
from loguru import logger

from ingestion.config import IngestionConfig, load_ingestion_config
from ingestion.message_parser import parse_message
from ingestion.subscriber import MQTTSubscriber
from simulator.config import MQTTConfig, load_mqtt_config


def _make_message_handler() -> Callable[[mqtt.MQTTMessage], None]:
    """Paho mesaj callback'i: parse + log. Bozuk mesajları yutar (servis çökmemeli)."""

    def handle(msg: mqtt.MQTTMessage) -> None:
        try:
            reading = parse_message(msg.payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error(
                "Bozuk mesaj atlandı: topic={} hata={} payload={!r}",
                msg.topic,
                e,
                msg.payload[:200],
            )
            return
        logger.info(
            "Telemetri: device={} sensor={} state={} value={} unit={} ts={}",
            reading.device_id,
            reading.sensor,
            reading.state,
            reading.value,
            reading.unit,
            reading.timestamp,
        )

    return handle


def run(
    mqtt_config_path: Path = Path("config/mqtt.yaml"),
    ingestion_config_path: Path = Path("config/ingestion.yaml"),
) -> None:
    """Ingestion servisini başlat. SIGINT/SIGTERM gelene kadar bloklar.

    Args:
        mqtt_config_path: MQTT broker YAML config (Faz 1 ile aynı dosya).
        ingestion_config_path: Ingestion-specific YAML config.

    Raises:
        FileNotFoundError: Config dosyası yoksa.
        ValueError: Config geçersizse.
    """
    mqtt_config = load_mqtt_config(mqtt_config_path)
    ingestion_config = load_ingestion_config(ingestion_config_path)
    logger.level(ingestion_config.log_level)

    handler = _make_message_handler()
    subscriber = MQTTSubscriber(
        config=mqtt_config,
        topic_pattern=ingestion_config.subscribe_topic_pattern,
        message_handler=handler,
    )

    shutdown = threading.Event()

    def _on_signal(signum: int, _frame: FrameType | None) -> None:
        logger.info("Shutdown sinyali alındı: {}", signum)
        shutdown.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    subscriber.connect_and_start()
    try:
        # Background paho thread mesajları işler; ana thread shutdown bekler.
        shutdown.wait()
    finally:
        subscriber.stop()
        logger.info("Ingestion temiz kapandı")


if __name__ == "__main__":  # pragma: no cover
    run()
```

- [x] **Step 4.4: Testleri koş, PASS gör**

```bash
pytest tests/unit/test_ingestion_main.py -v
```
Beklenen: 2 passed.

- [x] **Step 4.5: Tam suite + mypy + ruff**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion tests/unit tests/integration tests/scenarios
```
Beklenen: 139 + 2 = 141 passed, mypy clean, ruff clean.

- [x] **Step 4.6: Manuel uçtan uca smoke (simulator + ingestion paralel)**

İki ayrı terminal:

Terminal A — simulator (Faz 1):
```bash
python -m simulator
```

Terminal B — ingestion (Faz 2 walking skeleton):
```bash
cp config/ingestion.yaml.example config/ingestion.yaml
python -m ingestion
```

Beklenen Terminal B çıktısı:
- "MQTT subscriber bağlanılıyor: localhost:1883" log
- "Subscribed: telemetry/+/+ (QoS=1)" log
- Saniyede 18+ satır "Telemetri: device=device_001 sensor=motor_current state=idle value=0.5 unit=A ts=2026-05-29T..." benzeri (3 cihaz × 6 sensör)

Ctrl+C → "Shutdown sinyali alındı: 2" + "MQTT subscriber kapatılıyor" + "Ingestion temiz kapandı" + exit 0.

**NOTE FOR SUBAGENT:** Mosquitto kuruluysa otomatize edebilirsin (kısa 5-10s background simulator + 5s ingestion + grep + kill). Değilse SKIP, kullanıcı manuel doğrulayacak.

- [x] **Step 4.7: Commit**

```bash
git add src/ingestion/__main__.py tests/unit/test_ingestion_main.py
git commit -m "$(cat <<'EOF'
feat(ingestion): __main__ entry + signal handler + parse-log pipeline

python -m ingestion artık çalışıyor. Walking skeleton:
1. config/mqtt.yaml + config/ingestion.yaml yükle
2. MQTTSubscriber başlat (paho loop_start background thread)
3. message_handler: parse_message → loguru INFO; bozuk mesaj → ERROR + skip
4. threading.Event ile shutdown bekle (SIGINT/SIGTERM signal.signal)
5. Cleanup: subscriber.stop() (loop_stop + disconnect)

Iter 2.1 bitti kriteri 1-4 karşılanır:
- python -m ingestion çalışır ve çökmez ✅
- Simulator paralel akarken her mesaj loglanır ✅
- Bozuk JSON / eksik field → log + skip, servis devam ✅
- Ctrl+C → temiz exit 0 ✅

2 unit test: handle_message valid parse → log, bad json → error + no raise.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Iter 2.1 Milestone — CLAUDE.md Güncellemesi + Plan Closure

CLAUDE.md "Mevcut Faz" Iter 2.2 sıradaki olarak güncelle. Plan checkboxları [x]. Milestone commit.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/plans/2026-05-29-faz2-iter2-1-walking-skeleton-ingestion.md` (bu dosya — checkbox [x])

- [x] **Step 5.1: `CLAUDE.md` "Mevcut Faz" güncelle**

Header satırını şununla değiştir:
```
**Faz 2 — Iterasyon 2.2: SQLite Repository** (sıradaki)
```

"Tamamlanan iterasyonlar" listesine ekle (mevcut Faz 1 listesinin sonuna):
```
  - `docs/plans/2026-05-29-faz2-iter2-1-walking-skeleton-ingestion.md` (5/5 ✅)
```

"Spec (tek hakem)" satırının ALTINA yeni satır ekle:
```
- **Spec (Faz 2):** `docs/specs/2026-05-29-faz2-ingestion-storage-design.md`
```

"Çalıştırma" satırını şununla değiştir (yeni ingestion komutu ekle):
```
- **Çalıştırma:**
  - Simulator: `pip install -e .` editable install gerekli; sonra `python -m simulator` MQTT'ye N cihaz × 6 sensör × 1 Hz paralel yayın yapar (devices.yaml.example varsayılan 3 cihaz).
  - Ingestion (Iter 2.1 walking skeleton): `python -m ingestion` simulator yayınlarını subscribe edip loguru ile console'a basar. SQLite Iter 2.2'de eklenecek.
```

"Test/lint disiplini" satırına `src/ingestion` ekle:
```
- **Test/lint disiplini:** Her task sonunda tam suite + `mypy src/simulator src/ingestion tests/unit tests/integration tests/scenarios` + `ruff check src/simulator src/ingestion tests/unit tests/integration tests/scenarios`.
```

"Faz 1 Closure" alt başlığının ALTINA yeni başlık ekle:

```markdown
## Faz 2 (Ingestion + SQLite Storage)

### Iterasyon 2.1 (Walking Skeleton — MQTT Subscriber + Console Log) — Tamamlandı (2026-05-29)

`src/ingestion/` package'ı kuruldu: `config.py` (`IngestionConfig` dataclass + YAML loader),
`message_parser.py` (`IngestedReading` frozen dataclass + `parse_message`), `subscriber.py`
(`MQTTSubscriber` paho wrapper, loop_start background thread, callback delegasyonu),
`__main__.py` (config + subscriber + signal handler + parse-log pipeline). Bozuk JSON /
eksik field → ERROR log + skip (servis çökmez). SIGINT/SIGTERM graceful shutdown
(loop_stop + disconnect). `config/ingestion.yaml.example` ile birlikte 13 yeni unit test
(config 3 + parser 5 + subscriber 3 + main 2). 128 → 141 test, %85+ ingestion coverage.
Manuel uçtan uca: simulator + ingestion paralel çalışıyor, her mesaj loglanıyor.

### Iterasyon 2.2 (sıradaki) — Plan henüz yazılmadı

Kapsam (spec § 3 Iter 2.2): SQLAlchemy Core + tek wide tablo `telemetry` + composite
index + repository pattern (tek tek insert) + yalın script-based migration (`schema_version`
tablosu). `python -m ingestion` her mesajı SQLite'a yazacak.
```

- [x] **Step 5.2: Plan dosyasının tüm checkbox'larını [x] yap**

```bash
perl -i -pe 's/^- \[ \]/- [x]/g' docs/plans/2026-05-29-faz2-iter2-1-walking-skeleton-ingestion.md
```

Verify: `grep -c '^- \[ \]' docs/plans/2026-05-29-faz2-iter2-1-walking-skeleton-ingestion.md` → 0 olmalı.

- [x] **Step 5.3: Tam suite son kez**

```bash
pytest tests/ -q
mypy src/simulator src/ingestion tests/unit tests/integration tests/scenarios
ruff check src/simulator src/ingestion tests/unit tests/integration tests/scenarios
```
Beklenen: 141 passed, mypy/ruff clean.

- [x] **Step 5.4: Milestone commit**

```bash
git add CLAUDE.md docs/plans/2026-05-29-faz2-iter2-1-walking-skeleton-ingestion.md
git commit -m "$(cat <<'EOF'
milestone: Faz 2 Iterasyon 2.1 (ingestion walking skeleton) tamamlandı 🎉

src/ingestion/ package kuruldu (config + message_parser + subscriber +
__main__). python -m ingestion artık çalışıyor, Faz 1 simulator yayınlarını
subscribe edip loguru ile console'a basıyor. Bozuk mesaj log+skip, SIGINT
graceful shutdown.

Bitti kriterleri (spec § 3 Iter 2.1):
1. ✅ python -m ingestion çalışır, çökmez
2. ✅ Simulator paralel çalışırken her mesaj loglanır
3. ✅ Bozuk JSON / eksik field → ERROR log + skip
4. ✅ Ctrl+C → temiz exit 0
5. ✅ Unit testler (config 3 + parser 5 + subscriber 3 + main 2 = 13 yeni)

Toplam: 128 → 141 test (+13), ingestion paketi ≥%85 coverage. Iter 2.2
sıradaki: SQLAlchemy Core + repository + migration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Iter 2.1 Sonu — Bitti Kriterleri (spec § 3 ile birebir)

- [x] **Kriter 1:** `python -m ingestion` çalışır, çökmez (Task 4 manuel smoke).
- [x] **Kriter 2:** Simulator paralel çalışırken ingestion her mesajı loguru ile basar (Task 4 manuel smoke).
- [x] **Kriter 3:** Bozuk JSON / eksik field → ERROR log + skip, servis devam (Task 4 unit test `test_handle_message_bad_json_logs_error_and_skips`).
- [x] **Kriter 4:** Ctrl+C → "shutdown" log + temiz exit 0 (Task 4 manuel smoke).
- [x] **Kriter 5:** Unit testler ≥%85 ingestion coverage; toplam 128 + 13 = 141 (Task 1-4).

Her task'ın sonunda **DİSİPLİN** (CLAUDE.md kuralı): tam suite + mypy(src+tests) + ruff(src+tests) yeşil — per-file değil. Iter 2.1'den itibaren `src/ingestion` da dahil.

---

## Memory Güncellemesi (Iter 2.1 sonu, plan-dışı)

Iter 2.1 tamamlandıktan sonra `project_active_phase.md` memory'sini güncelle:
- `Active phase` → "Faz 2 — Iterasyon 2.2: SQLite Repository (next, plan not yet written). Iter 2.1 completed 2026-05-29."
- Iter 2.1 runtime contract notları: IngestionConfig + IngestedReading + MQTTSubscriber + _make_message_handler
- "Faz 2 brainstorming için açık tasarım soruları" bloğundan Iter 2.1'de karara bağlananları ÇIKAR (subscriber asyncio değil, IngestedReading ayrı dataclass, vb.)

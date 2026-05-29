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

"""Ingestion YAML konfigürasyon yükleyicisi (spec § 5)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class IngestionConfig:
    """ingestion.yaml'dan okunur.

    Iter 2.1 sadece ``subscribe_topic_pattern`` + ``log_level`` kullanır;
    ``db_path`` ve ``batch_*`` alanları Iter 2.2/2.3 için ileri-uyumlu
    (forward compat) eklendi.
    """

    db_path: Path
    subscribe_topic_pattern: str
    batch_max_size: int
    batch_flush_interval_s: float
    log_level: str


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"ingestion.yaml dosyası bulunamadı: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"ingestion config geçersiz ({path}): YAML parse hatası: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(
            f"ingestion config geçersiz ({path}): kök sözlük olmalı, "
            f"alınan {type(data).__name__}"
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

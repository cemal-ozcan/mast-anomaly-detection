"""Demo temiz baseline seed (Faz 8 Iter 8.1, spec § 5).

Servisler başlamadan önce demo cihazları için yakın-geçmiş TEMİZ telemetri yazar →
istatistik dedektör (ThreeSigma/IQR) baseline'ı hazır olur, arıza ~60s'de başlayınca
canlı tetiklenir (uzun gerçek-zamanlı warmup gerekmez). Gözlem modu: yalnız telemetry yazar.

NOT (B1, kayan pencere): seed bloğu zamanla `baseline_window_s`'lik kayan pencereden ERİR →
istatistik-overlap GEÇİCİ bir fırsat penceresinde gösterilir (yoğunluk `samples_per_state` +
`min_baseline` Task 5'te ölçülerek ayarlanır). NOT (S3): `__main__` `config/ingestion.yaml`
ister — demo_up.sh seed'den ÖNCE config'leri kopyalar; standalone çalıştırırken önce
`cp config/ingestion.yaml.example config/ingestion.yaml`.

Per-(sensor,state) temiz magnitüdler Faz 5 ölçümlerinden (seed 42, üretim çıktısı).
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ingestion.message_parser import IngestedReading
from storage.engine import create_sqlite_engine
from storage.migrator import MIGRATIONS_DIR, apply_migrations
from storage.repository import TelemetryRepository

# Ölçülen temiz per-(sensor, state) ortalamalar (Faz 5) + makul std (σ>0 → fence degenere değil).
# Yalnız arızaların tezahür ettiği RAISING + HOLDING durumları (istatistik bu state'lerde tetiklenir).
# NOT (Task 5 kalibrasyon): yalnız DURAĞAN, statistical-izlenen sensörler seed'lenir
# (detectors.demo `sensors: [motor_current, vibration, hydraulic_pressure]`). motor_temperature
# (stateful, soğuk-başlangıç rampası) + mast_position (rampalı) seed-baseline ile eşleşmez → FP'ye
# yol açar; motor_voltage statistical-kapsam dışı (varyans arızası kural katmanı işi). Bu yüzden
# burada YOK — canlı smoke device_001'de FP'yi bu daraltmayla giderdi.
_CLEAN: dict[str, dict[str, tuple[float, float]]] = {
    "motor_current":      {"raising": (8.0, 0.1),  "holding": (0.5, 0.1)},
    "vibration":          {"raising": (0.30, 0.01), "holding": (0.05, 0.01)},
    "hydraulic_pressure": {"raising": (150.0, 2.0), "holding": (80.0, 2.0)},
}

_UNITS = {
    "motor_current": "A", "vibration": "g", "hydraulic_pressure": "bar",
}


def _iso(now: datetime, back_s: float) -> str:
    return (now - timedelta(seconds=back_s)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed_baseline(
    db_path: Path,
    device_ids: list[str],
    window_s: int,
    samples_per_state: int,
    now: datetime | None = None,
) -> int:
    """Demo cihazları için temiz baseline telemetri yazar.

    Her (cihaz, sensör, state) için `samples_per_state` örnek, son `window_s` saniyeye yayılı,
    ölçülen temiz ortalama ± deterministik küçük salınım (σ>0). now DI ile (test edilebilir).

    Args:
        db_path: SQLite veritabanı dosya yolu.
        device_ids: Seed yazılacak cihaz ID listesi.
        window_s: Kayan pencere genişliği (saniye); örnekler bu aralığa yayılır.
        samples_per_state: Her (cihaz, sensör, state) için yazılacak örnek sayısı.
        now: Zaman referansı (varsayılan: UTC şimdiki zaman; test DI için).

    Returns:
        Yazılan satır sayısı.
    """
    now = now or datetime.now(UTC)
    engine = create_sqlite_engine(db_path)
    rows: list[IngestedReading] = []
    try:
        apply_migrations(engine, MIGRATIONS_DIR)
        repo = TelemetryRepository(engine)
        step = window_s / max(1, samples_per_state)
        for device_id in device_ids:
            for sensor, states in _CLEAN.items():
                for state, (mean, std) in states.items():
                    for i in range(samples_per_state):
                        val = mean + std * ((i % 3) - 1)
                        back = window_s - i * step  # eski→yeni
                        rows.append(IngestedReading(
                            device_id=device_id, sensor=sensor, timestamp=_iso(now, back),
                            state=state, value=val, unit=_UNITS[sensor],
                        ))
        repo.insert_batch(rows)
        return len(rows)
    finally:
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    from ingestion.config import load_ingestion_config

    cfg = load_ingestion_config(Path("config/ingestion.yaml"))
    written = seed_baseline(
        db_path=Path(cfg.db_path),
        device_ids=["device_001", "device_002", "device_003", "device_004"],
        window_s=300,
        samples_per_state=80,
    )
    print(f"seed_demo_baseline: {written} temiz baseline satırı yazıldı", file=sys.stderr)

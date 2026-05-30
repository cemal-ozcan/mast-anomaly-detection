"""İstatistiksel dedektör saf yardımcıları (Faz 5, spec § 5).

split_recent: uzun pencereyi baseline (eski) + güncel (son tail) olarak böler.
iter_sensor_state_groups: yeterli-örnekli (sensor, state) için baseline+güncel value Series üretir.
Saf — yalnız pandas; storage/service import etmez. ThreeSigma (5.1) + IQR (5.2) ortak kullanır.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence

import pandas as pd

# σ/IQR < EPSILON → yeterli değişkenlik yok, güvenilir baseline değil (o grup atlanır).
EPSILON = 1e-9


def split_recent(
    window: pd.DataFrame, current_window_s: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Uzun pencereyi (baseline, current) olarak böler (pencerenin max timestamp'ine göre).

    current = [max_ts - current_window_s, max_ts]; baseline = öncesi. Güncel'i baseline'dan
    dışlamak gelişen arızanın baseline'ı kirletmesini azaltır (spec § 5). `now` gerekmez —
    bölme pencerenin kendi zaman aralığına dayanır (dedektör saf kalır).

    Args:
        window: [device_id, timestamp, sensor, state, value] uzun-format (ISO 8601 ms Z).
        current_window_s: son "güncel" pencere saniyesi.

    Returns:
        (baseline_df, current_df). Boş pencere → (window, window).
    """
    if window.empty:
        return window, window
    ts = pd.to_datetime(window["timestamp"], format="ISO8601", utc=True)
    cutoff = ts.max() - pd.Timedelta(seconds=current_window_s)
    is_current = ts >= cutoff
    return window[~is_current], window[is_current]


def iter_sensor_state_groups(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    sensors: Sequence[str] | None,
    min_baseline: int,
    min_current: int,
) -> Iterator[tuple[str, str, pd.Series[float], pd.Series[float]]]:
    """Yeterli-örnekli (sensor, state) için (sensor, state, baseline_values, current_values).

    Güncel tail'de görülen her (sensor, state) için, baseline'da ≥min_baseline ve güncelde
    ≥min_current örnek varsa yield eder; aksi halde atlar (abstain).

    Args:
        baseline_df, current_df: split_recent çıktısı.
        sensors: İzlenecek sensörler; None → güncelde görülen tüm sensörler (sıralı).
        min_baseline, min_current: minimum örnek eşikleri.

    Yields:
        (sensor, state, baseline_values: pd.Series, current_values: pd.Series).
    """
    if current_df.empty:
        return
    sensor_list = sensors if sensors is not None else sorted(current_df["sensor"].unique())
    for sensor in sensor_list:
        cur_sensor = current_df[current_df["sensor"] == sensor]
        base_sensor = baseline_df[baseline_df["sensor"] == sensor]
        for state in sorted(cur_sensor["state"].unique()):
            cur_vals = cur_sensor[cur_sensor["state"] == state]["value"]
            base_vals = base_sensor[base_sensor["state"] == state]["value"]
            if len(cur_vals) < min_current or len(base_vals) < min_baseline:
                continue
            yield str(sensor), str(state), base_vals, cur_vals

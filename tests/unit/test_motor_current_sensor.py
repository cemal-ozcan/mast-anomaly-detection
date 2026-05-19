import random
import statistics

import pytest

from simulator.config import SensorConfig
from simulator.sensors.motor_current import MotorCurrentSensor


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

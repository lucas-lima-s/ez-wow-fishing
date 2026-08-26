from __future__ import annotations

from tests import synth
from wow_ez_fishing.calibration import AmbientBaseline
from wow_ez_fishing.config import DetectionConfig

SAMPLE_RATE = 48000


def make_cfg(**overrides: object) -> DetectionConfig:
    defaults = {
        "band_low_hz": 300.0,
        "band_high_hz": 5000.0,
        "window_size": 512,
        "hop_size": 256,
        "calibration_seconds": 1.0,
        "trigger_margin_db": 10.0,
        "onset_db": 6.0,
        "onset_lookback_frames": 4,
        "min_event_frames": 2,
        "refractory_s": 1.0,
        "baseline_alpha": 0.05,
        "baseline_freeze_margin_db": 6.0,
    }
    defaults.update(overrides)
    return DetectionConfig(**defaults)


def test_calibration_baseline_within_1_5_db_of_ambient() -> None:
    cfg = make_cfg()
    baseline_a = AmbientBaseline(cfg, SAMPLE_RATE).prime(
        synth.make_ambience(3.0, seed=1, level_db=-48.0)
    )
    baseline_b = AmbientBaseline(cfg, SAMPLE_RATE).prime(
        synth.make_ambience(3.0, seed=2, level_db=-48.0)
    )
    assert abs(baseline_a - baseline_b) < 1.5


def test_baseline_frozen_during_event() -> None:
    cfg = make_cfg()
    baseline = AmbientBaseline(cfg, SAMPLE_RATE)
    baseline.prime(synth.make_ambience(2.0, seed=1))
    before = baseline.value

    baseline.update(before + cfg.baseline_freeze_margin_db + 5.0)
    assert baseline.value == before

    baseline.update(before + 1.0)
    assert baseline.value != before

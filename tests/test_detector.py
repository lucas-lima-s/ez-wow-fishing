from __future__ import annotations

import numpy as np

from tests import synth
from wow_ez_fishing.config import DetectionConfig
from wow_ez_fishing.detector import SplashDetector

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
        "baseline_alpha": 0.02,
        "baseline_freeze_margin_db": 6.0,
    }
    defaults.update(overrides)
    return DetectionConfig(**defaults)


def _push_all(detector: SplashDetector, signal: np.ndarray, hop_size: int) -> list:
    events = []
    for i in range(0, len(signal), hop_size):
        chunk = signal[i : i + hop_size]
        if len(chunk) == 0:
            break
        events.extend(detector.push(chunk))
    return events


def test_detector_finds_single_splash() -> None:
    cfg = make_cfg()
    detector = SplashDetector(cfg, SAMPLE_RATE)
    detector.prime(synth.make_ambience(2.0, seed=1))

    signal = synth.make_ambience(3.0, seed=2)
    splash_t = 1.5
    synth.place(signal, synth.make_splash(0.6, seed=10), splash_t, SAMPLE_RATE)

    events = _push_all(detector, signal, cfg.hop_size)

    assert len(events) == 1
    assert abs(events[0].t - splash_t) <= 0.05


def test_detector_ignores_steady_tone() -> None:
    cfg = make_cfg()
    detector = SplashDetector(cfg, SAMPLE_RATE)

    ambient_tone = synth.make_ambience(2.0, seed=1) + synth.make_tone(
        2.0, freq_hz=800.0, level_db=-40.0
    )
    detector.prime(ambient_tone)

    signal = synth.make_ambience(3.0, seed=2) + synth.make_tone(3.0, freq_hz=800.0, level_db=-40.0)
    events = _push_all(detector, signal, cfg.hop_size)

    assert events == []


def test_detector_ignores_slow_ramp() -> None:
    cfg = make_cfg()
    detector = SplashDetector(cfg, SAMPLE_RATE)
    detector.prime(synth.make_ambience(2.0, seed=1, level_db=-60.0))

    ambience = synth.make_ambience(5.0, seed=2, level_db=-60.0)
    ramp = synth.make_ramp(5.0, start_db=-60.0, end_db=-30.0)
    signal = (ambience * ramp).astype(np.float32)

    events = _push_all(detector, signal, cfg.hop_size)

    assert events == []


def test_detector_ignores_out_of_band_burst() -> None:
    cfg = make_cfg()
    detector = SplashDetector(cfg, SAMPLE_RATE)
    detector.prime(synth.make_ambience(2.0, seed=1))

    signal = synth.make_ambience(3.0, seed=2)
    synth.place(signal, synth.make_out_of_band_burst(), 1.5, SAMPLE_RATE)

    events = _push_all(detector, signal, cfg.hop_size)

    assert events == []


def test_detector_requires_onset() -> None:
    cfg = make_cfg()
    detector = SplashDetector(cfg, SAMPLE_RATE)
    detector.prime(synth.make_ambience(2.0, seed=1))

    signal = synth.make_ambience(4.0, seed=2)
    synth.place(signal, synth.make_fading_splash(2.0, fade_in_s=2.0, seed=10), 1.0, SAMPLE_RATE)

    events = _push_all(detector, signal, cfg.hop_size)

    assert events == []


def test_detector_refractory() -> None:
    cfg = make_cfg(refractory_s=3.0)

    detector_close = SplashDetector(cfg, SAMPLE_RATE)
    detector_close.prime(synth.make_ambience(2.0, seed=1))
    signal_close = synth.make_ambience(4.0, seed=2)
    synth.place(signal_close, synth.make_splash(0.4, seed=10), 1.0, SAMPLE_RATE)
    synth.place(signal_close, synth.make_splash(0.4, seed=11), 1.5, SAMPLE_RATE)
    events_close = _push_all(detector_close, signal_close, cfg.hop_size)
    assert len(events_close) == 1

    detector_far = SplashDetector(cfg, SAMPLE_RATE)
    detector_far.prime(synth.make_ambience(2.0, seed=1))
    signal_far = synth.make_ambience(7.0, seed=2)
    synth.place(signal_far, synth.make_splash(0.4, seed=10), 1.0, SAMPLE_RATE)
    synth.place(signal_far, synth.make_splash(0.4, seed=11), 5.0, SAMPLE_RATE)
    events_far = _push_all(detector_far, signal_far, cfg.hop_size)
    assert len(events_far) == 2

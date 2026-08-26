from __future__ import annotations

import numpy as np

SAMPLE_RATE = 48000


def _db_to_lin(db: float) -> float:
    return float(10 ** (db / 20))


def make_ambience(
    seconds: float, seed: int = 1, level_db: float = -48.0, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * sample_rate)
    white = rng.normal(0, 1, n)
    spec = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1 / sample_rate)
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    spec = spec / np.sqrt(freqs)
    pink = np.fft.irfft(spec, n)
    pink = pink / (np.max(np.abs(pink)) + 1e-12)
    return (pink * _db_to_lin(level_db)).astype(np.float32)


def make_band_noise(
    duration_s: float, seed: int, low_hz: float, high_hz: float, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = max(1, int(duration_s * sample_rate))
    white = rng.normal(0, 1, n)
    spec = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1 / sample_rate)
    spec[~((freqs >= low_hz) & (freqs <= high_hz))] = 0
    burst = np.fft.irfft(spec, n)
    return burst / (np.max(np.abs(burst)) + 1e-12)


def make_splash(
    duration_s: float,
    seed: int,
    level_db_over_ambient: float = 18.0,
    ambient_db: float = -48.0,
    sample_rate: int = SAMPLE_RATE,
    low_hz: float = 300.0,
    high_hz: float = 5000.0,
) -> np.ndarray:
    n = int(duration_s * sample_rate)
    burst = make_band_noise(duration_s, seed, low_hz, high_hz, sample_rate)
    attack_n = max(1, int(sample_rate * 0.015))
    env = np.ones(n)
    env[:attack_n] = np.linspace(0, 1, attack_n)
    tau = 0.4 * sample_rate
    env *= np.exp(-np.arange(n) / tau)
    level = _db_to_lin(ambient_db) * _db_to_lin(level_db_over_ambient)
    return (burst * env * level).astype(np.float32)


def make_fading_splash(
    duration_s: float,
    fade_in_s: float,
    seed: int,
    level_db_over_ambient: float = 18.0,
    ambient_db: float = -48.0,
    sample_rate: int = SAMPLE_RATE,
    low_hz: float = 300.0,
    high_hz: float = 5000.0,
) -> np.ndarray:
    n = int(duration_s * sample_rate)
    burst = make_band_noise(duration_s, seed, low_hz, high_hz, sample_rate)
    fade_n = min(n, max(1, int(fade_in_s * sample_rate)))
    env = np.ones(n)
    env[:fade_n] = np.linspace(0, 1, fade_n)
    level = _db_to_lin(ambient_db) * _db_to_lin(level_db_over_ambient)
    return (burst * env * level).astype(np.float32)


def make_tone(
    seconds: float,
    freq_hz: float = 220.0,
    level_db: float = -42.0,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    return (np.sin(2 * np.pi * freq_hz * t) * _db_to_lin(level_db)).astype(np.float32)


def make_ramp(
    seconds: float,
    start_db: float = -60.0,
    end_db: float = -30.0,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    n = int(seconds * sample_rate)
    gains = np.linspace(_db_to_lin(start_db), _db_to_lin(end_db), n)
    return gains.astype(np.float32)


def make_click(
    sample_rate: int = SAMPLE_RATE, duration_ms: float = 1.0, level: float = 0.9, seed: int = 3
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = max(1, int(sample_rate * duration_ms / 1000))
    return (rng.normal(0, level, n)).astype(np.float32)


def make_out_of_band_burst(
    duration_s: float = 0.1,
    low_hz: float = 11000.0,
    high_hz: float = 16000.0,
    level_db_over_ambient: float = 18.0,
    ambient_db: float = -48.0,
    sample_rate: int = SAMPLE_RATE,
    seed: int = 5,
) -> np.ndarray:
    burst = make_band_noise(duration_s, seed, low_hz, high_hz, sample_rate)
    level = _db_to_lin(ambient_db) * _db_to_lin(level_db_over_ambient)
    return (burst * level).astype(np.float32)


def place(
    base: np.ndarray, event: np.ndarray, start_s: float, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    start = int(start_s * sample_rate)
    end = min(start + len(event), len(base))
    length = end - start
    if length > 0:
        base[start:end] += event[:length]
    return base

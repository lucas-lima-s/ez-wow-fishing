from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000


def _db_to_lin(db: float) -> float:
    return float(10 ** (db / 20))


def _band_limited_noise(
    rng: np.random.Generator, n: int, low_hz: float, high_hz: float, sample_rate: int
) -> np.ndarray:
    white = rng.normal(0, 1, n)
    spec = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1 / sample_rate)
    spec[~((freqs >= low_hz) & (freqs <= high_hz))] = 0
    filtered = np.fft.irfft(spec, n)
    peak = np.max(np.abs(filtered)) + 1e-12
    return filtered / peak


def _pink_ambience(rng: np.random.Generator, n: int, sample_rate: int) -> np.ndarray:
    white = rng.normal(0, 1, n)
    spec = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1 / sample_rate)
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    spec = spec / np.sqrt(freqs)
    pink = np.fft.irfft(spec, n)
    return pink / (np.max(np.abs(pink)) + 1e-12)


def _splash_envelope(
    n: int, sample_rate: int, attack_ms: float = 15.0, decay_ms: float = 400.0
) -> np.ndarray:
    attack_n = min(n, max(1, int(sample_rate * attack_ms / 1000)))
    t = np.arange(n)
    env = np.ones(n)
    env[:attack_n] = np.linspace(0, 1, attack_n)
    decay_tau = (decay_ms / 1000) * sample_rate
    env *= np.exp(-t / decay_tau)
    return env


def generate(seconds: float, splash_times: list[float], seed: int, distractors: bool) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n_total = int(seconds * SAMPLE_RATE)

    ambient_level = _db_to_lin(-48.0)
    signal = _pink_ambience(rng, n_total, SAMPLE_RATE) * ambient_level

    if distractors:
        t_axis = np.arange(n_total) / SAMPLE_RATE
        tone = np.sin(2 * np.pi * 220.0 * t_axis) * ambient_level * _db_to_lin(6.0)
        signal = signal + tone
        gain_ramp = np.linspace(1.0, _db_to_lin(10.0), n_total)
        signal = signal * gain_ramp

    splash_level = ambient_level * _db_to_lin(18.0)
    splash_duration_s = 0.6
    splash_n = int(splash_duration_s * SAMPLE_RATE)

    for t in splash_times:
        start = int(t * SAMPLE_RATE)
        end = min(start + splash_n, n_total)
        length = end - start
        if length <= 0:
            continue
        burst = _band_limited_noise(rng, splash_n, 300.0, 5000.0, SAMPLE_RATE)[:length]
        env = _splash_envelope(length, SAMPLE_RATE)
        signal[start:end] += burst * env * splash_level

    if distractors:
        click_time = min(seconds * 0.5, seconds - 0.05)
        click_start = int(click_time * SAMPLE_RATE)
        click_len = max(1, int(0.001 * SAMPLE_RATE))
        click_end = min(click_start + click_len, n_total)
        if click_end > click_start:
            signal[click_start:click_end] += rng.normal(
                0, splash_level * 2, click_end - click_start
            )

        burst_time = min(seconds * 0.85, seconds - 0.15)
        burst_start = int(burst_time * SAMPLE_RATE)
        burst_len = int(0.1 * SAMPLE_RATE)
        burst_end = min(burst_start + burst_len, n_total)
        length = burst_end - burst_start
        if length > 0:
            oob = _band_limited_noise(rng, burst_len, 11000.0, 16000.0, SAMPLE_RATE)[:length]
            signal[burst_start:burst_end] += oob * splash_level

    peak = float(np.max(np.abs(signal)))
    if peak > 0.98:
        signal = signal / peak * 0.98

    return signal.astype(np.float32)


def _write_wav(path: Path, signal: np.ndarray, sample_rate: int) -> None:
    pcm = np.clip(signal, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())


def _choose_splash_times(seconds: float, count: int, rng: np.random.Generator) -> list[float]:
    margin = seconds * 0.08
    usable = seconds - 2 * margin
    if count <= 0:
        return []
    slot = usable / count
    base = np.arange(count) * slot + slot / 2
    jitter = rng.uniform(-slot * 0.15, slot * 0.15, count)
    times = sorted((margin + base + jitter).tolist())
    return [round(t, 4) for t in times]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a synthetic fishing-splash WAV fixture.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--splashes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--distractors", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    rng = np.random.default_rng(args.seed)
    splash_times = _choose_splash_times(args.seconds, args.splashes, rng)
    signal = generate(args.seconds, splash_times, args.seed, args.distractors)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(args.out, signal, SAMPLE_RATE)

    truth_path = args.out.with_name(args.out.stem + ".truth.json")
    truth_path.write_text(
        json.dumps(
            {"events_s": splash_times, "sample_rate": SAMPLE_RATE, "seed": args.seed},
            indent=2,
        )
    )

    print(f"wrote {args.out} and {truth_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

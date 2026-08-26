from __future__ import annotations

import numpy as np

from wow_ez_fishing.config import DetectionConfig


class AmbientBaseline:
    """Tracks the ambient (non-splash) band energy level, in dB, over time."""

    def __init__(self, cfg: DetectionConfig, sample_rate: int) -> None:
        self._cfg = cfg
        self._sample_rate = sample_rate
        self._window = np.hanning(cfg.window_size).astype(np.float64)
        freqs = np.fft.rfftfreq(cfg.window_size, 1 / sample_rate)
        self._band_mask = (freqs >= cfg.band_low_hz) & (freqs <= cfg.band_high_hz)
        self._value = -120.0
        self._primed = False

    def _frame_band_db(self, frame: np.ndarray) -> float:
        spec = np.abs(np.fft.rfft(self._window * frame))
        band = spec[self._band_mask]
        energy = np.sqrt(np.mean(band**2)) if band.size else 0.0
        return float(20 * np.log10(energy + 1e-12))

    def prime(self, samples: np.ndarray) -> float:
        samples = np.asarray(samples, dtype=np.float64)
        window = self._cfg.window_size
        hop = self._cfg.hop_size
        values: list[float] = []
        pos = 0
        while pos + window <= len(samples):
            values.append(self._frame_band_db(samples[pos : pos + window]))
            pos += hop
        if not values:
            padded = np.pad(samples, (0, max(0, window - len(samples))))
            values.append(self._frame_band_db(padded))
        self._value = float(np.median(values))
        self._primed = True
        return self._value

    def update(self, band_db: float) -> None:
        if not self._primed:
            self._value = band_db
            self._primed = True
            return
        if band_db > self._value + self._cfg.baseline_freeze_margin_db:
            return
        alpha = self._cfg.baseline_alpha
        self._value = (1 - alpha) * self._value + alpha * band_db

    @property
    def value(self) -> float:
        return self._value

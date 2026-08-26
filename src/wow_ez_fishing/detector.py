from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wow_ez_fishing.calibration import AmbientBaseline
from wow_ez_fishing.config import DetectionConfig


@dataclass(frozen=True)
class DetectionEvent:
    t: float
    band_db: float
    baseline_db: float
    flux_db: float


class SplashDetector:
    """Pure-numpy band-limited onset detector. No I/O, no threads, no wall clock."""

    def __init__(self, cfg: DetectionConfig, sample_rate: int) -> None:
        self._cfg = cfg
        self._sample_rate = sample_rate
        self._window = np.hanning(cfg.window_size).astype(np.float64)
        freqs = np.fft.rfftfreq(cfg.window_size, 1 / sample_rate)
        self._band_mask = (freqs >= cfg.band_low_hz) & (freqs <= cfg.band_high_hz)
        self._baseline = AmbientBaseline(cfg, sample_rate)

        self._ring = np.zeros(0, dtype=np.float64)
        self._consumed_samples = 0
        self._history: list[float] = []

        self._in_event = False
        self._consecutive = 0
        self._event_start_t = 0.0
        self._event_start_band_db = -120.0
        self._event_start_flux_db = 0.0
        self._last_event_t: float | None = None
        self._last_band_db = -120.0

    def prime(self, ambient: np.ndarray) -> float:
        return self._baseline.prime(ambient)

    def push(self, samples: np.ndarray) -> list[DetectionEvent]:
        events: list[DetectionEvent] = []
        self._ring = np.concatenate([self._ring, np.asarray(samples, dtype=np.float64)])
        window = self._cfg.window_size
        hop = self._cfg.hop_size
        while len(self._ring) >= window:
            frame = self._ring[:window]
            frame_t = self._consumed_samples / self._sample_rate
            self._ring = self._ring[hop:]
            self._consumed_samples += hop
            event = self._process_frame(frame, frame_t)
            if event is not None:
                events.append(event)
        return events

    def _band_db(self, frame: np.ndarray) -> float:
        spec = np.abs(np.fft.rfft(self._window * frame))
        band = spec[self._band_mask]
        energy = np.sqrt(np.mean(band**2)) if band.size else 0.0
        return float(20 * np.log10(energy + 1e-12))

    def _process_frame(self, frame: np.ndarray, frame_t: float) -> DetectionEvent | None:
        cfg = self._cfg
        band_db = self._band_db(frame)
        lookback = self._history[-cfg.onset_lookback_frames :] if self._history else []
        reference = max(lookback) if lookback else band_db
        flux_db = band_db - reference

        self._last_band_db = band_db

        qualifies = (
            band_db >= self._baseline.value + cfg.trigger_margin_db and flux_db >= cfg.onset_db
        )

        event: DetectionEvent | None = None
        if qualifies:
            if not self._in_event:
                self._in_event = True
                self._consecutive = 1
                self._event_start_t = frame_t
                self._event_start_band_db = band_db
                self._event_start_flux_db = flux_db
            else:
                self._consecutive += 1

            in_refractory = (
                self._last_event_t is not None
                and self._event_start_t - self._last_event_t < cfg.refractory_s
            )
            if self._consecutive >= cfg.min_event_frames and not in_refractory:
                event = DetectionEvent(
                    t=self._event_start_t,
                    band_db=self._event_start_band_db,
                    baseline_db=self._baseline.value,
                    flux_db=self._event_start_flux_db,
                )
                self._last_event_t = self._event_start_t
                self._in_event = False
                self._consecutive = 0
        else:
            self._in_event = False
            self._consecutive = 0

        currently_in_refractory = (
            self._last_event_t is not None and frame_t - self._last_event_t < cfg.refractory_s
        )
        if not self._in_event and not currently_in_refractory and event is None:
            self._baseline.update(band_db)

        if not qualifies:
            self._history.append(band_db)
            if len(self._history) > cfg.onset_lookback_frames:
                self._history.pop(0)

        return event

    @property
    def baseline_db(self) -> float:
        return self._baseline.value

    @property
    def last_band_db(self) -> float:
        return self._last_band_db

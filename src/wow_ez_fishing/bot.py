from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum
from typing import Any

import numpy as np

from wow_ez_fishing.config import AppConfig

_TIME_EPSILON = 1e-9


class State(Enum):
    CALIBRATING = "calibrating"
    IDLE = "idle"
    CASTING = "casting"
    ARMING = "arming"
    LISTENING = "listening"
    LOOTING = "looting"
    BLOCKED = "blocked"
    PAUSED = "paused"
    STOPPED = "stopped"


class FishingBot:
    def __init__(
        self,
        source: Any,
        detector: Any,
        actions: Any,
        guard: Any,
        meter: Any,
        cfg: AppConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._detector = detector
        self._actions = actions
        self._guard = guard
        self._meter = meter
        self._cfg = cfg
        self._clock = clock

        self.state = State.CALIBRATING
        self._casts = 0
        self._catches = 0
        self._misses = 0
        self._gated = 0
        self._start_t: float | None = None
        self._paused = False
        self._stop_requested = False
        self.baseline_db = 0.0

    @property
    def cfg(self) -> AppConfig:
        return self._cfg

    @property
    def detector(self) -> Any:
        return self._detector

    @property
    def guard(self) -> Any:
        return self._guard

    def pause(self) -> None:
        self._paused = not self._paused

    def request_stop(self) -> None:
        self._stop_requested = True

    def _read_frame(self) -> np.ndarray | None:
        return self._source.read(timeout=0.05)

    def _source_exhausted(self) -> bool:
        return bool(getattr(self._source, "exhausted", False))

    def _read_for(self, seconds: float) -> np.ndarray:
        remaining = seconds
        chunks: list[np.ndarray] = []
        while remaining > _TIME_EPSILON:
            if self._source_exhausted():
                break
            t0 = self._clock()
            frame = self._read_frame()
            dt = self._clock() - t0
            if frame is not None and len(frame):
                chunks.append(frame)
            remaining -= max(dt, 1e-6)
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def calibrate(self) -> float:
        self.state = State.CALIBRATING
        ambient = self._read_for(self._cfg.detection.calibration_seconds)
        self.baseline_db = self._detector.prime(ambient)
        return self.baseline_db

    def _tick(self, resume_state: State) -> tuple[np.ndarray | None, float, list[Any]] | None:
        if self._should_stop():
            return None
        if self._paused:
            self.state = State.PAUSED
            self._consume(discard=True)
            return None
        if not self._guard.allowed():
            self.state = State.BLOCKED
            self._consume(discard=True)
            return None
        self.state = resume_state
        return self._consume(discard=False)

    def _consume(self, discard: bool) -> tuple[np.ndarray | None, float, list[Any]]:
        t0 = self._clock()
        frame = self._read_frame()
        dt = self._clock() - t0
        events: list[Any] = []
        if frame is not None and len(frame):
            pushed = self._detector.push(frame)
            events = [] if discard else pushed
        return frame, dt, events

    def _wait(self, seconds: float, resume_state: State) -> bool:
        remaining = seconds
        while remaining > _TIME_EPSILON:
            result = self._tick(resume_state)
            if result is None:
                return False
            _, dt, _ = result
            remaining -= max(dt, 1e-6)
        return True

    def _should_stop(self) -> bool:
        if self._stop_requested or self._source_exhausted():
            return True
        b = self._cfg.bot
        return bool(
            b.stop_after_minutes
            and self._start_t is not None
            and (self._clock() - self._start_t) >= b.stop_after_minutes * 60
        )

    def _cast_budget_reached(self) -> bool:
        b = self._cfg.bot
        return bool(b.max_casts and self._casts >= b.max_casts)

    def run(self) -> dict[str, float]:
        self._start_t = self._clock()
        self.calibrate()
        self.state = State.IDLE
        try:
            while not self._should_stop() and not self._cast_budget_reached():
                if not self._wait(self._cfg.input.recast_delay_s, State.IDLE):
                    continue
                if self._should_stop() or self._cast_budget_reached():
                    break
                self.state = State.CASTING
                ok = self._actions.cast()
                if not ok:
                    self.state = State.BLOCKED
                    continue
                self._casts += 1
                self._step_arming()
        except KeyboardInterrupt:
            pass
        self.state = State.STOPPED
        self._source.stop()
        return self.stats()

    def _step_arming(self) -> None:
        remaining = self._cfg.input.cast_to_arm_s
        while remaining > _TIME_EPSILON:
            result = self._tick(State.ARMING)
            if result is None:
                return
            _, dt, _events = result
            remaining -= max(dt, 1e-6)
        self._step_listening()

    def _step_listening(self) -> None:
        remaining = self._cfg.bot.max_wait_s
        while remaining > _TIME_EPSILON:
            result = self._tick(State.LISTENING)
            if result is None:
                return
            _, dt, events = result
            if self._cfg.audio.backend == "session_meter":
                if self._meter.available and (
                    self._meter.recent_peak() >= self._cfg.audio.session_gate_peak
                ):
                    self._step_looting()
                    return
            else:
                for _event in events:
                    if (
                        self._cfg.audio.backend == "hybrid"
                        and self._meter.available
                        and self._meter.recent_peak() < self._cfg.audio.session_gate_peak
                    ):
                        self._gated += 1
                        continue
                    self._step_looting()
                    return
            remaining -= max(dt, 1e-6)
        self._misses += 1
        self.state = State.IDLE

    def _step_looting(self) -> None:
        if not self._wait(self._cfg.input.loot_delay_ms / 1000, State.LOOTING):
            return
        self._actions.loot()
        if not self._wait(self._cfg.input.post_loot_s, State.LOOTING):
            return
        self._catches += 1
        self.state = State.IDLE

    def stats(self) -> dict[str, float]:
        elapsed = (self._clock() - self._start_t) if self._start_t is not None else 0.0
        hours = elapsed / 3600
        catches_per_hour = (self._catches / hours) if hours > 0 else 0.0
        return {
            "casts": self._casts,
            "catches": self._catches,
            "misses": self._misses,
            "gated": self._gated,
            "dropped_frames": self._source.dropped_frames,
            "elapsed_s": elapsed,
            "catches_per_hour": catches_per_hour,
        }

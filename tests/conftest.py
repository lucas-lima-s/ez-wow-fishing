from __future__ import annotations

import sys
from collections import deque
from typing import Any

import numpy as np
import pytest

from wow_ez_fishing.input import DryRunKeyboard


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


class FakeSource:
    def __init__(
        self,
        clock: FakeClock,
        sample_rate: int = 48000,
        hop_size: int = 1024,
    ) -> None:
        self.clock = clock
        self.sample_rate = sample_rate
        self.channels = 1
        self.hop_size = hop_size
        self._frames: deque[np.ndarray] = deque()
        self._dropped_frames = 0
        self.exhausted = False
        self.stopped = False
        self.started = False

    def start(self) -> None:
        self.started = True

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        dt = self.hop_size / self.sample_rate
        if self._frames:
            frame = self._frames.popleft()
        else:
            frame = np.zeros(self.hop_size, dtype=np.float32)
        self.clock.advance(dt)
        return frame

    def stop(self) -> None:
        self.stopped = True

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    def push_signal(self, signal: np.ndarray) -> None:
        n = self.hop_size
        for i in range(0, len(signal), n):
            chunk = signal[i : i + n]
            if len(chunk) < n:
                chunk = np.pad(chunk, (0, n - len(chunk)))
            self._frames.append(chunk.astype(np.float32))


class FakeMeter:
    def __init__(self, available: bool = True, peak: float = 0.0) -> None:
        self.available = available
        self._peak = peak

    def recent_peak(self) -> float:
        return self._peak

    def set_peak(self, value: float) -> None:
        self._peak = value

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class AlwaysFocusedGuard:
    def allowed(self) -> bool:
        return True


class NeverFocusedGuard:
    def allowed(self) -> bool:
        return False


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def dry_keyboard(fake_clock: FakeClock) -> DryRunKeyboard:
    return DryRunKeyboard(clock=fake_clock)


@pytest.fixture
def always_focused() -> AlwaysFocusedGuard:
    return AlwaysFocusedGuard()


@pytest.fixture
def never_focused() -> NeverFocusedGuard:
    return NeverFocusedGuard()


@pytest.fixture
def fake_meter() -> FakeMeter:
    return FakeMeter()


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "windows_only: skip on non-Windows platforms")


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    if sys.platform == "win32":
        return
    skip_marker = pytest.mark.skip(reason="requires Windows")
    for item in items:
        if "windows_only" in item.keywords:
            item.add_marker(skip_marker)

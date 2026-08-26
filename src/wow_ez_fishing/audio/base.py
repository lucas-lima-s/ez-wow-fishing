from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class AudioSource(Protocol):
    sample_rate: int
    channels: int

    def start(self) -> None: ...

    def read(self, timeout: float | None = None) -> np.ndarray | None: ...

    def stop(self) -> None: ...

    @property
    def dropped_frames(self) -> int: ...

from __future__ import annotations

import time
import wave
from pathlib import Path

import numpy as np


class WavFileSource:
    def __init__(self, path: str | Path, hop_size: int, realtime: bool = False) -> None:
        self._wav = wave.open(str(path), "rb")  # noqa: SIM115
        self.sample_rate = self._wav.getframerate()
        self.channels = self._wav.getnchannels()
        self._sampwidth = self._wav.getsampwidth()
        self._hop_size = hop_size
        self._realtime = realtime
        self._dropped_frames = 0
        self._closed = False
        self.elapsed_s = 0.0
        self.exhausted = False

    def start(self) -> None:
        pass

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        if self._closed or self.exhausted:
            return None
        raw = self._wav.readframes(self._hop_size)
        if not raw:
            self.exhausted = True
            return None
        if self._sampwidth == 2:
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif self._sampwidth == 1:
            data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        else:
            raise ValueError(f"unsupported WAV sample width: {self._sampwidth} bytes")
        if self.channels > 1:
            data = data.reshape(-1, self.channels).mean(axis=1)
        duration = len(data) / self.sample_rate
        if self._realtime:
            time.sleep(duration)
        self.elapsed_s += duration
        return data

    def stop(self) -> None:
        if not self._closed:
            self._wav.close()
            self._closed = True

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    def __enter__(self) -> WavFileSource:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

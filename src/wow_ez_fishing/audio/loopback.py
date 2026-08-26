from __future__ import annotations

import contextlib
import queue
from typing import Any

import numpy as np

from wow_ez_fishing.audio.devices import resolve_loopback_device
from wow_ez_fishing.config import AudioConfig


class LoopbackSource:
    def __init__(self, cfg: AudioConfig, pa: Any | None = None) -> None:
        import pyaudiowpatch as pyaudio

        self._pyaudio = pyaudio
        self._cfg = cfg
        self._pa_owned = pa is None
        self._pa = pa if pa is not None else pyaudio.PyAudio()
        self._device = resolve_loopback_device(self._pa, cfg.device_name)
        self.sample_rate = cfg.sample_rate or int(self._device["defaultSampleRate"])
        self.channels = int(self._device["maxInputChannels"]) or 1
        self._queue: queue.Queue = queue.Queue(maxsize=cfg.queue_frames)
        self._dropped_frames = 0
        self._stream = None

    def start(self) -> None:
        if self._stream is not None:
            return
        self._stream = self._pa.open(
            format=self._pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            frames_per_buffer=self._cfg.frame_size,
            input=True,
            input_device_index=self._device["index"],
            stream_callback=self._callback,
        )
        self._stream.start_stream()

    def _callback(self, in_data, frame_count, time_info, status):
        pcm = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
        if self.channels > 1:
            pcm = pcm.reshape(-1, self.channels).mean(axis=1)
        try:
            self._queue.put_nowait(pcm)
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()
            self._dropped_frames += 1
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait(pcm)
        return (in_data, self._pyaudio.paContinue)

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
            if self._pa_owned:
                self._pa.terminate()

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    def __enter__(self) -> LoopbackSource:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

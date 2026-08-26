from __future__ import annotations

import logging
import threading
import time
from collections import deque

from wow_ez_fishing.config import AudioConfig

logger = logging.getLogger(__name__)

_HISTORY_WINDOW_S = 0.3


class SessionMeter:
    def __init__(self, cfg: AudioConfig) -> None:
        self._cfg = cfg
        self._peaks: deque[tuple[float, float]] = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._available = False
        self._import_ok = True
        try:
            import comtypes  # noqa: F401
            import pycaw.api.endpointvolume
            import pycaw.utils  # noqa: F401
        except ImportError:
            self._import_ok = False
            logger.warning("pycaw is not available; the per-process session gate is disabled")

    def start(self) -> None:
        if not self._import_ok or self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        from pycaw.api.endpointvolume import IAudioMeterInformation
        from pycaw.utils import AudioUtilities

        interval = 1.0 / max(self._cfg.session_poll_hz, 1)
        meter = None
        while not self._stop_event.is_set():
            if meter is None:
                meter = self._resolve_meter(AudioUtilities, IAudioMeterInformation)
            if meter is not None:
                try:
                    peak = meter.GetPeakValue()
                    self._push(peak)
                except Exception:
                    meter = None
                    self._available = False
            time.sleep(interval)

    def _resolve_meter(self, audio_utilities, meter_interface):
        from comtypes import COMError

        try:
            sessions = audio_utilities.GetAllSessions()
        except Exception:
            self._available = False
            return None
        for session in sessions:
            proc = session.Process
            if proc and proc.name().lower() == self._cfg.process_name.lower():
                try:
                    meter = session._ctl.QueryInterface(meter_interface)
                except (COMError, OSError, AttributeError):
                    continue
                self._available = True
                return meter
        self._available = False
        return None

    def _push(self, peak: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._peaks.append((now, peak))
            cutoff = now - _HISTORY_WINDOW_S
            while self._peaks and self._peaks[0][0] < cutoff:
                self._peaks.popleft()

    def recent_peak(self) -> float:
        with self._lock:
            if not self._peaks:
                return 0.0
            return max(p for _, p in self._peaks)

    @property
    def available(self) -> bool:
        return self._import_ok and self._available

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

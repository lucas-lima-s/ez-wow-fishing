from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from wow_ez_fishing.config import HotkeyConfig

logger = logging.getLogger(__name__)


class HotkeyListener:
    def __init__(
        self, pause_cb: Callable[[], None], stop_cb: Callable[[], None], cfg: HotkeyConfig
    ) -> None:
        self._pause_cb = pause_cb
        self._stop_cb = stop_cb
        self._cfg = cfg
        self._listener: Any = None

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            logger.warning("pynput is not available; hotkeys are disabled")
            return
        try:
            self._listener = keyboard.GlobalHotKeys(
                {
                    self._cfg.pause: self._pause_cb,
                    self._cfg.stop: self._stop_cb,
                }
            )
            self._listener.start()
        except Exception:
            logger.warning("failed to start the global hotkey listener; hotkeys are disabled")
            self._listener = None

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener.join(timeout=1.0)
            self._listener = None

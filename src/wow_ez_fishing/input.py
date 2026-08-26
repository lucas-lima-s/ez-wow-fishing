from __future__ import annotations

import random
import time
from typing import Any, Protocol

from wow_ez_fishing.config import InputConfig
from wow_ez_fishing.window import FocusGuard


class Keyboard(Protocol):
    def tap(self, key: str, hold_ms: int) -> None: ...


class DirectInputKeyboard:
    def __init__(self) -> None:
        import pydirectinput

        pydirectinput.PAUSE = 0
        self._pydirectinput = pydirectinput

    def tap(self, key: str, hold_ms: int) -> None:
        self._pydirectinput.keyDown(key)
        time.sleep(hold_ms / 1000)
        self._pydirectinput.keyUp(key)


class DryRunKeyboard:
    def __init__(self, clock: Any = None, console: Any = None) -> None:
        self._clock = clock or time.monotonic
        self._console = console
        self.presses: list[tuple[float, str]] = []

    def set_console(self, console: Any) -> None:
        self._console = console

    def tap(self, key: str, hold_ms: int) -> None:
        t = self._clock()
        self.presses.append((t, key))
        if self._console is not None:
            self._console.log(f"[dry-run] tap {key} ({hold_ms}ms)")


class Actions:
    def __init__(
        self,
        kb: Keyboard,
        guard: FocusGuard,
        cfg: InputConfig,
        rng: random.Random | None = None,
    ) -> None:
        self._kb = kb
        self._guard = guard
        self._cfg = cfg
        self._rng = rng if rng is not None else random.Random(cfg.rng_seed or None)

    def _jitter(self) -> None:
        delay = self._rng.uniform(0, self._cfg.jitter_ms / 1000)
        if delay > 0:
            time.sleep(delay)

    def cast(self) -> bool:
        if not self._guard.allowed():
            return False
        self._jitter()
        self._kb.tap(self._cfg.cast_key, self._cfg.key_hold_ms)
        return True

    def loot(self) -> bool:
        if not self._guard.allowed():
            return False
        self._jitter()
        self._kb.tap(self._cfg.loot_key, self._cfg.key_hold_ms)
        return True

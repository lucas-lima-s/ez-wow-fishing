from __future__ import annotations

import ctypes
import sys

import psutil


def foreground_process_name() -> str | None:
    if sys.platform != "win32":
        return None
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    try:
        return psutil.Process(pid.value).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def foreground_window_title() -> str:
    if sys.platform != "win32":
        return ""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


class FocusGuard:
    def __init__(self, process_name: str, title_contains: str, enabled: bool) -> None:
        self._process_name = process_name.lower()
        self._title_contains = title_contains
        self._enabled = enabled

    def allowed(self) -> bool:
        if not self._enabled:
            return True
        name = foreground_process_name()
        if name is None or name.lower() != self._process_name:
            return False
        if self._title_contains:
            title = foreground_window_title()
            if self._title_contains not in title:
                return False
        return True

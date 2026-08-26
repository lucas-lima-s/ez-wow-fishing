from __future__ import annotations

import pytest

from wow_ez_fishing import window


def test_guard_disabled_is_always_allowed() -> None:
    guard = window.FocusGuard("Wow.exe", "World of Warcraft", enabled=False)
    assert guard.allowed() is True


def test_guard_allows_matching_process_and_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "foreground_process_name", lambda: "Wow.exe")
    monkeypatch.setattr(window, "foreground_window_title", lambda: "World of Warcraft")
    guard = window.FocusGuard("Wow.exe", "World of Warcraft", enabled=True)
    assert guard.allowed() is True


def test_guard_rejects_wrong_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "foreground_process_name", lambda: "explorer.exe")
    monkeypatch.setattr(window, "foreground_window_title", lambda: "World of Warcraft")
    guard = window.FocusGuard("Wow.exe", "World of Warcraft", enabled=True)
    assert guard.allowed() is False


def test_guard_rejects_wrong_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "foreground_process_name", lambda: "Wow.exe")
    monkeypatch.setattr(window, "foreground_window_title", lambda: "Notepad")
    guard = window.FocusGuard("Wow.exe", "World of Warcraft", enabled=True)
    assert guard.allowed() is False


def test_guard_skips_title_check_when_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "foreground_process_name", lambda: "Wow.exe")
    monkeypatch.setattr(window, "foreground_window_title", lambda: "anything at all")
    guard = window.FocusGuard("Wow.exe", "", enabled=True)
    assert guard.allowed() is True


def test_guard_process_match_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "foreground_process_name", lambda: "WOW.EXE")
    monkeypatch.setattr(window, "foreground_window_title", lambda: "World of Warcraft")
    guard = window.FocusGuard("Wow.exe", "World of Warcraft", enabled=True)
    assert guard.allowed() is True


def test_guard_returns_false_when_no_foreground_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "foreground_process_name", lambda: None)
    guard = window.FocusGuard("Wow.exe", "World of Warcraft", enabled=True)
    assert guard.allowed() is False

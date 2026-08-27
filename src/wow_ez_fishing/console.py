from __future__ import annotations

from collections import deque

from rich.console import Console as RichConsole
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from wow_ez_fishing.bot import FishingBot


class ConsoleUI:
    def __init__(
        self,
        bot: FishingBot,
        refresh_hz: int = 8,
        record: bool = False,
        color: bool = True,
    ) -> None:
        self._bot = bot
        self._refresh_hz = refresh_hz
        self._console = RichConsole(record=record, no_color=not color)
        self._events: deque[str] = deque(maxlen=5)
        self._live: Live | None = None

    def log(self, message: str) -> None:
        self._events.append(message)

    def print_line(self, text: str) -> None:
        self._console.print(text)

    def _render(self) -> Panel:
        bot = self._bot
        stats = bot.stats()
        detector = bot.detector
        table = Table.grid(padding=(0, 1))
        table.add_column(justify="left", style="bold")
        table.add_column(justify="right")
        table.add_row("State", bot.state.value)
        table.add_row("Elapsed (s)", f"{stats['elapsed_s']:.1f}")
        table.add_row("Baseline (dB)", f"{bot.baseline_db:.1f}")
        band_db = getattr(detector, "last_band_db", 0.0)
        margin = bot.cfg.detection.trigger_margin_db
        table.add_row("Band / margin (dB)", f"{band_db:.1f} / {margin:.1f}")
        table.add_row("Casts", str(stats["casts"]))
        table.add_row("Catches", str(stats["catches"]))
        table.add_row("Misses", str(stats["misses"]))
        table.add_row("Gated", str(stats["gated"]))
        table.add_row("Dropped frames", str(stats["dropped_frames"]))
        table.add_row("Focus", "ok" if bot.guard.allowed() else "blocked")
        table.add_row(
            "Hotkeys",
            f"pause={bot.cfg.hotkeys.pause} stop={bot.cfg.hotkeys.stop}",
        )
        events_text = "\n".join(self._events) or "(none yet)"
        return Panel.fit(table, title="ez-wow-fishing", subtitle=events_text)

    def start(self) -> None:
        self._live = Live(
            self._render(), console=self._console, refresh_per_second=self._refresh_hz
        )
        self._live.start()

    def refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())
        else:
            self._console.print(self._render())

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def save_svg(self, path: str, title: str) -> None:
        self._console.save_svg(path, title=title)

    def export_text(self, clear: bool = False) -> str:
        return self._console.export_text(clear=clear)

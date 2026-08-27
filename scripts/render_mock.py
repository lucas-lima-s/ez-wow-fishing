from __future__ import annotations

import argparse
import random
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_demo_wav import SAMPLE_RATE, _choose_splash_times, _write_wav, generate

from wow_ez_fishing.audio.wavfile import WavFileSource
from wow_ez_fishing.bot import FishingBot
from wow_ez_fishing.config import AppConfig
from wow_ez_fishing.console import ConsoleUI
from wow_ez_fishing.detector import SplashDetector
from wow_ez_fishing.input import Actions, DryRunKeyboard
from wow_ez_fishing.window import FocusGuard

CAPTION = "Synthetic demo - audio from a generated WAV, no live game"
SVG_TITLE = "ez-wow-fishing - synthetic demo (mock)"


class NullMeter:
    available = False

    def recent_peak(self) -> float:
        return 0.0

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def _build_demo_wav(path: Path, seed: int = 7, seconds: float = 20.0) -> None:
    rng = np.random.default_rng(seed)
    splash_times = _choose_splash_times(seconds, 4, rng)
    signal = generate(seconds, splash_times, seed, distractors=True)
    _write_wav(path, signal, SAMPLE_RATE)


def _load_font(size: int = 14) -> ImageFont.FreeTypeFont:
    for name in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_png(text: str, out_path: Path) -> None:
    lines = text.splitlines() or [text]
    font = _load_font(14)
    line_height = 18
    char_width = 9
    width = max(900, max((len(line) for line in lines), default=40) * char_width + 40)
    height = line_height * (len(lines) + 3)
    image = Image.new("RGB", (width, height), color=(13, 17, 23))
    draw = ImageDraw.Draw(image)
    y = 12
    for line in lines:
        draw.text((16, y), line, fill=(201, 209, 217), font=font)
        y += line_height
    image.save(out_path)


def render(out_prefix: Path) -> None:
    cfg = AppConfig()
    cfg = replace(
        cfg,
        input=replace(cfg.input, rng_seed=7, jitter_ms=0, cast_to_arm_s=0.2, recast_delay_s=0.1),
        bot=replace(cfg.bot, require_focus=False, max_casts=4),
    )

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "mock.wav"
        _build_demo_wav(wav_path)

        source = WavFileSource(wav_path, hop_size=cfg.detection.hop_size)
        clock = lambda: source.elapsed_s  # noqa: E731
        detector = SplashDetector(cfg.detection, source.sample_rate)
        guard = FocusGuard(cfg.audio.process_name, cfg.bot.window_title_contains, False)

        kb = DryRunKeyboard(clock=clock)
        actions = Actions(kb, guard, cfg.input, rng=random.Random(cfg.input.rng_seed))
        meter = NullMeter()

        bot = FishingBot(source, detector, actions, guard, meter, cfg, clock=clock)
        console = ConsoleUI(bot, cfg.ui.refresh_hz, record=True, color=True)
        kb.set_console(console)

        bot.run()
        console.refresh()
        console.print_line(CAPTION)

        out_prefix.parent.mkdir(parents=True, exist_ok=True)
        svg_path = out_prefix.with_suffix(".svg")
        png_path = out_prefix.with_suffix(".png")

        text = console.export_text()
        console.save_svg(str(svg_path), title=SVG_TITLE)
        _render_png(text, png_path)

        print(f"wrote {svg_path} and {png_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a synthetic console mock screenshot.")
    parser.add_argument("--out", type=Path, default=Path("docs/images/console-mock"))
    args = parser.parse_args(argv)
    render(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

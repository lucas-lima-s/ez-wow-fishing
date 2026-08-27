from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from wow_ez_fishing.audio.wavfile import WavFileSource
from wow_ez_fishing.bot import FishingBot
from wow_ez_fishing.config import AppConfig, AudioConfig, DetectionConfig, load_config
from wow_ez_fishing.console import ConsoleUI
from wow_ez_fishing.detector import SplashDetector
from wow_ez_fishing.errors import AudioDeviceError, ConfigError
from wow_ez_fishing.hotkeys import HotkeyListener
from wow_ez_fishing.input import Actions, DirectInputKeyboard, DryRunKeyboard
from wow_ez_fishing.window import FocusGuard

COMMANDS = {"run", "devices", "calibrate", "analyze", "doctor"}


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return ["run"]
    if argv[0] in COMMANDS or argv[0] in ("-h", "--help"):
        return list(argv)
    return ["run", *argv]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ez-wow-fishing")
    subparsers = parser.add_subparsers(dest="command")

    run_p = subparsers.add_parser("run", help="run the fishing bot")
    run_p.add_argument("--config", type=Path, default=None)
    run_p.add_argument("--source", default="auto")
    run_p.add_argument("--backend", default=None, choices=["hybrid", "loopback", "session_meter"])
    run_p.add_argument("--cast-key", default=None)
    run_p.add_argument("--loot-key", default=None)
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--ignore-focus", action="store_true")
    run_p.add_argument("--json-summary", action="store_true")
    run_p.add_argument("--verbose", action="store_true")

    devices_p = subparsers.add_parser("devices", help="list WASAPI loopback devices")
    devices_p.add_argument("--json", action="store_true")

    calibrate_p = subparsers.add_parser("calibrate", help="measure the ambient noise baseline")
    calibrate_p.add_argument("--seconds", type=float, default=5.0)
    calibrate_p.add_argument("--json", action="store_true")

    analyze_p = subparsers.add_parser("analyze", help="run the detector offline over a WAV file")
    analyze_p.add_argument("wav", type=Path)
    analyze_p.add_argument("--config", type=Path, default=None)
    analyze_p.add_argument("--json", action="store_true")
    analyze_p.add_argument("--truth", type=Path, default=None)
    analyze_p.add_argument("--tolerance-ms", type=float, default=150.0)

    doctor_p = subparsers.add_parser("doctor", help="check the runtime environment")
    doctor_p.add_argument("--no-fail-on-device", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:]) if argv is None else list(argv)
    parser = _build_parser()
    args = parser.parse_args(_normalize_argv(raw_argv))
    command = args.command or "run"

    try:
        if command == "run":
            return _cmd_run(args)
        if command == "devices":
            return _cmd_devices(args)
        if command == "calibrate":
            return _cmd_calibrate(args)
        if command == "analyze":
            return _cmd_analyze(args)
        if command == "doctor":
            return _cmd_doctor(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    except AudioDeviceError as exc:
        print(f"audio device error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


def _build_source(source_arg: str, audio_cfg: AudioConfig, detection_cfg: DetectionConfig) -> Any:
    if source_arg.startswith("wav:"):
        path = source_arg[len("wav:") :]
        return WavFileSource(path, hop_size=detection_cfg.hop_size)
    from wow_ez_fishing.audio.loopback import LoopbackSource

    return LoopbackSource(audio_cfg)


def _build_meter(audio_cfg: AudioConfig) -> Any:
    from wow_ez_fishing.audio.session_meter import SessionMeter

    return SessionMeter(audio_cfg)


def _describe_session(process_name: str) -> str:
    try:
        from pycaw.utils import AudioUtilities
    except ImportError:
        return "pycaw not available"
    try:
        for session in AudioUtilities.GetAllSessions():
            proc = session.Process
            if proc and proc.name().lower() == process_name.lower():
                return f"{process_name} session active"
    except Exception:
        return "session query failed"
    return f"{process_name} session not found"


def _apply_run_overrides(cfg: AppConfig, args: argparse.Namespace) -> AppConfig:
    audio = cfg.audio
    if args.backend:
        audio = replace(audio, backend=args.backend)
    elif args.source == "session":
        audio = replace(audio, backend="session_meter")
    elif args.source == "loopback":
        audio = replace(audio, backend="loopback")
    cfg = replace(cfg, audio=audio)

    input_cfg = cfg.input
    if args.cast_key:
        input_cfg = replace(input_cfg, cast_key=args.cast_key)
    if args.loot_key:
        input_cfg = replace(input_cfg, loot_key=args.loot_key)
    cfg = replace(cfg, input=input_cfg)

    if args.ignore_focus:
        cfg = replace(cfg, bot=replace(cfg.bot, require_focus=False))

    return cfg


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cfg = _apply_run_overrides(cfg, args)

    source = _build_source(args.source, cfg.audio, cfg.detection)
    clock = (lambda s=source: s.elapsed_s) if hasattr(source, "elapsed_s") else time.monotonic

    detector = SplashDetector(cfg.detection, source.sample_rate)
    guard = FocusGuard(cfg.audio.process_name, cfg.bot.window_title_contains, cfg.bot.require_focus)

    kb = DryRunKeyboard(clock=clock) if args.dry_run else DirectInputKeyboard()
    actions = Actions(kb, guard, cfg.input)
    meter = _build_meter(cfg.audio)

    bot = FishingBot(source, detector, actions, guard, meter, cfg, clock=clock)

    hotkeys = HotkeyListener(bot.pause, bot.request_stop, cfg.hotkeys)
    hotkeys.start()

    ui = None if args.json_summary else ConsoleUI(bot, cfg.ui.refresh_hz, color=cfg.ui.color)

    source.start()
    meter.start()
    if ui is not None:
        ui.start()
    try:
        stats = bot.run()
    finally:
        hotkeys.stop()
        meter.stop()
        if ui is not None:
            ui.stop()

    if args.json_summary:
        print(json.dumps(stats))
    else:
        print(
            f"casts={stats['casts']} catches={stats['catches']} "
            f"misses={stats['misses']} gated={stats['gated']} "
            f"dropped_frames={stats['dropped_frames']}"
        )
    return 0


def _cmd_devices(args: argparse.Namespace) -> int:
    from wow_ez_fishing.audio.devices import list_loopback_devices

    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        print("pyaudiowpatch is not installed on this platform.", file=sys.stderr)
        return 1

    try:
        pa = pyaudio.PyAudio()
    except Exception as exc:
        print(f"could not initialize the audio backend: {exc}", file=sys.stderr)
        return 1

    try:
        try:
            pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            wasapi_available = True
        except OSError:
            wasapi_available = False

        try:
            devices = list_loopback_devices(pa) if wasapi_available else []
        except Exception:
            devices = []

        payload = {
            "wasapi_available": wasapi_available,
            "loopback_devices": [
                {
                    "index": d["index"],
                    "name": d["name"],
                    "sample_rate": d["defaultSampleRate"],
                    "channels": d["maxInputChannels"],
                }
                for d in devices
            ],
            "session": _describe_session("Wow.exe"),
        }
    finally:
        pa.terminate()

    if args.json:
        print(json.dumps(payload))
    else:
        print(f"WASAPI available: {payload['wasapi_available']}")
        for d in payload["loopback_devices"]:
            print(f"  [{d['index']}] {d['name']} ({d['sample_rate']} Hz, {d['channels']} ch)")
        print(f"session: {payload['session']}")

    if not payload["loopback_devices"]:
        print("no loopback devices were found on this system.", file=sys.stderr)
        return 1
    return 0


def _octave_band_table(samples: np.ndarray, sample_rate: int) -> list[tuple[float, float, float]]:
    n = len(samples)
    if n == 0:
        return []
    window = np.hanning(n)
    spec = np.abs(np.fft.rfft(samples * window))
    freqs = np.fft.rfftfreq(n, 1 / sample_rate)
    bands: list[tuple[float, float, float]] = []
    low = 31.25
    nyquist = sample_rate / 2
    while low < nyquist:
        high = min(low * 2, nyquist)
        mask = (freqs >= low) & (freqs < high)
        energy = np.sqrt(np.mean(spec[mask] ** 2)) if mask.any() else 0.0
        bands.append((low, high, float(20 * np.log10(energy + 1e-12))))
        low = high
    return bands


def _cmd_calibrate(args: argparse.Namespace) -> int:
    from wow_ez_fishing.audio.loopback import LoopbackSource

    cfg = load_config(None)
    source = LoopbackSource(cfg.audio)
    source.start()
    try:
        detector = SplashDetector(cfg.detection, source.sample_rate)
        remaining = args.seconds
        chunks: list[np.ndarray] = []
        deadline = time.monotonic() + remaining
        while time.monotonic() < deadline:
            frame = source.read(timeout=0.5)
            if frame is not None:
                chunks.append(frame)
        ambient = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        baseline = detector.prime(ambient) if len(ambient) else 0.0
    finally:
        source.stop()

    bands = _octave_band_table(ambient, source.sample_rate)
    payload = {
        "baseline_db": baseline,
        "suggested_trigger_margin_db": cfg.detection.trigger_margin_db,
        "bands": bands,
    }

    if args.json:
        print(json.dumps(payload))
    else:
        print(f"baseline: {baseline:.1f} dB")
        print(f"suggested trigger_margin_db: {cfg.detection.trigger_margin_db:.1f}")
        for low, high, db in bands:
            print(f"  {low:>6.0f}-{high:<6.0f} Hz: {db:6.1f} dB")
    return 0


def _run_detector_over_wav(path: Path, cfg: AppConfig) -> tuple[list[Any], int]:
    from dataclasses import replace as dc_replace

    source = WavFileSource(path, hop_size=cfg.detection.hop_size)
    detector = SplashDetector(cfg.detection, source.sample_rate)

    calib_target = cfg.detection.calibration_seconds
    ambient_chunks: list[np.ndarray] = []
    ambient_seconds = 0.0
    while ambient_seconds < calib_target:
        frame = source.read()
        if frame is None:
            break
        ambient_chunks.append(frame)
        ambient_seconds += len(frame) / source.sample_rate
    ambient = np.concatenate(ambient_chunks) if ambient_chunks else np.zeros(0, dtype=np.float32)
    detector.prime(ambient)

    events = []
    while True:
        frame = source.read()
        if frame is None:
            break
        for event in detector.push(frame):
            events.append(dc_replace(event, t=event.t + ambient_seconds))
    source.stop()
    return events, source.sample_rate


def _match_events(detected: list[float], truth: list[float], tolerance_s: float) -> tuple[int, int]:
    remaining = list(detected)
    matched = 0
    for t in truth:
        best = None
        for d in remaining:
            if abs(d - t) <= tolerance_s and (best is None or abs(d - t) < abs(best - t)):
                best = d
        if best is not None:
            matched += 1
            remaining.remove(best)
    return matched, len(remaining)


def _cmd_analyze(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    events, sample_rate = _run_detector_over_wav(args.wav, cfg)
    event_times = [round(e.t, 3) for e in events]

    result: dict[str, Any] = {"events_s": event_times, "sample_rate": sample_rate}

    if args.truth is not None:
        truth = json.loads(Path(args.truth).read_text())
        truth_times = list(truth["events_s"])
        tolerance_s = args.tolerance_ms / 1000
        matched, false_positives = _match_events(event_times, truth_times, tolerance_s)
        result["matched"] = matched
        result["expected"] = len(truth_times)
        result["false_positives"] = false_positives
        ok = matched == len(truth_times) and false_positives == 0

        if args.json:
            print(json.dumps(result))
        else:
            print(f"detected {len(event_times)} events: {event_times}")
            print(f"matched {matched}/{len(truth_times)}, false positives {false_positives}")
        return 0 if ok else 1

    if args.json:
        print(json.dumps(result))
    else:
        print(f"detected {len(event_times)} events: {event_times}")
    return 0


def _is_process_elevated() -> bool | None:
    if sys.platform != "win32":
        return None
    import ctypes

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return None


def _cmd_doctor(args: argparse.Namespace) -> int:
    ok = True
    lines = [f"python: {sys.version.split()[0]}", f"platform: {sys.platform}"]

    wasapi_available = False
    device_ok = False
    device_info: str | None = None

    if sys.platform == "win32":
        try:
            import pyaudiowpatch as pyaudio

            pa = pyaudio.PyAudio()
            try:
                try:
                    pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                    wasapi_available = True
                except OSError:
                    wasapi_available = False

                if wasapi_available:
                    from wow_ez_fishing.audio.devices import resolve_loopback_device

                    try:
                        device = resolve_loopback_device(pa, "")
                        device_ok = True
                        device_info = device["name"]
                    except AudioDeviceError as exc:
                        device_info = str(exc)
            finally:
                pa.terminate()
        except ImportError:
            lines.append("pyaudiowpatch: not installed")
    else:
        lines.append("pyaudiowpatch: skipped (not Windows)")

    lines.append(f"WASAPI available: {wasapi_available}")
    lines.append(f"loopback device: {device_info if device_info else 'not resolved'}")

    if not device_ok and not args.no_fail_on_device:
        ok = False

    lines.append(f"Wow.exe session: {_describe_session('Wow.exe')}")

    try:
        import pydirectinput  # noqa: F401

        lines.append("pydirectinput: available")
    except ImportError:
        lines.append("pydirectinput: not available")
        ok = False

    try:
        import pynput  # noqa: F401

        lines.append("pynput: available")
    except ImportError:
        lines.append("pynput: not available (hotkeys disabled)")

    elevated = _is_process_elevated()
    if elevated is True:
        lines.append("elevation: this process is elevated")
    elif elevated is False:
        lines.append(
            "elevation: this process is NOT elevated. "
            "If WoW runs elevated, run this bot elevated too."
        )
    else:
        lines.append("elevation: unknown (not Windows)")

    for line in lines:
        print(line)

    return 0 if ok else 1

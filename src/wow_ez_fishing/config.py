from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Literal

from wow_ez_fishing.errors import ConfigError


@dataclass(frozen=True)
class AudioConfig:
    backend: Literal["hybrid", "loopback", "session_meter"] = "hybrid"
    device_name: str = ""
    sample_rate: int = 0
    frame_size: int = 1024
    queue_frames: int = 64
    process_name: str = "Wow.exe"
    session_gate_peak: float = 0.05
    session_poll_hz: int = 20


@dataclass(frozen=True)
class DetectionConfig:
    band_low_hz: float = 500.0
    band_high_hz: float = 4000.0
    window_size: int = 2048
    hop_size: int = 1024
    calibration_seconds: float = 3.0
    trigger_margin_db: float = 12.0
    onset_db: float = 6.0
    onset_lookback_frames: int = 4
    min_event_frames: int = 2
    refractory_s: float = 3.0
    baseline_alpha: float = 0.02
    baseline_freeze_margin_db: float = 6.0


@dataclass(frozen=True)
class InputConfig:
    cast_key: str = "1"
    loot_key: str = "3"
    key_hold_ms: int = 60
    loot_delay_ms: int = 120
    cast_to_arm_s: float = 1.5
    post_loot_s: float = 1.2
    recast_delay_s: float = 0.8
    jitter_ms: int = 80
    rng_seed: int = 0


@dataclass(frozen=True)
class BotConfig:
    max_wait_s: float = 25.0
    require_focus: bool = True
    window_title_contains: str = "World of Warcraft"
    max_casts: int = 0
    stop_after_minutes: float = 0


@dataclass(frozen=True)
class HotkeyConfig:
    pause: str = "<f9>"
    stop: str = "<f10>"


@dataclass(frozen=True)
class UiConfig:
    refresh_hz: int = 8
    log_file: str = ""
    color: bool = True


@dataclass(frozen=True)
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    input: InputConfig = field(default_factory=InputConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    ui: UiConfig = field(default_factory=UiConfig)


_SECTION_TYPES: dict[str, type] = {
    "audio": AudioConfig,
    "detection": DetectionConfig,
    "input": InputConfig,
    "bot": BotConfig,
    "hotkeys": HotkeyConfig,
    "ui": UiConfig,
}


def _is_power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


def load_config(path: Path | None) -> AppConfig:
    cfg = AppConfig()
    if path is not None:
        data = _read_toml(path)
        cfg = _apply_overrides(cfg, data)
    _validate(cfg)
    return cfg


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML syntax in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc


def _apply_overrides(cfg: AppConfig, data: dict[str, Any]) -> AppConfig:
    section_updates: dict[str, Any] = {}
    for section_name, section_data in data.items():
        if section_name not in _SECTION_TYPES:
            raise ConfigError(f"unknown config section '{section_name}'")
        if not isinstance(section_data, dict):
            raise ConfigError(f"config section '{section_name}' must be a table")
        section_cls = _SECTION_TYPES[section_name]
        current = getattr(cfg, section_name)
        valid_keys = {f.name for f in fields(section_cls)}
        for key in section_data:
            if key not in valid_keys:
                raise ConfigError(f"unknown config key '{section_name}.{key}'")
        section_updates[section_name] = replace(current, **section_data)
    return replace(cfg, **section_updates)


def _validate(cfg: AppConfig) -> None:
    audio = cfg.audio
    detection = cfg.detection

    if not (detection.band_low_hz < detection.band_high_hz):
        raise ConfigError("detection.band_high_hz must be greater than detection.band_low_hz")
    if audio.sample_rate:
        nyquist = audio.sample_rate / 2
        if not (detection.band_high_hz < nyquist):
            raise ConfigError(
                "detection.band_high_hz must be below Nyquist (audio.sample_rate / 2)"
            )
    if detection.hop_size > detection.window_size:
        raise ConfigError("detection.hop_size must be <= detection.window_size")
    if not _is_power_of_two(detection.window_size):
        raise ConfigError("detection.window_size must be a power of two")
    if not _is_power_of_two(detection.hop_size):
        raise ConfigError("detection.hop_size must be a power of two")

    positive_durations = {
        "detection.calibration_seconds": detection.calibration_seconds,
        "detection.refractory_s": detection.refractory_s,
        "input.cast_to_arm_s": cfg.input.cast_to_arm_s,
        "input.post_loot_s": cfg.input.post_loot_s,
        "input.recast_delay_s": cfg.input.recast_delay_s,
        "input.key_hold_ms": cfg.input.key_hold_ms,
        "input.loot_delay_ms": cfg.input.loot_delay_ms,
        "bot.max_wait_s": cfg.bot.max_wait_s,
        "ui.refresh_hz": cfg.ui.refresh_hz,
    }
    for name, value in positive_durations.items():
        if value <= 0:
            raise ConfigError(f"{name} must be greater than zero")

from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path

import pytest

from wow_ez_fishing.config import (
    AudioConfig,
    BotConfig,
    DetectionConfig,
    HotkeyConfig,
    InputConfig,
    UiConfig,
    load_config,
)
from wow_ez_fishing.errors import ConfigError

SECTION_TYPES = {
    "audio": AudioConfig,
    "detection": DetectionConfig,
    "input": InputConfig,
    "bot": BotConfig,
    "hotkeys": HotkeyConfig,
    "ui": UiConfig,
}


def test_config_defaults() -> None:
    cfg = load_config(None)
    assert cfg.audio.backend == "hybrid"
    assert cfg.audio.device_name == ""
    assert cfg.detection.band_low_hz == 500.0
    assert cfg.detection.band_high_hz == 4000.0
    assert cfg.input.cast_key == "1"
    assert cfg.bot.max_wait_s == 25.0
    assert cfg.hotkeys.pause == "<f9>"
    assert cfg.ui.refresh_hz == 8


def test_config_toml_override(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[audio]
device_name = "Speakers"
backend = "loopback"

[detection]
band_low_hz = 400.0
band_high_hz = 3000.0
"""
    )
    cfg = load_config(config_path)
    assert cfg.audio.device_name == "Speakers"
    assert cfg.audio.backend == "loopback"
    assert cfg.detection.band_low_hz == 400.0
    assert cfg.detection.band_high_hz == 3000.0
    assert cfg.input.cast_key == "1"


def test_config_rejects_unknown_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[audio]
not_a_real_key = 1
"""
    )
    with pytest.raises(ConfigError):
        load_config(config_path)


def test_config_rejects_band_above_nyquist(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[audio]
sample_rate = 8000

[detection]
band_high_hz = 5000.0
"""
    )
    with pytest.raises(ConfigError):
        load_config(config_path)


def test_example_toml_parses_and_matches_dataclass_keys() -> None:
    example_path = Path(__file__).resolve().parent.parent / "config.example.toml"
    with example_path.open("rb") as handle:
        data = tomllib.load(handle)

    assert set(data.keys()) == set(SECTION_TYPES.keys())

    for section_name, section_cls in SECTION_TYPES.items():
        dataclass_keys = {f.name for f in fields(section_cls)}
        toml_keys = set(data[section_name].keys())
        assert toml_keys == dataclass_keys, section_name

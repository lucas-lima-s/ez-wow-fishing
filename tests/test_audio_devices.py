from __future__ import annotations

import pytest

from wow_ez_fishing.config import AudioConfig
from wow_ez_fishing.errors import AudioDeviceError

DEVICES = [
    {
        "index": 0,
        "name": "Speakers (Realtek)",
        "isLoopbackDevice": False,
        "maxInputChannels": 0,
        "defaultSampleRate": 48000.0,
    },
    {
        "index": 1,
        "name": "Speakers (Realtek) [Loopback]",
        "isLoopbackDevice": True,
        "maxInputChannels": 2,
        "defaultSampleRate": 48000.0,
    },
    {
        "index": 2,
        "name": "Headset [Loopback]",
        "isLoopbackDevice": True,
        "maxInputChannels": 2,
        "defaultSampleRate": 48000.0,
    },
]


class _FakeStream:
    def start_stream(self) -> None:
        pass

    def stop_stream(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakePyAudio:
    def __init__(self, devices: list[dict], default_output_index: int = 0) -> None:
        self._devices = devices
        self._default_output_index = default_output_index
        self.host_api_calls = 0
        self.device_info_calls = 0
        self.loopback_generator_calls = 0

    def get_host_api_info_by_type(self, api_type: object) -> dict:
        self.host_api_calls += 1
        return {"defaultOutputDevice": self._default_output_index}

    def get_device_info_by_index(self, index: int) -> dict:
        self.device_info_calls += 1
        for device in self._devices:
            if device["index"] == index:
                return device
        raise OSError(-9996, "Invalid device info")

    def get_loopback_device_info_generator(self):
        self.loopback_generator_calls += 1
        return iter([d for d in self._devices if d.get("isLoopbackDevice")])

    def open(self, **kwargs: object) -> _FakeStream:
        return _FakeStream()

    def terminate(self) -> None:
        pass


@pytest.mark.windows_only
def test_resolve_loopback_device_matches_default_speakers() -> None:
    from wow_ez_fishing.audio.devices import resolve_loopback_device

    pa = FakePyAudio(list(DEVICES))
    device = resolve_loopback_device(pa, "")
    assert device["name"] == "Speakers (Realtek) [Loopback]"


@pytest.mark.windows_only
def test_resolve_loopback_device_matches_by_name_substring() -> None:
    from wow_ez_fishing.audio.devices import resolve_loopback_device

    pa = FakePyAudio(list(DEVICES))
    device = resolve_loopback_device(pa, "headset")
    assert device["name"] == "Headset [Loopback]"


@pytest.mark.windows_only
def test_resolve_loopback_device_raises_when_nothing_matches() -> None:
    from wow_ez_fishing.audio.devices import resolve_loopback_device

    pa = FakePyAudio(list(DEVICES))
    with pytest.raises(AudioDeviceError):
        resolve_loopback_device(pa, "nonexistent")


@pytest.mark.windows_only
def test_resolve_loopback_device_raises_when_no_default_output_device() -> None:
    from wow_ez_fishing.audio.devices import resolve_loopback_device

    pa = FakePyAudio(list(DEVICES), default_output_index=-1)
    with pytest.raises(AudioDeviceError):
        resolve_loopback_device(pa, "")


@pytest.mark.windows_only
def test_list_loopback_devices_returns_only_loopback_entries() -> None:
    from wow_ez_fishing.audio.devices import list_loopback_devices

    pa = FakePyAudio(list(DEVICES))
    devices = list_loopback_devices(pa)
    assert len(devices) == 2
    assert all(d["isLoopbackDevice"] for d in devices)


@pytest.mark.windows_only
def test_device_resolved_once() -> None:
    from wow_ez_fishing.audio.loopback import LoopbackSource

    pa = FakePyAudio(list(DEVICES))
    cfg = AudioConfig(device_name="", queue_frames=4)
    source = LoopbackSource(cfg, pa=pa)

    for _ in range(3):
        source.start()
        source.stop()

    assert pa.loopback_generator_calls == 1

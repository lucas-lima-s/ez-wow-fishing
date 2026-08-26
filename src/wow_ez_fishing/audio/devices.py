from __future__ import annotations

from typing import Any

from wow_ez_fishing.errors import AudioDeviceError


def list_loopback_devices(p: Any) -> list[dict]:
    return list(p.get_loopback_device_info_generator())


def resolve_loopback_device(p: Any, device_name: str) -> dict:
    import pyaudiowpatch as pyaudio

    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError as exc:
        raise AudioDeviceError("WASAPI host API is not available on this system") from exc

    if device_name:
        for loopback in p.get_loopback_device_info_generator():
            if device_name.lower() in loopback["name"].lower():
                return loopback
        available = [d["name"] for d in p.get_loopback_device_info_generator()]
        raise AudioDeviceError(
            f"no loopback device matches '{device_name}'. Available devices: {available}"
        )

    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    if not default_speakers.get("isLoopbackDevice"):
        for loopback in p.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                return loopback
        available = [d["name"] for d in p.get_loopback_device_info_generator()]
        raise AudioDeviceError(
            f"no loopback device found for default output device "
            f"'{default_speakers['name']}'. Available devices: {available}"
        )
    return default_speakers

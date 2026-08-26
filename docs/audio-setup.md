# Audio setup (driverless)

wow-ez-fishing captures system audio through WASAPI loopback, a feature built into
Windows 10 and 11. It needs **no driver and no special recording device at all** — the
capture path is entirely pip-installable (`PyAudioWPatch`, a PortAudio fork with WASAPI
loopback support).

## Verifying loopback works on your machine

```bash
uv run wow-ez-fishing devices
```

This lists every WASAPI loopback-capable device Windows exposes, plus whether a
`Wow.exe` audio session is currently visible in the Volume Mixer. If the list is empty,
WASAPI itself is unavailable (very old Windows, or an unusual audio driver stack) — there
is no fallback path in this project; the loopback capture is the only capture path.

## How the default device is picked

With `device_name = ""` (the default), the bot resolves your **current default output
device** (whatever you'd hear through) and asks Windows for its loopback counterpart.
This happens once at startup, not on every audio poll.

If you use multiple outputs (headset + speakers, a virtual mixing app, etc.) and want to
pin capture to a specific one regardless of which is currently default, set
`device_name` to a substring of its name, e.g.:

```toml
[audio]
device_name = "Realtek"
```

Run `wow-ez-fishing devices` to see the exact names Windows reports.

## Switching outputs mid-session

If you change your default output device (plug in a headset, switch to a Bluetooth
speaker) while the bot is running, the already-open loopback stream keeps capturing the
*old* device. Restart the bot after switching outputs so it re-resolves the new default.

## Why the per-process gate exists

Loopback capture hears everything mixed into your speakers: the game, Discord, Spotify,
a browser tab. The default `backend = "hybrid"` adds a second, independent signal — a
per-process volume peak read via `pycaw` for the process named in `audio.process_name`
(default `Wow.exe`). A detected splash only counts if the game's own audio session was
also making noise at that moment, which kills the most common driverless failure mode:
music or a notification sound in the same frequency band as a splash.

To confirm the game shows up as its own mixer session, right-click the speaker icon in
the Windows taskbar → **Open Volume Mixer** and look for World of Warcraft while it is
running with sound enabled.

## Exclusive mode caveat

If WoW (or another application) opens the default audio endpoint in **exclusive mode**,
Windows blocks every other client — including loopback capture — from reading it. If
`devices` shows no loopback device while the game is running with audio previously
working fine outside the game, check the endpoint's *Advanced* tab in
**Sound Control Panel → Playback → (device) → Properties → Advanced** and make sure
"Allow applications to take exclusive control of this device" reflects your setup, or
switch the game's audio output to shared mode if it exposes that option.

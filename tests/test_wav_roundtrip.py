from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from wow_ez_fishing.cli import _run_detector_over_wav
from wow_ez_fishing.config import AppConfig

REPO_ROOT = Path(__file__).resolve().parent.parent


def _generate_demo(tmp_path: Path, seed: int = 7) -> tuple[Path, dict]:
    out = tmp_path / "demo.wav"
    script = REPO_ROOT / "scripts" / "generate_demo_wav.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--out",
            str(out),
            "--seconds",
            "30",
            "--splashes",
            "4",
            "--seed",
            str(seed),
            "--distractors",
        ],
        check=True,
        cwd=REPO_ROOT,
    )
    truth_path = out.with_name(out.stem + ".truth.json")
    return out, json.loads(truth_path.read_text())


def _match(detected: list[float], truth: list[float], tolerance_s: float) -> tuple[int, int]:
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


def test_wav_roundtrip_all_events(tmp_path: Path) -> None:
    wav_path, truth = _generate_demo(tmp_path)
    cfg = AppConfig()

    events, _sample_rate = _run_detector_over_wav(wav_path, cfg)
    detected = [e.t for e in events]

    matched, false_positives = _match(detected, truth["events_s"], tolerance_s=0.15)

    assert matched == 4
    assert false_positives == 0

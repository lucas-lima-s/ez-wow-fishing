from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _generate_demo(tmp_path: Path, seed: int = 7) -> tuple[Path, Path]:
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
    truth = out.with_name(out.stem + ".truth.json")
    return out, truth


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "wow_ez_fishing", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_cli_analyze_truth_exit_codes(tmp_path: Path) -> None:
    wav_path, truth_path = _generate_demo(tmp_path)

    good = _run_cli(["analyze", str(wav_path), "--truth", str(truth_path), "--tolerance-ms", "150"])
    assert good.returncode == 0, good.stdout + good.stderr
    assert "matched 4/4" in good.stdout
    assert "false positives 0" in good.stdout

    truth_data = json.loads(truth_path.read_text())
    truth_data["events_s"] = [t + 5.0 for t in truth_data["events_s"]]
    bad_truth = tmp_path / "bad.truth.json"
    bad_truth.write_text(json.dumps(truth_data))

    bad = _run_cli(["analyze", str(wav_path), "--truth", str(bad_truth), "--tolerance-ms", "150"])
    assert bad.returncode == 1


def test_cli_run_wav_dry_run_summary(tmp_path: Path) -> None:
    wav_path, _truth_path = _generate_demo(tmp_path)

    result = _run_cli(
        [
            "run",
            "--source",
            f"wav:{wav_path}",
            "--dry-run",
            "--ignore-focus",
            "--json-summary",
        ]
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["catches"] == 4
    assert payload["casts"] >= 4
    assert payload["dropped_frames"] == 0

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BANNED_PATTERNS = [
    r"e-?deploy",
    r"\brbi\.com\b",
    r"\bRDC\b",
    r"[redacted]",
    r"[redacted]",
    r"VB-?Audio",
    r"VB-?CABLE",
    r"CABLE Output",
    r"Voicemeeter",
    r"Stereo Mix",
    r"C:[\\/]+Users[\\/]+lucas",
    r"[redacted]",
    r"[redacted]",
    r"D:[\\/]+Projects[\\/]+RDC",
    r"C:\\Python312",
    r"[redacted]",
    r"[redacted]",
]

_COMPILED = [re.compile(pattern, re.IGNORECASE) for pattern in BANNED_PATTERNS]


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line.strip()]


def test_no_banned_references() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _tracked_files():
        if path.name == "test_hygiene.py":
            continue
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in _COMPILED:
            if pattern.search(text):
                offenders.append((str(path), pattern.pattern))
    assert offenders == []


def test_readme_has_eula_disclaimer() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    lowered = readme.lower()
    assert "eula" in lowered or "terms of service" in lowered
    assert "no memory reading" in lowered

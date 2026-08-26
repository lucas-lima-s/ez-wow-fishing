from __future__ import annotations

import subprocess
import sys


def test_lazy_imports() -> None:
    code = (
        "import sys\n"
        "import wow_ez_fishing.detector\n"
        "import wow_ez_fishing.config\n"
        "import wow_ez_fishing.bot\n"
        "import wow_ez_fishing.cli\n"
        "banned = ['pyaudiowpatch', 'pycaw', 'pydirectinput', 'pynput']\n"
        "leaked = [b for b in banned if b in sys.modules]\n"
        "assert not leaked, leaked\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_es_module_loads_through_production_webengine_stack() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "xcb",
            "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu",
            "QTWEBENGINE_DISABLE_SANDBOX": "1",
        }
    )
    completed = subprocess.run(
        [
            "xvfb-run",
            "-a",
            sys.executable,
            str(ROOT / "tests" / "webengine_smoke_runner.py"),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, (
        f"WebEngine smoke failed with exit code {completed.returncode}.\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )

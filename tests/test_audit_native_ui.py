import os
import subprocess
import sys
from pathlib import Path


def test_real_webengine_response_isolation_history_hidden_and_close():
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, "-m", "tests.native_audit_probe"], cwd=root,
        env=environment, capture_output=True, text=True, timeout=25, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NATIVE_AUDIT_OK" in result.stdout

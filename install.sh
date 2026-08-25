#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    printf 'Error: %s was not found in PATH.\n' "$PYTHON_BIN" >&2
    exit 1
fi

if ! "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
then
    printf 'Error: Python 3.12 or newer is required.\n' >&2
    exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
    rm -rf .venv
    "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python - <<'PY'
import cryptography
import keyring
from PySide6 import QtCore, QtWebChannel, QtWebEngineWidgets

print("Verified critical imports:", QtCore.__version__)
PY

printf '\nInstallation complete. Launch with:\n  .venv/bin/python main.py\n'

#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$ROOT_DIR/.venv"

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

venv_is_usable=false
if [[ -x "$VENV_DIR/bin/python" ]]; then
    if "$VENV_DIR/bin/python" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
    then
        venv_is_usable=true
    fi
fi

if [[ "$venv_is_usable" != true ]]; then
    rm -rf -- "$VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r requirements.txt -r requirements-dev.txt

"$VENV_DIR/bin/python" - <<'PY'
import cryptography
import keyring
from PySide6 import QtCore, QtWebChannel, QtWebEngineWidgets

print("Verified critical imports:", QtCore.__version__)
PY

printf '\nInstallation complete. Launch with:\n  .venv/bin/python main.py\n'

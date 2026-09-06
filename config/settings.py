from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.application.inference_endpoint import InferenceEndpoint, InferenceLocation

_LOG = logging.getLogger(__name__)


def validated_inference_endpoint(settings: AppSettings) -> InferenceEndpoint:
    try:
        endpoint = InferenceEndpoint(settings.inference_endpoint, InferenceLocation(settings.inference_location))
        endpoint.validate()
        return endpoint
    except ValueError:
        defaults = AppSettings()
        _LOG.warning("Invalid inference settings; using local defaults")
        settings.inference_endpoint = defaults.inference_endpoint
        settings.inference_location = defaults.inference_location
        return InferenceEndpoint(defaults.inference_endpoint, InferenceLocation(defaults.inference_location))

@dataclass(slots=True)
class AppSettings:
    window_width: int = 1280
    window_height: int = 820
    inference_endpoint: str = "http://127.0.0.1:8080"
    inference_location: str = "LOCAL_PROCESS"
    inference_model: str = "default"


class SettingsStore:
    """Own application settings and recover safely from malformed files."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppSettings:
        defaults = AppSettings()
        if not self._path.exists():
            return defaults

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            _LOG.warning("Settings could not be decoded; using defaults (original file preserved)")
            return defaults

        if not isinstance(payload, dict):
            _LOG.warning("Settings root is not an object; using defaults (original file preserved)")
            return defaults

        return AppSettings(
            window_width=self._bounded_int(payload.get("window_width"), defaults.window_width, 1100, 3840),
            window_height=self._bounded_int(payload.get("window_height"), defaults.window_height, 720, 2160),
            inference_endpoint=self._string(payload.get("inference_endpoint"), defaults.inference_endpoint),
            inference_location=self._choice(
                payload.get("inference_location"),
                defaults.inference_location,
                {"LOCAL_PROCESS", "USER_APPROVED_LAN", "REMOTE"},
            ),
            inference_model=self._string(payload.get("inference_model"), defaults.inference_model),
        )

    def save(self, settings: AppSettings) -> None:
        self._write_payload(asdict(settings))

    def save_window_geometry(self, width: int, height: int) -> None:
        """Keep configured inference values and preserve unreadable files for recovery."""
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8")) if self._path.exists() else {}
            if not isinstance(payload, dict):
                raise TypeError("Settings root must be an object")
            payload["window_width"] = self._bounded_int(width, 1280, 1100, 3840)
            payload["window_height"] = self._bounded_int(height, 820, 720, 2160)
            self._write_payload(payload)
        except (OSError, UnicodeError, ValueError, TypeError):
            _LOG.warning("Window geometry could not be saved; original settings preserved")

    def _write_payload(self, payload: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=self._path.name + ".", suffix=".tmp", dir=self._path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self._path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            return default
        return min(max(value, minimum), maximum)

    @staticmethod
    def _string(value: Any, default: str) -> str:
        return value if isinstance(value, str) and value.strip() else default

    @staticmethod
    def _choice(value: Any, default: str, allowed: set[str]) -> str:
        return value if isinstance(value, str) and value in allowed else default

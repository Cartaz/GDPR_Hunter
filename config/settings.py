from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


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
        except (OSError, json.JSONDecodeError):
            return defaults

        if not isinstance(payload, dict):
            return defaults

        return AppSettings(
            window_width=self._bounded_int(payload.get("window_width"), defaults.window_width, 960, 3840),
            window_height=self._bounded_int(payload.get("window_height"), defaults.window_height, 700, 2160),
            inference_endpoint=self._string(payload.get("inference_endpoint"), defaults.inference_endpoint),
            inference_location=self._choice(
                payload.get("inference_location"),
                defaults.inference_location,
                {"LOCAL_PROCESS", "USER_APPROVED_LAN", "REMOTE"},
            ),
            inference_model=self._string(payload.get("inference_model"), defaults.inference_model),
        )

    def save(self, settings: AppSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self._path)

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

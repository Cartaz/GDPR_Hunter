from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path
    config_dir: Path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "gdpr_hunter.sqlite3"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def settings_path(self) -> Path:
        return self.config_dir / "settings.json"


def default_app_paths() -> AppPaths:
    home = Path.home()
    data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return AppPaths(
        data_dir=data_home / "gdpr-hunter",
        config_dir=config_home / "gdpr-hunter",
    )

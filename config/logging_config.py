from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from core.application.paths import default_app_paths


def configure_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        directory = default_app_paths().data_dir / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "gdpr-hunter.log"
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        path.chmod(0o600)
        handlers.append(handler)
    except OSError:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning("File logging unavailable; using the terminal")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s %(name)s: %(message)s",
        handlers=handlers, force=True,
    )

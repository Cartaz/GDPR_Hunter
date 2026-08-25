from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import SettingsStore
from core.application.app_controller import AppController
from core.application.identity_service import IdentityService
from core.application.paths import default_app_paths
from core.storage.artifact_store import ArtifactStore
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.secret_store import SecretStore, SecretStoreUnavailable
from core.storage.sensitive_store import SensitiveStore
from ui.bridge import Bridge
from ui.window import MainWindow


_LOG = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_controller() -> tuple[AppController, ArtifactStore, SettingsStore]:
    paths = default_app_paths()
    settings_store = SettingsStore(paths.settings_path)

    database = Database(paths.database_path)
    database.initialize()

    master_key = SecretStore().get_or_create_master_key()
    sensitive_store = SensitiveStore(master_key)
    artifact_store = ArtifactStore(paths.artifacts_dir, sensitive_store)

    identity_repository = IdentityRepository(database, sensitive_store)
    identity_service = IdentityService(identity_repository)
    controller = AppController(identity_service)
    return controller, artifact_store, settings_store


def main() -> int:
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("GDPR Hunter")

    try:
        controller, artifact_store, settings_store = build_controller()
    except SecretStoreUnavailable as exc:
        _LOG.critical("Secure credential store unavailable", exc_info=True)
        QMessageBox.critical(
            None,
            "GDPR Hunter",
            "A secure operating-system credential store is required before GDPR Hunter can start.",
        )
        return 1
    except Exception:
        _LOG.critical("Application initialization failed", exc_info=True)
        QMessageBox.critical(None, "GDPR Hunter", "Application initialization failed. Check the logs for details.")
        return 1

    # Keep lifecycle-owned services alive for the duration of the Qt event loop.
    application.setProperty("artifactStore", artifact_store)

    settings = settings_store.load()
    bridge = Bridge(controller)
    window = MainWindow(
        bridge=bridge,
        web_root=ROOT_DIR / "ui" / "web",
        width=settings.window_width,
        height=settings.window_height,
    )
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

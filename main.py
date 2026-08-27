from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import SettingsStore
from core.application.app_controller import AppController
from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.case_service import CaseService
from core.application.deadline_engine import DeadlineEngine
from core.application.egress_policy import EgressPolicy
from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.application.network_policy import NetworkPolicy
from core.application.paths import default_app_paths
from core.application.research_service import ResearchService
from core.application.target_service import TargetService
from core.domain.rights import RightsPolicy
from core.storage.artifact_store import ArtifactStore
from core.storage.case_repository import CaseRepository
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.investigation_repository import InvestigationRepository
from core.storage.secret_store import SecretStore, SecretStoreUnavailable
from core.storage.sensitive_store import SensitiveStore
from core.storage.target_repository import TargetRepository
from ui.bridge import Bridge
from ui.research_runner import ResearchRunner
from ui.window import MainWindow

_LOG = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_controller() -> tuple[AppController, SettingsStore]:
    paths = default_app_paths()
    settings_store = SettingsStore(paths.settings_path)

    database = Database(paths.database_path)
    database.initialize()

    master_key = SecretStore().get_or_create_master_key()
    sensitive_store = SensitiveStore(master_key)

    identity_service = IdentityService(IdentityRepository(database, sensitive_store))
    target_service = TargetService(TargetRepository(database))
    case_service = CaseService(
        CaseRepository(database),
        identity_service,
        target_service,
        RightsPolicy(),
        DeadlineEngine(),
    )
    network_policy = NetworkPolicy()
    research_service = ResearchService(network_policy)
    investigation_service = InvestigationService(
        InvestigationRepository(database, sensitive_store),
        ArtifactStore(paths.artifacts_dir, sensitive_store),
        identity_service,
        ArtifactAnalyzer(),
        research_service,
        EgressPolicy(),
    )
    return (
        AppController(identity_service, target_service, case_service, investigation_service),
        settings_store,
    )


def main() -> int:
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("GDPR Hunter")

    try:
        controller, settings_store = build_controller()
    except SecretStoreUnavailable:
        _LOG.critical("Secure credential store unavailable", exc_info=True)
        QMessageBox.critical(
            None,
            "GDPR Hunter",
            "A secure operating-system credential store is required before GDPR Hunter can start.",
        )
        return 1
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        _LOG.critical("Application initialization failed", exc_info=True)
        QMessageBox.critical(None, "GDPR Hunter", "Application initialization failed. Check the logs for details.")
        return 1

    settings = settings_store.load()
    research_runner = ResearchRunner(controller)
    bridge = Bridge(controller, research_runner)
    application.aboutToQuit.connect(research_runner.shutdown)
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

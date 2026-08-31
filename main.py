from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import AppSettings, SettingsStore
from core.application.app_controller import AppController
from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.case_service import CaseService
from core.application.deadline_engine import DeadlineEngine
from core.application.egress_policy import EgressPolicy
from core.application.holiday_calendar import HolidayCalendarProvider
from core.application.identity_service import IdentityService
from core.application.inference_endpoint import InferenceEndpoint, InferenceLocation
from core.application.inference_service import InferenceService
from core.application.investigation_service import InvestigationService
from core.application.model_analysis_service import ModelAnalysisService
from core.application.model_proposal_parser import ModelProposalParser
from core.application.network_policy import NetworkPolicy
from core.application.paths import default_app_paths
from core.application.proposal_review_service import ProposalReviewService
from core.application.request_approval_service import RequestApprovalService
from core.application.research_service import ResearchService
from core.application.target_service import TargetService
from core.domain.rights import RightsPolicy
from core.storage.approved_outbound_request_repository import (
    ApprovedOutboundRequestRepository,
)
from core.storage.artifact_store import ArtifactStore
from core.storage.case_repository import CaseRepository
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.investigation_repository import InvestigationRepository
from core.storage.outbound_audit_repository import OutboundAuditRepository
from core.storage.secret_store import SecretStore, SecretStoreUnavailable
from core.storage.sensitive_store import SensitiveStore
from core.storage.target_repository import TargetRepository
from ui.bridge import Bridge
from ui.model_analysis_runner import ModelAnalysisRunner
from ui.research_runner import ResearchRunner
from ui.window import MainWindow

_LOG = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _validated_inference_endpoint(settings: AppSettings) -> InferenceEndpoint:
    try:
        endpoint = InferenceEndpoint(
            settings.inference_endpoint,
            InferenceLocation(settings.inference_location),
        )
        endpoint.validate()
        return endpoint
    except ValueError:
        defaults = AppSettings()
        _LOG.warning("Invalid inference settings; using local defaults", exc_info=True)
        settings.inference_endpoint = defaults.inference_endpoint
        settings.inference_location = defaults.inference_location
        return InferenceEndpoint(
            defaults.inference_endpoint,
            InferenceLocation(defaults.inference_location),
        )


def build_controller() -> tuple[
    AppController,
    ModelAnalysisService,
    ProposalReviewService,
    AppSettings,
]:
    paths = default_app_paths()
    settings = SettingsStore(paths.settings_path).load()

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
        HolidayCalendarProvider(),
    )
    request_approval_service = RequestApprovalService(
        case_service,
        ApprovedOutboundRequestRepository(database, sensitive_store),
    )
    network_policy = NetworkPolicy()
    research_service = ResearchService(network_policy)
    egress_policy = EgressPolicy(OutboundAuditRepository(database, sensitive_store))
    investigation_service = InvestigationService(
        InvestigationRepository(database, sensitive_store),
        ArtifactStore(paths.artifacts_dir, sensitive_store),
        identity_service,
        ArtifactAnalyzer(),
        research_service,
        egress_policy,
    )
    inference_service = InferenceService(_validated_inference_endpoint(settings))
    model_analysis_service = ModelAnalysisService(
        investigation_service,
        inference_service,
        ModelProposalParser(),
        egress_policy,
        model=settings.inference_model,
    )
    return (
        AppController(
            identity_service,
            target_service,
            case_service,
            investigation_service,
            request_approval_service,
        ),
        model_analysis_service,
        ProposalReviewService(investigation_service),
        settings,
    )


def main() -> int:
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("GDPR Hunter")

    try:
        controller, model_analysis_service, proposal_review_service, settings = build_controller()
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

    research_runner = ResearchRunner(controller)
    model_analysis_runner = ModelAnalysisRunner(model_analysis_service)
    bridge = Bridge(
        controller,
        research_runner,
        model_analysis_runner,
        proposal_review_service,
    )
    application.aboutToQuit.connect(research_runner.shutdown)
    application.aboutToQuit.connect(model_analysis_runner.shutdown)
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

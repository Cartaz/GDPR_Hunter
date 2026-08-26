from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from core.application.app_controller import AppController
from ui.research_runner import ResearchRunner

_LOG = logging.getLogger(__name__)


class Bridge(QObject):
    stateChanged = Signal(object)
    operationFailed = Signal(str, str)
    researchStarted = Signal(int, int)
    researchCompleted = Signal(int, int, object)
    researchFailed = Signal(int, int, str, str)

    def __init__(self, controller: AppController, research_runner: ResearchRunner) -> None:
        super().__init__()
        self._controller = controller
        self._research_runner = research_runner
        research_runner.researchStarted.connect(self.researchStarted)
        research_runner.researchSucceeded.connect(self._research_succeeded)
        research_runner.researchFailed.connect(self._research_failed)

    @Slot(result="QVariant")
    def getBootstrapState(self) -> dict[str, object]:
        return self._controller.get_bootstrap_state()

    @Slot(str, result="QVariant")
    def setDisplayName(self, display_name: str) -> dict[str, object]:
        return self._mutate(lambda: self._controller.set_display_name(display_name))

    @Slot(str, str, str, result="QVariant")
    def addIdentifier(self, kind: str, value: str, label: str) -> dict[str, object]:
        return self._mutate(lambda: self._controller.add_identifier(kind, value, label or None))

    @Slot(str, str, str, result="QVariant")
    def createTarget(self, name: str, domain: str, privacy_email: str) -> dict[str, object]:
        return self._mutate(
            lambda: self._controller.create_target(name, domain or None, privacy_email or None)
        )

    @Slot(int, str, result="QVariant")
    def createCase(self, target_id: int, right: str) -> dict[str, object]:
        return self._mutate(lambda: self._controller.create_case(target_id, right))

    @Slot(int, str, result="QVariant")
    def submitCase(self, case_id: int, received_on: str) -> dict[str, object]:
        return self._mutate(lambda: self._controller.submit_case(case_id, received_on))

    @Slot(int, str, result="QVariant")
    def recordCaseExtension(self, case_id: int, notified_on: str) -> dict[str, object]:
        return self._mutate(lambda: self._controller.record_case_extension(case_id, notified_on))

    @Slot(int, str, result="QVariant")
    def transitionCase(self, case_id: int, target_status: str) -> dict[str, object]:
        return self._mutate(lambda: self._controller.transition_case(case_id, target_status))

    @Slot(int, result="QVariant")
    def getCaseTimeline(self, case_id: int) -> list[dict[str, object]] | dict[str, object]:
        return self._read(lambda: self._controller.get_case_timeline(case_id))

    @Slot(str, result="QVariant")
    def createInvestigation(self, title: str) -> dict[str, object]:
        return self._mutate(lambda: self._controller.create_investigation(title))

    @Slot(int, str, str, str, result="QVariant")
    def importTextArtifact(
        self,
        investigation_id: int,
        kind: str,
        role: str,
        text: str,
    ) -> dict[str, object]:
        return self._mutate(
            lambda: self._controller.import_text_artifact(investigation_id, kind, role, text)
        )

    @Slot(int, int, result="QVariant")
    def analyzeArtifact(self, investigation_id: int, artifact_id: int) -> dict[str, object]:
        return self._mutate(lambda: self._controller.analyze_artifact(investigation_id, artifact_id))

    @Slot(int, int, result="QVariant")
    def researchArtifactUrls(self, investigation_id: int, artifact_id: int) -> dict[str, object]:
        if investigation_id <= 0 or artifact_id <= 0:
            return self._fail("INVALID_INPUT", "Investigation and artifact ids must be positive")
        if not self._research_runner.start(investigation_id, artifact_id):
            return self._fail("BUSY", "Another research operation is already running")
        return {"ok": True}

    @Slot(int, int, str, str, result="QVariant")
    def addUserEvidence(
        self,
        investigation_id: int,
        artifact_id: int,
        value: str,
        source_locator: str,
    ) -> dict[str, object]:
        return self._mutate(
            lambda: self._controller.add_user_evidence(
                investigation_id,
                artifact_id or None,
                value or None,
                source_locator or None,
            )
        )

    @Slot(int, str, result="QVariant")
    def createUserClaim(self, investigation_id: int, statement: str) -> dict[str, object]:
        return self._mutate(lambda: self._controller.create_user_claim(investigation_id, statement))

    @Slot(int, result="QVariant")
    def getInvestigationDetail(self, investigation_id: int) -> dict[str, object]:
        return self._read(lambda: self._controller.get_investigation_detail(investigation_id))

    @Slot(int, int, object)
    def _research_succeeded(
        self,
        investigation_id: int,
        artifact_id: int,
        result: object,
    ) -> None:
        self.stateChanged.emit(self._controller.get_bootstrap_state())
        self.researchCompleted.emit(investigation_id, artifact_id, result)

    @Slot(int, int, str, str)
    def _research_failed(
        self,
        investigation_id: int,
        artifact_id: int,
        code: str,
        message: str,
    ) -> None:
        _LOG.warning("Asynchronous research failed: code=%s", code)
        self.researchFailed.emit(investigation_id, artifact_id, code, message)
        self.operationFailed.emit(code, message)

    def _read(self, operation):
        try:
            return operation()
        except (ValueError, LookupError) as exc:
            return self._fail("INVALID_INPUT", str(exc))

    def _mutate(self, operation) -> dict[str, object]:
        try:
            result = operation()
        except (ValueError, LookupError) as exc:
            return self._fail("INVALID_INPUT", str(exc))
        self.stateChanged.emit(self._controller.get_bootstrap_state())
        return {"ok": True, "result": result}

    def _fail(self, code: str, message: str) -> dict[str, object]:
        _LOG.warning("Bridge operation failed: code=%s", code)
        self.operationFailed.emit(code, message)
        return {"ok": False, "error": {"code": code, "message": message}}

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from core.application.app_controller import AppController
from core.application.proposal_review_service import ProposalReviewService, ReviewProposal
from core.domain.investigation import Claim
from core.domain.model_proposal import ClaimProposal, ResearchEvidenceProposal
from ui.model_analysis_runner import ModelAnalysisRunner
from ui.research_runner import ResearchRunner

_LOG = logging.getLogger(__name__)


class Bridge(QObject):
    stateChanged = Signal(object)
    operationFailed = Signal(str, str)
    researchStarted = Signal(int, int)
    researchCompleted = Signal(int, int, object)
    researchFailed = Signal(int, int, str, str)
    modelAnalysisStarted = Signal(int)
    modelAnalysisCompleted = Signal(int, object)
    modelAnalysisFailed = Signal(int, str, str)

    def __init__(
        self,
        controller: AppController,
        research_runner: ResearchRunner,
        model_analysis_runner: ModelAnalysisRunner | None = None,
        proposal_review_service: ProposalReviewService | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._research_runner = research_runner
        self._model_analysis_runner = model_analysis_runner
        self._proposal_review_service = proposal_review_service
        research_runner.researchStarted.connect(self.researchStarted)
        research_runner.researchSucceeded.connect(self._research_succeeded)
        research_runner.researchFailed.connect(self._research_failed)
        if model_analysis_runner is not None:
            model_analysis_runner.analysisStarted.connect(self.modelAnalysisStarted)
            model_analysis_runner.analysisSucceeded.connect(self._model_analysis_succeeded)
            model_analysis_runner.analysisFailed.connect(self._model_analysis_failed)

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

    @Slot(int, int, bool, result="QVariant")
    def researchArtifactUrls(
        self,
        investigation_id: int,
        artifact_id: int,
        approved_by_user: bool,
    ) -> dict[str, object]:
        if investigation_id <= 0 or artifact_id <= 0:
            return self._fail("INVALID_INPUT", "Investigation and artifact ids must be positive")
        if not approved_by_user:
            return self._fail("APPROVAL_REQUIRED", "Outbound research requires explicit user approval")
        if not self._research_runner.start(
            investigation_id,
            artifact_id,
            approved_by_user=approved_by_user,
        ):
            return self._fail("BUSY", "Another research operation is already running")
        return {"ok": True}

    @Slot(int, bool, result="QVariant")
    def analyzeInvestigationWithModel(
        self,
        investigation_id: int,
        approved_by_user: bool,
    ) -> dict[str, object]:
        if investigation_id <= 0:
            return self._fail("INVALID_INPUT", "Investigation id must be positive")
        if not approved_by_user:
            return self._fail(
                "APPROVAL_REQUIRED",
                "Model analysis requires explicit approval to send Investigation Evidence to the configured inference endpoint",
            )
        runner = self._model_analysis_runner
        if runner is None or self._proposal_review_service is None:
            return self._fail("CAPABILITY_UNAVAILABLE", "Model analysis review is not configured")
        if not runner.start(investigation_id, approved_by_user=approved_by_user):
            return self._fail("BUSY", "Another model analysis is already running")
        return {"ok": True}

    @Slot(str, bool, result="QVariant")
    def acceptModelClaim(self, proposal_token: str, approved_by_user: bool) -> dict[str, object]:
        if not approved_by_user:
            return self._fail("APPROVAL_REQUIRED", "Model claim requires explicit user review and approval")
        review_service = self._proposal_review_service
        if review_service is None:
            return self._fail("CAPABILITY_UNAVAILABLE", "Model proposal review is not configured")
        try:
            claim = review_service.accept_claim(proposal_token, approved_by_user=True)
        except (TypeError, ValueError, LookupError) as exc:
            return self._fail("INVALID_INPUT", str(exc))
        self.stateChanged.emit(self._controller.get_bootstrap_state())
        return {"ok": True, "result": self._claim_dto(claim)}

    @Slot(str, result="QVariant")
    def discardModelProposal(self, proposal_token: str) -> dict[str, object]:
        review_service = self._proposal_review_service
        if review_service is None:
            return self._fail("CAPABILITY_UNAVAILABLE", "Model proposal review is not configured")
        try:
            review_service.discard(proposal_token)
        except (ValueError, LookupError) as exc:
            return self._fail("INVALID_INPUT", str(exc))
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

    @Slot(int, object)
    def _model_analysis_succeeded(self, investigation_id: int, result: object) -> None:
        review_service = self._proposal_review_service
        if review_service is None:
            self._model_analysis_failed(
                investigation_id,
                "CAPABILITY_UNAVAILABLE",
                "Model proposal review is not configured",
            )
            return
        registered = review_service.register(investigation_id, tuple(result))
        proposals = [self._proposal_dto(item) for item in registered]
        self.modelAnalysisCompleted.emit(investigation_id, {"proposals": proposals})

    @Slot(int, str, str)
    def _model_analysis_failed(
        self,
        investigation_id: int,
        code: str,
        message: str,
    ) -> None:
        _LOG.warning("Asynchronous model analysis failed: code=%s", code)
        self.modelAnalysisFailed.emit(investigation_id, code, message)
        self.operationFailed.emit(code, message)

    @staticmethod
    def _proposal_dto(reviewed: ReviewProposal) -> dict[str, object]:
        proposal = reviewed.proposal
        if isinstance(proposal, ClaimProposal):
            return {
                "token": reviewed.token,
                "kind": "CLAIM",
                "statement": proposal.statement,
                "evidenceIds": list(proposal.evidence_ids),
                "confidence": proposal.confidence,
            }
        if isinstance(proposal, ResearchEvidenceProposal):
            return {
                "token": reviewed.token,
                "kind": "RESEARCH_EVIDENCE",
                "evidenceId": proposal.evidence_id,
                "rationale": proposal.rationale,
            }
        raise TypeError("Unsupported model proposal type")

    @staticmethod
    def _claim_dto(claim: Claim) -> dict[str, object]:
        return {
            "id": claim.id,
            "statement": claim.statement,
            "status": claim.status.value,
            "provenance": claim.provenance.value,
            "confidence": claim.confidence,
            "createdAt": claim.created_at,
            "updatedAt": claim.updated_at,
        }

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

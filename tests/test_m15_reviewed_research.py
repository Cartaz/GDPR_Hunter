from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.egress_policy import (
    EgressDecision,
    EgressPolicy,
    OutboundActor,
    OutboundIntent,
)
from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.application.network_policy import NetworkPolicy
from core.application.proposal_review_service import ProposalReviewService
from core.application.research_service import ResearchService, TransportResponse
from core.domain.investigation import (
    ArtifactKind,
    ArtifactRole,
    ClaimProvenance,
    EvidenceKind,
    EvidenceProvenance,
)
from core.domain.model_proposal import ClaimProposal, ResearchEvidenceProposal
from core.storage.artifact_store import ArtifactStore
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.investigation_repository import InvestigationRepository
from core.storage.sensitive_store import SensitiveStore
from ui.bridge import Bridge
from ui.research_runner import ResearchRunner

TEST_KEY = b"m" * 32
PUBLIC_IP = "93.184.216.34"


class RecordingAuditSink:
    def __init__(self) -> None:
        self.entries: list[tuple[OutboundIntent, EgressDecision]] = []

    def record_decision(self, intent: OutboundIntent, decision: EgressDecision) -> None:
        self.entries.append((intent, decision))


def resolver(_host, port, _family, _socktype):
    return [(2, 1, 6, "", (PUBLIC_IP, port))]


def build_services(tmp_path, transport):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity = IdentityService(IdentityRepository(database, sensitive))
    audit = RecordingAuditSink()
    investigation = InvestigationService(
        InvestigationRepository(database, sensitive),
        ArtifactStore(tmp_path / "artifacts", sensitive),
        identity,
        ArtifactAnalyzer(),
        ResearchService(NetworkPolicy(resolver), transport),
        EgressPolicy(audit),
    )
    return investigation, ProposalReviewService(investigation), audit


def add_url_evidence(service: InvestigationService, investigation_id: int):
    artifact = service.import_artifact(
        investigation_id,
        ArtifactKind.SMS,
        ArtifactRole.TRIGGER,
        "text/plain",
        b"Visit https://example.test/privacy",
    )
    assert artifact.id is not None
    service.analyze_artifact(investigation_id, artifact.id)
    evidence = next(
        item
        for item in service.list_evidence(investigation_id)
        if item.value == "https://example.test/privacy"
    )
    assert evidence.id is not None
    return evidence


def test_reviewed_research_consumes_only_python_owned_research_token(tmp_path) -> None:
    def transport(_validated, _timeout, _max_bytes):
        return TransportResponse(200, {"content-type": "text/plain"}, b"Privacy policy")

    service, review, _audit = build_services(tmp_path, transport)
    investigation = service.create_investigation("Reviewed research")
    assert investigation.id is not None
    evidence = add_url_evidence(service, investigation.id)
    reviewed = review.register(
        investigation.id,
        (ResearchEvidenceProposal(evidence.id, "Inspect the public privacy page"),),
    )[0]

    request = review.accept_research(reviewed.token, approved_by_user=True)

    assert request.investigation_id == investigation.id
    assert request.evidence_id == evidence.id
    with pytest.raises(LookupError, match="unknown, expired, or already used"):
        review.accept_research(reviewed.token, approved_by_user=True)


def test_denied_or_wrong_type_research_review_does_not_consume_token(tmp_path) -> None:
    def transport(_validated, _timeout, _max_bytes):
        return TransportResponse(200, {"content-type": "text/plain"}, b"ok")

    service, review, _audit = build_services(tmp_path, transport)
    investigation = service.create_investigation("Review gates")
    assert investigation.id is not None
    evidence = add_url_evidence(service, investigation.id)
    research = review.register(
        investigation.id,
        (ResearchEvidenceProposal(evidence.id, "Research it"),),
    )[0]

    with pytest.raises(PermissionError, match="explicit user review"):
        review.accept_research(research.token, approved_by_user=False)
    accepted = review.accept_research(research.token, approved_by_user=True)
    assert accepted.evidence_id == evidence.id

    claim = review.register(
        investigation.id,
        (ClaimProposal("A claim", (evidence.id,), 0.5),),
    )[0]
    with pytest.raises(TypeError, match="Only research proposals"):
        review.accept_research(claim.token, approved_by_user=True)
    accepted_claim = review.accept_claim(claim.token, approved_by_user=True)
    assert accepted_claim.provenance is ClaimProvenance.MODEL_INFERENCE


def test_model_research_derives_destination_from_persisted_evidence_and_audits_model_actor(
    tmp_path,
) -> None:
    calls: list[str] = []

    def transport(validated, _timeout, _max_bytes):
        calls.append(validated.url)
        return TransportResponse(
            200,
            {"content-type": "text/html"},
            b"<html><body>Privacy policy</body></html>",
        )

    service, review, audit = build_services(tmp_path, transport)
    investigation = service.create_investigation("Model egress")
    assert investigation.id is not None
    evidence = add_url_evidence(service, investigation.id)
    token = review.register(
        investigation.id,
        (ResearchEvidenceProposal(evidence.id, "Verify the public page"),),
    )[0].token
    request = review.accept_research(token, approved_by_user=True)

    created = service.research_model_evidence(
        request.investigation_id,
        request.evidence_id,
        approved_by_user=True,
    )

    assert calls == ["https://example.test/privacy"]
    assert any(item.provenance is EvidenceProvenance.REMOTE_DOCUMENT for item in created)
    assert len(audit.entries) == 1
    intent, decision = audit.entries[0]
    assert intent.destination == "https://example.test/privacy"
    assert intent.operation == "PUBLIC_RESEARCH_FETCH"
    assert intent.actor is OutboundActor.MODEL
    assert intent.approved_by_user is True
    assert decision is EgressDecision.ALLOW


def test_model_research_rejects_non_url_or_cross_investigation_evidence_before_egress(
    tmp_path,
) -> None:
    calls: list[str] = []

    def transport(validated, _timeout, _max_bytes):
        calls.append(validated.url)
        return TransportResponse(200, {"content-type": "text/plain"}, b"ok")

    service, _review, audit = build_services(tmp_path, transport)
    first = service.create_investigation("First")
    second = service.create_investigation("Second")
    assert first.id is not None and second.id is not None
    non_url = service.add_evidence(
        first.id,
        None,
        EvidenceKind.OBSERVATION,
        EvidenceProvenance.USER_STATEMENT,
        "Example Ltd",
        "manual.note",
    )
    foreign = add_url_evidence(service, second.id)
    assert non_url.id is not None and foreign.id is not None

    with pytest.raises(ValueError, match=r"HTTP\(S\) URL"):
        service.research_model_evidence(first.id, non_url.id, approved_by_user=True)
    with pytest.raises(LookupError, match="not attached"):
        service.research_model_evidence(first.id, foreign.id, approved_by_user=True)

    assert calls == []
    assert audit.entries == []


class FakeResearchController:
    def __init__(self) -> None:
        self.worker_thread_id: int | None = None
        self.calls: list[tuple[int, int, bool]] = []
        self.state_reads = 0

    def research_model_evidence(
        self,
        investigation_id: int,
        evidence_id: int,
        *,
        approved_by_user: bool,
        cancel_requested,
    ) -> dict[str, object]:
        assert cancel_requested() is False
        self.worker_thread_id = threading.get_ident()
        self.calls.append((investigation_id, evidence_id, approved_by_user))
        return {"createdCount": 1, "evidence": []}

    def get_bootstrap_state(self) -> dict[str, object]:
        self.state_reads += 1
        return {"milestone": "M15"}


def test_bridge_executes_research_token_as_async_model_evidence_request(tmp_path) -> None:
    application = QCoreApplication.instance() or QCoreApplication([])
    assert application is not None

    def transport(_validated, _timeout, _max_bytes):
        return TransportResponse(200, {"content-type": "text/plain"}, b"ok")

    service, review, _audit = build_services(tmp_path, transport)
    investigation = service.create_investigation("Bridge research")
    assert investigation.id is not None
    evidence = add_url_evidence(service, investigation.id)
    reviewed = review.register(
        investigation.id,
        (ResearchEvidenceProposal(evidence.id, "Research via token"),),
    )[0]
    controller = FakeResearchController()
    runner = ResearchRunner(controller)  # type: ignore[arg-type]
    bridge = Bridge(
        controller,  # type: ignore[arg-type]
        runner,
        proposal_review_service=review,
    )
    completed = QSignalSpy(bridge.modelResearchCompleted)
    caller_thread_id = threading.get_ident()

    try:
        denied = bridge.executeModelResearchProposal(reviewed.token, False)
        assert denied["ok"] is False
        assert denied["error"]["code"] == "APPROVAL_REQUIRED"

        started = bridge.executeModelResearchProposal(reviewed.token, True)
        assert started["ok"] is True
        assert started["result"] == {
            "investigationId": investigation.id,
            "evidenceId": evidence.id,
        }

        deadline = time.monotonic() + 2.0
        while (completed.count() == 0 or runner.is_busy) and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)

        assert completed.count() == 1
        assert runner.is_busy is False
        assert controller.calls == [(investigation.id, evidence.id, True)]
        assert controller.worker_thread_id is not None
        assert controller.worker_thread_id != caller_thread_id
        assert controller.state_reads == 1
        replay = bridge.executeModelResearchProposal(reviewed.token, True)
        assert replay["ok"] is False
        assert replay["error"]["code"] == "INVALID_INPUT"
    finally:
        runner.shutdown()

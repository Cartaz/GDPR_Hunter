from __future__ import annotations

import pytest

from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.application.proposal_review_service import ProposalReviewService
from core.domain.investigation import (
    ClaimProvenance,
    ClaimStatus,
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

TEST_KEY = b"r" * 32


class FakeController:
    def __init__(self) -> None:
        self.state_reads = 0

    def get_bootstrap_state(self):
        self.state_reads += 1
        return {"milestone": "M14"}


def build_services(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity = IdentityService(IdentityRepository(database, sensitive))
    investigation = InvestigationService(
        InvestigationRepository(database, sensitive),
        ArtifactStore(tmp_path / "artifacts", sensitive),
        identity,
        ArtifactAnalyzer(),
    )
    review = ProposalReviewService(investigation)
    return investigation, review


def add_evidence(service: InvestigationService, investigation_id: int):
    evidence = service.add_evidence(
        investigation_id,
        None,
        EvidenceKind.OBSERVATION,
        EvidenceProvenance.DETERMINISTIC_ANALYSIS,
        "Observed sender relationship",
        "test.sender",
    )
    assert evidence.id is not None
    return evidence


def test_review_service_accepts_only_python_owned_claim_and_consumes_token(tmp_path) -> None:
    investigation_service, review = build_services(tmp_path)
    investigation = investigation_service.create_investigation("Opaque review")
    assert investigation.id is not None
    evidence = add_evidence(investigation_service, investigation.id)
    registered = review.register(
        investigation.id,
        (ClaimProposal("Example Ltd may control the campaign", (evidence.id,), 0.81),),
    )
    token = registered[0].token

    claim = review.accept_claim(token, approved_by_user=True)

    assert claim.provenance is ClaimProvenance.MODEL_INFERENCE
    assert claim.status is ClaimStatus.HYPOTHESIS
    assert claim.statement == "Example Ltd may control the campaign"
    assert claim.confidence == 0.81
    with pytest.raises(LookupError, match="unknown, expired, or already used"):
        review.accept_claim(token, approved_by_user=True)
    assert len(investigation_service.list_claims(investigation.id)) == 1


def test_forged_token_and_unapproved_review_do_not_mutate_state(tmp_path) -> None:
    investigation_service, review = build_services(tmp_path)
    investigation = investigation_service.create_investigation("Forgery")
    assert investigation.id is not None
    evidence = add_evidence(investigation_service, investigation.id)
    registered = review.register(
        investigation.id,
        (ClaimProposal("Python-owned proposal", (evidence.id,), 0.7),),
    )

    with pytest.raises(LookupError):
        review.accept_claim("attacker-controlled-token", approved_by_user=True)
    with pytest.raises(PermissionError, match="explicit user review"):
        review.accept_claim(registered[0].token, approved_by_user=False)

    assert investigation_service.list_claims(investigation.id) == []
    claim = review.accept_claim(registered[0].token, approved_by_user=True)
    assert claim.statement == "Python-owned proposal"


def test_new_analysis_invalidates_previous_tokens_for_same_investigation(tmp_path) -> None:
    investigation_service, review = build_services(tmp_path)
    investigation = investigation_service.create_investigation("Refresh")
    assert investigation.id is not None
    evidence = add_evidence(investigation_service, investigation.id)
    old = review.register(
        investigation.id,
        (ClaimProposal("Old proposal", (evidence.id,), 0.5),),
    )[0]
    current = review.register(
        investigation.id,
        (ClaimProposal("Current proposal", (evidence.id,), 0.9),),
    )[0]

    with pytest.raises(LookupError):
        review.accept_claim(old.token, approved_by_user=True)
    accepted = review.accept_claim(current.token, approved_by_user=True)
    assert accepted.statement == "Current proposal"


def test_research_proposal_cannot_be_accepted_as_claim(tmp_path) -> None:
    investigation_service, review = build_services(tmp_path)
    investigation = investigation_service.create_investigation("Research proposal")
    assert investigation.id is not None
    evidence = add_evidence(investigation_service, investigation.id)
    registered = review.register(
        investigation.id,
        (ResearchEvidenceProposal(evidence.id, "Research this evidence"),),
    )

    with pytest.raises(TypeError, match="Only claim proposals"):
        review.accept_claim(registered[0].token, approved_by_user=True)
    assert investigation_service.list_claims(investigation.id) == []


def test_bridge_accepts_only_token_and_emits_state_after_success(tmp_path) -> None:
    investigation_service, review = build_services(tmp_path)
    investigation = investigation_service.create_investigation("Bridge review")
    assert investigation.id is not None
    evidence = add_evidence(investigation_service, investigation.id)
    reviewed = review.register(
        investigation.id,
        (ClaimProposal("Bridge-owned model claim", (evidence.id,), 0.75),),
    )[0]
    controller = FakeController()
    research_runner = ResearchRunner(controller)  # type: ignore[arg-type]
    bridge = Bridge(
        controller,  # type: ignore[arg-type]
        research_runner,
        proposal_review_service=review,
    )

    forged = bridge.acceptModelClaim("not-a-real-token", True)
    denied = bridge.acceptModelClaim(reviewed.token, False)
    accepted = bridge.acceptModelClaim(reviewed.token, True)
    replay = bridge.acceptModelClaim(reviewed.token, True)

    assert forged["ok"] is False
    assert denied["ok"] is False
    assert denied["error"]["code"] == "APPROVAL_REQUIRED"
    assert accepted["ok"] is True
    assert accepted["result"]["provenance"] == ClaimProvenance.MODEL_INFERENCE.value
    assert replay["ok"] is False
    assert controller.state_reads == 1

from __future__ import annotations

import pytest

from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.domain.investigation import (
    ClaimProvenance,
    ClaimStatus,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRelation,
)
from core.domain.model_proposal import ClaimProposal
from core.storage.artifact_store import ArtifactStore
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.investigation_repository import InvestigationRepository
from core.storage.sensitive_store import SensitiveStore

TEST_KEY = b"m" * 32


def build_service(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity = IdentityService(IdentityRepository(database, sensitive))
    repository = InvestigationRepository(database, sensitive)
    service = InvestigationService(
        repository,
        ArtifactStore(tmp_path / "artifacts", sensitive),
        identity,
        ArtifactAnalyzer(),
    )
    return database, repository, service


def add_observation(service: InvestigationService, investigation_id: int, value: str):
    evidence = service.add_evidence(
        investigation_id,
        None,
        EvidenceKind.OBSERVATION,
        EvidenceProvenance.DETERMINISTIC_ANALYSIS,
        value,
        "test.observation",
    )
    assert evidence.id is not None
    return evidence


def test_approved_model_claim_is_created_as_hypothesis_with_supporting_evidence(tmp_path) -> None:
    database, repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Reviewed model claim")
    assert investigation.id is not None
    first = add_observation(service, investigation.id, "Observation one")
    second = add_observation(service, investigation.id, "Observation two")

    claim = service.accept_model_claim(
        investigation.id,
        ClaimProposal("Example Ltd may be the source", (first.id, second.id), 0.82),
        approved_by_user=True,
    )

    assert claim.provenance is ClaimProvenance.MODEL_INFERENCE
    assert claim.status is ClaimStatus.HYPOTHESIS
    assert claim.confidence == 0.82
    assert repository.supporting_evidence_count(claim.id) == 2
    assert b"Example Ltd may be the source" not in database.path.read_bytes()
    with database.connection_scope() as connection:
        relations = connection.execute(
            "SELECT relation FROM claim_evidence WHERE claim_id = ? ORDER BY evidence_id",
            (claim.id,),
        ).fetchall()
    assert [row["relation"] for row in relations] == [
        EvidenceRelation.SUPPORTS.value,
        EvidenceRelation.SUPPORTS.value,
    ]


def test_unapproved_model_claim_does_not_mutate_state(tmp_path) -> None:
    _database, _repository, service = build_service(tmp_path)
    investigation = service.create_investigation("No approval")
    assert investigation.id is not None
    evidence = add_observation(service, investigation.id, "Observation")

    with pytest.raises(PermissionError, match="explicit user review"):
        service.accept_model_claim(
            investigation.id,
            ClaimProposal("Unapproved", (evidence.id,), 0.5),
            approved_by_user=False,
        )

    assert service.list_claims(investigation.id) == []


def test_cross_investigation_model_evidence_rolls_back_claim_creation(tmp_path) -> None:
    database, _repository, service = build_service(tmp_path)
    first = service.create_investigation("First")
    second = service.create_investigation("Second")
    assert first.id is not None and second.id is not None
    first_evidence = add_observation(service, first.id, "First evidence")
    second_evidence = add_observation(service, second.id, "Second evidence")

    with pytest.raises(ValueError, match="belong to this investigation"):
        service.accept_model_claim(
            first.id,
            ClaimProposal("Mixed evidence claim", (first_evidence.id, second_evidence.id), 0.6),
            approved_by_user=True,
        )

    assert service.list_claims(first.id) == []
    with database.connection_scope() as connection:
        assert connection.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0] == 0


def test_duplicate_evidence_ids_are_rejected_before_mutation(tmp_path) -> None:
    _database, _repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Duplicate evidence")
    assert investigation.id is not None
    evidence = add_observation(service, investigation.id, "Observation")

    with pytest.raises(ValueError, match="duplicate evidence"):
        service.accept_model_claim(
            investigation.id,
            ClaimProposal("Duplicate evidence claim", (evidence.id, evidence.id), 0.7),
            approved_by_user=True,
        )

    assert service.list_claims(investigation.id) == []

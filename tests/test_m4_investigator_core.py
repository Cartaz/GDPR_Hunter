from __future__ import annotations

import sqlite3

import pytest

from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.domain.investigation import (
    ArtifactKind,
    ArtifactRole,
    ClaimProvenance,
    ClaimStatus,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRelation,
    InvestigationStatus,
)
from core.storage.artifact_store import ArtifactStore
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.investigation_repository import InvestigationRepository
from core.storage.sensitive_store import SensitiveStore

TEST_KEY = b"i" * 32


def build_service(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity_service = IdentityService(IdentityRepository(database, sensitive))
    repository = InvestigationRepository(database, sensitive)
    service = InvestigationService(
        repository,
        ArtifactStore(tmp_path / "artifacts", sensitive),
        identity_service,
    )
    return database, repository, service


def test_investigation_artifact_evidence_and_claim_are_persisted_encrypted(tmp_path):
    database, _repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Why did Example Corp get my phone?")
    assert investigation.id is not None

    payload = b"Example marketing SMS for +39 333 123 4567"
    artifact = service.import_artifact(
        investigation.id,
        ArtifactKind.SMS,
        ArtifactRole.TRIGGER,
        "text/plain",
        payload,
    )
    assert artifact.id is not None

    evidence = service.add_evidence(
        investigation.id,
        artifact.id,
        EvidenceKind.EXTRACTED_FIELD,
        EvidenceProvenance.DETERMINISTIC_ANALYSIS,
        "+39 333 123 4567",
        "sms.body.phone",
    )
    claim = service.create_claim(
        investigation.id,
        "Example Corp appears to possess this phone number",
        ClaimProvenance.DETERMINISTIC,
        0.7,
    )

    assert evidence.id is not None
    assert claim.id is not None
    assert claim.status is ClaimStatus.HYPOTHESIS

    database_bytes = database.path.read_bytes()
    assert b"+39 333 123 4567" not in database_bytes
    assert b"Example Corp appears to possess this phone number" not in database_bytes
    assert b"Why did Example Corp get my phone?" not in database_bytes


def test_model_claim_starts_as_hypothesis_and_confidence_cannot_verify_it(tmp_path):
    _database, _repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Model claim")
    assert investigation.id is not None

    claim = service.create_claim(
        investigation.id,
        "A broker supplied the number",
        ClaimProvenance.MODEL_INFERENCE,
        0.999,
    )
    assert claim.id is not None
    assert claim.status is ClaimStatus.HYPOTHESIS

    with pytest.raises(ValueError, match="Invalid claim transition"):
        service.transition_claim(claim.id, ClaimStatus.VERIFIED)


def test_claim_promotion_requires_increasing_supporting_evidence(tmp_path):
    _database, _repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Evidence requirement")
    assert investigation.id is not None

    claim = service.create_claim(
        investigation.id,
        "Company response identifies Broker X as the source",
        ClaimProvenance.DETERMINISTIC,
    )
    assert claim.id is not None

    with pytest.raises(ValueError, match="Supported claims require"):
        service.transition_claim(claim.id, ClaimStatus.SUPPORTED)

    first = service.add_evidence(
        investigation.id,
        None,
        EvidenceKind.SOURCE_STATEMENT,
        EvidenceProvenance.COMPANY_RESPONSE,
        "We obtained your number from Broker X",
        "response.body",
    )
    assert first.id is not None
    service.attach_evidence(claim.id, first.id, EvidenceRelation.SUPPORTS)
    supported = service.transition_claim(claim.id, ClaimStatus.SUPPORTED)
    assert supported.status is ClaimStatus.SUPPORTED

    with pytest.raises(ValueError, match="at least two"):
        service.transition_claim(claim.id, ClaimStatus.CORROBORATED)

    second = service.add_evidence(
        investigation.id,
        None,
        EvidenceKind.OBSERVATION,
        EvidenceProvenance.AUTHORITATIVE_SOURCE,
        "Broker X is identified as the campaign lead provider",
        "authoritative.registry.entry",
    )
    assert second.id is not None
    service.attach_evidence(claim.id, second.id, EvidenceRelation.SUPPORTS)

    corroborated = service.transition_claim(claim.id, ClaimStatus.CORROBORATED)
    verified = service.transition_claim(corroborated.id, ClaimStatus.VERIFIED)
    assert verified.status is ClaimStatus.VERIFIED


def test_cross_investigation_evidence_attachment_is_rejected(tmp_path):
    _database, _repository, service = build_service(tmp_path)
    first = service.create_investigation("First")
    second = service.create_investigation("Second")
    assert first.id is not None and second.id is not None

    claim = service.create_claim(first.id, "Claim one", ClaimProvenance.USER)
    evidence = service.add_evidence(
        second.id,
        None,
        EvidenceKind.OBSERVATION,
        EvidenceProvenance.USER_STATEMENT,
        "Observation two",
        None,
    )
    assert claim.id is not None and evidence.id is not None

    with pytest.raises(ValueError, match="same investigation"):
        service.attach_evidence(claim.id, evidence.id, EvidenceRelation.SUPPORTS)


def test_artifact_metadata_is_immutable_and_failed_metadata_write_cleans_file(tmp_path):
    database, repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Immutable artifact")
    assert investigation.id is not None
    artifact = service.import_artifact(
        investigation.id,
        ArtifactKind.TEXT,
        ArtifactRole.TRIGGER,
        "text/plain",
        b"immutable contents",
    )
    assert artifact.id is not None

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute("UPDATE artifacts SET byte_size = 1 WHERE id = ?", (artifact.id,))

    with pytest.raises(LookupError):
        service.import_artifact(
            999,
            ArtifactKind.TEXT,
            ArtifactRole.TRIGGER,
            "text/plain",
            b"never stored",
        )

    assert len(list((tmp_path / "artifacts").rglob("*.dat"))) == 1
    assert repository.list_artifacts(investigation.id)[0].byte_size == len(b"immutable contents")


def test_investigation_state_machine_blocks_invalid_shortcuts(tmp_path):
    _database, _repository, service = build_service(tmp_path)
    investigation = service.create_investigation("State machine")
    assert investigation.id is not None

    with pytest.raises(ValueError, match="Invalid investigation transition"):
        service.transition(investigation.id, InvestigationStatus.CONCLUDED)

    analysing = service.transition(investigation.id, InvestigationStatus.ANALYSING)
    concluded = service.transition(analysing.id, InvestigationStatus.CONCLUDED)
    reopened = service.transition(concluded.id, InvestigationStatus.ANALYSING)
    assert reopened.status is InvestigationStatus.ANALYSING


def test_sensitive_investigation_domain_repr_is_redacted(tmp_path):
    _database, _repository, service = build_service(tmp_path)
    investigation = service.create_investigation("secret title")
    assert "secret title" not in repr(investigation)

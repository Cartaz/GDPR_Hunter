from __future__ import annotations

from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.domain.investigation import ArtifactKind, ArtifactRole, EvidenceProvenance
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
    service = InvestigationService(
        InvestigationRepository(database, sensitive),
        ArtifactStore(tmp_path / "artifacts", sensitive),
        identity,
        ArtifactAnalyzer(),
    )
    return service


def import_and_analyze(service, investigation_id, kind, payload):
    artifact = service.import_artifact(
        investigation_id,
        kind,
        ArtifactRole.TRIGGER,
        "text/plain; charset=utf-8",
        payload,
    )
    assert artifact.id is not None
    created = service.analyze_artifact(investigation_id, artifact.id)
    return artifact, created


def test_sms_analysis_extracts_url_host_and_phone(tmp_path):
    service = build_service(tmp_path)
    investigation = service.create_investigation("Suspicious SMS")
    assert investigation.id is not None

    artifact, created = import_and_analyze(
        service,
        investigation.id,
        ArtifactKind.SMS,
        b"Call +39 333 123 4567 or visit https://Lead.Example.com/path?x=1.",
    )

    values = {item.value for item in created}
    assert "+39 333 123 4567" in values
    assert "https://Lead.Example.com/path?x=1" in values
    assert "lead.example.com" in values
    assert all(item.artifact_id == artifact.id for item in created)
    assert all(item.provenance is EvidenceProvenance.DETERMINISTIC_ANALYSIS for item in created)


def test_phone_extraction_does_not_treat_iso_date_as_phone(tmp_path):
    service = build_service(tmp_path)
    investigation = service.create_investigation("Date")
    assert investigation.id is not None

    _artifact, created = import_and_analyze(
        service,
        investigation.id,
        ArtifactKind.TEXT,
        b"Request received on 2026-08-25.",
    )

    assert created == []


def test_email_analysis_extracts_sender_reply_path_dkim_message_id_and_body_url(tmp_path):
    service = build_service(tmp_path)
    investigation = service.create_investigation("Marketing email")
    assert investigation.id is not None
    raw = b"""From: Sales <sales@sender.example>\r\nReply-To: privacy@reply.example\r\nReturn-Path: <bounce@return.example>\r\nMessage-ID: <abc123@mail.example>\r\nDKIM-Signature: v=1; a=rsa-sha256; d=dkim.example; s=test; bh=x; b=y\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nOpen https://track.example/campaign now.\r\n"""

    _artifact, created = import_and_analyze(service, investigation.id, ArtifactKind.EMAIL, raw)
    values = {item.value for item in created}

    assert "sender.example" in values
    assert "reply.example" in values
    assert "return.example" in values
    assert "mail.example" in values
    assert "dkim.example" in values
    assert "track.example" in values
    assert "https://track.example/campaign" in values


def test_url_artifact_rejects_non_http_as_finding(tmp_path):
    service = build_service(tmp_path)
    investigation = service.create_investigation("URL")
    assert investigation.id is not None

    _artifact, created = import_and_analyze(
        service,
        investigation.id,
        ArtifactKind.URL,
        b"file:///home/user/private.txt",
    )

    assert created == []


def test_analysis_is_idempotent(tmp_path):
    service = build_service(tmp_path)
    investigation = service.create_investigation("Repeat")
    assert investigation.id is not None
    artifact = service.import_artifact(
        investigation.id,
        ArtifactKind.SMS,
        ArtifactRole.TRIGGER,
        "text/plain",
        b"https://example.com and +386 40 123 456",
    )
    assert artifact.id is not None

    first = service.analyze_artifact(investigation.id, artifact.id)
    second = service.analyze_artifact(investigation.id, artifact.id)

    assert first
    assert second == []
    assert len(service.list_evidence(investigation.id)) == len(first)


def test_analysis_cannot_read_artifact_from_another_investigation(tmp_path):
    service = build_service(tmp_path)
    first = service.create_investigation("First")
    second = service.create_investigation("Second")
    assert first.id is not None and second.id is not None
    artifact = service.import_artifact(
        first.id,
        ArtifactKind.TEXT,
        ArtifactRole.TRIGGER,
        "text/plain",
        b"https://example.com",
    )
    assert artifact.id is not None

    try:
        service.analyze_artifact(second.id, artifact.id)
    except LookupError as exc:
        assert "not attached" in str(exc)
    else:
        raise AssertionError("Cross-investigation artifact analysis should fail")

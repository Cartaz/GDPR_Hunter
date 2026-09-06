from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from config.settings import AppSettings, SettingsStore
from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.model_proposal_parser import (
    ModelProposalParser,
    ModelProposalValidationError,
)
from core.application.research_service import TransportResponse
from core.application.strict_json import loads
from core.domain.investigation import (
    ArtifactKind,
    ArtifactRole,
    ClaimProvenance,
    ClaimStatus,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRelation,
)
from core.domain.rights import CaseRight, ErasureGround
from core.storage.database import Database
from core.storage.secret_store import SecretStore, SecretStoreUnavailable
from core.storage.sensitive_store import SensitiveStore, StorageIntegrityError
from tests.test_m4_investigator_core import build_service
from tests.test_m6_research import build_investigation_service
from tests.test_m18_request_approval import create_case


@pytest.mark.parametrize("ground", list(ErasureGround))
def test_every_erasure_ground_can_be_approved_and_reloaded(tmp_path, ground):
    _db, _identity, _cases, approvals, case = create_case(tmp_path, CaseRight.ERASURE)
    request = approvals.approve(case.id, erasure_ground=ground, approved_by_user=True)
    assert approvals.get(request.id) == request
    assert request.erasure_ground is ground


def test_approval_rechecks_draft_status_inside_persistence(tmp_path, monkeypatch):
    from core.domain.case import CaseStatus

    db, _identity, cases, approvals, case = create_case(tmp_path)
    repository = approvals._repository
    original = repository.create

    def concurrent_transition(request):
        cases.transition_case(case.id, CaseStatus.CANCELLED)
        return original(request)

    monkeypatch.setattr(repository, "create", concurrent_transition)
    with pytest.raises(ValueError, match="case changed"):
        approvals.approve(case.id, approved_by_user=True)
    with db.connection_scope() as connection:
        assert connection.execute("SELECT COUNT(*) FROM approved_outbound_requests").fetchone()[0] == 0


def downgrade_approval_fixture_to_v10(database):
    """Construct the actual old CHECK constraint, not merely a version label."""
    mapping = {
        "CONSENT_WITHDRAWN": "WITHDRAWN_CONSENT",
        "OBJECTION": "OBJECTION_NO_OVERRIDE",
        "CHILD_INFORMATION_SOCIETY_SERVICES": "CHILD_INFORMATION_SOCIETY",
    }
    statements = Database._approved_outbound_request_statements()
    with database.connection_scope() as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT * FROM approved_outbound_requests").fetchall()
            connection.execute("DROP TABLE approved_outbound_requests")
            schema = statements[0]
            for canonical, legacy in mapping.items():
                schema = schema.replace(f"'{canonical}'", f"'{legacy}'")
            connection.execute(schema)
            for row in rows:
                values = list(row)
                values[8] = mapping.get(values[8], values[8])
                connection.execute("INSERT INTO approved_outbound_requests VALUES (?,?,?,?,?,?,?,?,?,?)", values)
            for statement in statements[1:]:
                connection.execute(statement)
            connection.execute("DROP TABLE claim_reviews")
            connection.execute("UPDATE schema_meta SET schema_version = 10")


@pytest.mark.parametrize("ground", [ErasureGround.CONSENT_WITHDRAWN, ErasureGround.OBJECTION, ErasureGround.CHILD_INFORMATION_SOCIETY_SERVICES])
def test_v10_migration_preserves_ciphertext_ids_submission_and_delivery(tmp_path, ground):
    db, _identity, cases, approvals, case = create_case(tmp_path, CaseRight.ERASURE)
    approved = approvals.approve(case.id, erasure_ground=ground, approved_by_user=True)
    cases.submit_case(case.id, approved.id, date(2026, 9, 1), "IT")
    with db.transaction() as connection:
        connection.execute("""
            INSERT INTO outbound_delivery_events VALUES (1, 'attempt', ?, 'HANDOFF_REQUESTED', 'now')
        """, (approved.id,))
        ciphertext = tuple(connection.execute(
            "SELECT recipient_email_enc, subject_enc, body_enc FROM approved_outbound_requests"
        ).fetchone())
    downgrade_approval_fixture_to_v10(db)
    Database(db.path).initialize()
    assert approvals.get(approved.id) == approved
    with db.connection_scope() as connection:
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert tuple(connection.execute("SELECT recipient_email_enc, subject_enc, body_enc FROM approved_outbound_requests").fetchone()) == ciphertext
        assert connection.execute("SELECT approved_request_id FROM case_submission_bindings").fetchone()[0] == approved.id
        assert connection.execute("SELECT approved_request_id FROM outbound_delivery_events").fetchone()[0] == approved.id
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), db.transaction() as connection:
        connection.execute("DELETE FROM approved_outbound_requests")


def test_fresh_schema_ddl_failure_is_atomic_and_retryable(tmp_path, monkeypatch):
    database = Database(tmp_path / "fresh.sqlite3")
    original = database._create_targets_schema

    def fail(_connection):
        raise sqlite3.OperationalError("injected DDL failure")

    monkeypatch.setattr(database, "_create_targets_schema", fail)
    with pytest.raises(sqlite3.OperationalError):
        database.initialize()
    with database.connection_scope() as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    monkeypatch.setattr(database, "_create_targets_schema", original)
    database.initialize()


@pytest.mark.parametrize("from_version", [9, 10])
def test_migration_failure_rolls_back_ddl_and_version_then_retries(tmp_path, monkeypatch, from_version):
    db, _identity, _cases, approvals, case = create_case(tmp_path)
    approved = approvals.approve(case.id, approved_by_user=True)
    downgrade_approval_fixture_to_v10(db)
    if from_version == 9:
        with db.transaction() as connection:
            connection.execute("DROP TABLE case_responses")
            connection.execute("UPDATE schema_meta SET schema_version = 9")
    with db.connection_scope() as connection:
        before = [tuple(row) for row in connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name")]
    original = db._set_schema_version

    def fail(_connection, *, expected, target):
        raise sqlite3.OperationalError("injected version failure")

    monkeypatch.setattr(db, "_set_schema_version", fail)
    with pytest.raises(sqlite3.OperationalError):
        db.initialize()
    with db.connection_scope() as connection:
        assert connection.execute("SELECT schema_version FROM schema_meta").fetchone()[0] == from_version
        assert [tuple(row) for row in connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name")] == before
    monkeypatch.setattr(db, "_set_schema_version", original)
    db.initialize()
    assert approvals.get(approved.id) == approved


def research_fixture(tmp_path):
    calls = []

    def transport(validated, _timeout, _limit):
        calls.append(validated.url)
        return TransportResponse(200, {"content-type": "text/plain"}, b"https://partner.test/privacy")

    database, service = build_investigation_service(tmp_path, transport)
    investigation = service.create_investigation("Atomic research")
    artifact = service.import_artifact(investigation.id, ArtifactKind.URL, ArtifactRole.TRIGGER, "text/plain", b"https://example.test/")
    service.analyze_artifact(investigation.id, artifact.id)
    return database, service, investigation.id, artifact.id, calls


def test_research_failure_has_no_partial_evidence_or_orphan_and_retry_completes(tmp_path, monkeypatch):
    _db, service, investigation_id, artifact_id, calls = research_fixture(tmp_path)
    repository = service._repository
    before = service.list_evidence(investigation_id)
    original = repository._add_evidence
    count = 0

    def fail_after_first(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise sqlite3.OperationalError("injected evidence failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "_add_evidence", fail_after_first)
    with pytest.raises(sqlite3.OperationalError):
        service.research_artifact_urls(investigation_id, artifact_id, approved_by_user=True)
    assert service.list_evidence(investigation_id) == before
    assert len(service.list_artifacts(investigation_id)) == 1
    assert len(list((tmp_path / "artifacts").rglob("*.dat"))) == 1
    monkeypatch.setattr(repository, "_add_evidence", original)
    created = service.research_artifact_urls(investigation_id, artifact_id, approved_by_user=True)
    assert any(item.value == "https://partner.test/privacy" for item in created)
    assert any(item.source_locator.startswith("research.complete.v1:") for item in created)
    assert service.research_artifact_urls(investigation_id, artifact_id, approved_by_user=True) == []
    assert len(calls) == 2


def test_legacy_request_marker_does_not_skip_an_incomplete_document(tmp_path):
    _db, service, investigation_id, artifact_id, _calls = research_fixture(tmp_path)
    service.add_evidence(investigation_id, artifact_id, EvidenceKind.OBSERVATION,
                         EvidenceProvenance.REMOTE_DOCUMENT, "https://example.test/", "research.request:https://example.test/")
    assert service.research_artifact_urls(investigation_id, artifact_id, approved_by_user=True)


def test_analysis_is_atomic_and_bounded_without_partial_findings(tmp_path, monkeypatch):
    _db, repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Analysis")
    artifact = service.import_artifact(investigation.id, ArtifactKind.TEXT, ArtifactRole.TRIGGER, "text/plain", b"https://example.test/path")
    original = repository._add_evidence
    calls = 0

    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("injected batch failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "_add_evidence", fail)
    with pytest.raises(sqlite3.OperationalError):
        service.analyze_artifact(investigation.id, artifact.id)
    assert service.list_evidence(investigation.id) == []
    monkeypatch.setattr(repository, "_add_evidence", original)
    assert len(service.analyze_artifact(investigation.id, artifact.id)) == 2
    assert service.analyze_artifact(investigation.id, artifact.id) == []
    payload = " ".join(f"https://example.test/{index}" for index in range(1001)).encode()
    with pytest.raises(ValueError, match="finding limit"):
        ArtifactAnalyzer().analyze(ArtifactKind.TEXT, payload)


def test_html_only_email_extracts_visible_links_but_not_scripts_or_attachments():
    payload = b'''MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n--x
Content-Type: text/html; charset=utf-8

<html><head><script>https://script.test/</script></head><body><a href="https://link.test/?a=1&amp;b=2">Privacy</a> https://visible.test/</body></html>
--x
Content-Type: text/html
Content-Disposition: attachment

<a href="https://attachment.test/">Ignore</a>
--x--
'''
    findings = ArtifactAnalyzer().analyze(ArtifactKind.EMAIL, payload)
    values = {item.value for item in findings}
    assert "https://link.test/?a=1&b=2" in values
    assert "https://visible.test/" in values
    assert not any("script.test" in value or "attachment.test" in value for value in values)
    assert all("email.body.part[" in item.source_locator for item in findings)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10**1000])
def test_model_confidence_rejects_non_finite_and_extreme_numbers(value):
    with pytest.raises(ModelProposalValidationError):
        ModelProposalParser().parse({"proposals": [{"kind": "CLAIM", "statement": "hypothesis", "evidence_ids": [1], "confidence": value}]}, available_evidence_ids={1})


@pytest.mark.parametrize("payload", ['{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e999}', '{"x":1,"x":2}'])
def test_model_json_rejects_nonstandard_numbers_and_duplicate_keys(payload):
    with pytest.raises(ValueError):
        loads(payload)


def test_non_utf8_settings_recover_without_rewriting_original(tmp_path, caplog):
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xff\xfeinvalid")
    assert SettingsStore(path).load() == AppSettings()
    assert path.read_bytes() == b"\xff\xfeinvalid"
    assert "original file preserved" in caplog.text


def test_missing_key_for_existing_archive_never_writes_replacement(monkeypatch):
    writes = []
    monkeypatch.setattr("core.storage.secret_store.keyring.get_password", lambda *_: None)
    monkeypatch.setattr("core.storage.secret_store.keyring.set_password", lambda *args: writes.append(args))
    with pytest.raises(SecretStoreUnavailable, match="archive already exists"):
        SecretStore().get_or_create_master_key(allow_create=False)
    assert writes == []
    assert len(SecretStore().get_or_create_master_key()) == 32
    assert len(writes) == 1


def test_startup_checks_missing_key_before_changing_existing_database(tmp_path, monkeypatch):
    from core.application.paths import AppPaths
    from main import build_controller

    paths = AppPaths(tmp_path, tmp_path / "config")
    paths.database_path.write_bytes(b"EXISTING ARCHIVE")
    monkeypatch.setattr("main.default_app_paths", lambda: paths)
    monkeypatch.setattr("core.storage.secret_store.keyring.get_password", lambda *_: None)
    writes = []
    monkeypatch.setattr("core.storage.secret_store.keyring.set_password", lambda *args: writes.append(args))
    with pytest.raises(SecretStoreUnavailable, match="archive already exists"):
        build_controller()
    assert paths.database_path.read_bytes() == b"EXISTING ARCHIVE"
    assert writes == []


def test_bad_key_and_malformed_encrypted_data_raise_safe_integrity_error():
    encrypted = SensitiveStore(b"a" * 32).encrypt_text("PRIVATE VALUE")
    for payload in [encrypted, b"bad"]:
        with pytest.raises(StorageIntegrityError) as caught:
            SensitiveStore(b"b" * 32).decrypt_text(payload)
        assert "PRIVATE VALUE" not in str(caught.value)


def test_claim_support_mutation_cannot_invalidate_promoted_status(tmp_path):
    _db, repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Claim review")
    artifact = service.import_artifact(investigation.id, ArtifactKind.TEXT, ArtifactRole.TRIGGER, "text/plain", b"https://example.test/path")
    evidence = service.analyze_artifact(investigation.id, artifact.id)
    claim = service.create_claim(investigation.id, "Claim", ClaimProvenance.USER)
    service.attach_evidence(claim.id, evidence[0].id, EvidenceRelation.SUPPORTS)
    service.transition_claim(claim.id, ClaimStatus.SUPPORTED)
    with pytest.raises(ValueError, match="supporting evidence"):
        service.attach_evidence(claim.id, evidence[0].id, EvidenceRelation.CONTRADICTS)
    assert repository.supporting_evidence_count(claim.id) == 1
    service.attach_evidence(claim.id, evidence[1].id, EvidenceRelation.SUPPORTS)
    with pytest.raises(ValueError, match="distinct supporting artifacts"):
        service.transition_claim(claim.id, ClaimStatus.CORROBORATED, review_note="Not sufficient")
    duplicate = service.import_artifact(investigation.id, ArtifactKind.TEXT, ArtifactRole.SUPPORTING, "text/plain", b"https://example.test/path")
    duplicate_evidence = service.analyze_artifact(investigation.id, duplicate.id)[0]
    service.attach_evidence(claim.id, duplicate_evidence.id, EvidenceRelation.SUPPORTS)
    with pytest.raises(ValueError, match="distinct supporting artifacts"):
        service.transition_claim(claim.id, ClaimStatus.CORROBORATED, review_note="Duplicate contents are not a new source")


def test_human_review_note_is_required_encrypted_and_append_only(tmp_path):
    db, _repository, service = build_service(tmp_path)
    investigation = service.create_investigation("Human review")
    claim = service.create_claim(investigation.id, "Claim", ClaimProvenance.USER)
    for index in [1, 2]:
        artifact = service.import_artifact(investigation.id, ArtifactKind.TEXT, ArtifactRole.SUPPORTING, "text/plain", f"https://source{index}.test/".encode())
        evidence = service.analyze_artifact(investigation.id, artifact.id)[0]
        service.attach_evidence(claim.id, evidence.id, EvidenceRelation.SUPPORTS)
    service.transition_claim(claim.id, ClaimStatus.SUPPORTED)
    with pytest.raises(ValueError, match="Human review note"):
        service.transition_claim(claim.id, ClaimStatus.CORROBORATED)
    service.transition_claim(claim.id, ClaimStatus.CORROBORATED, review_note="Independent sources checked")
    with pytest.raises(ValueError, match="Human review note"):
        service.transition_claim(claim.id, ClaimStatus.VERIFIED)
    service.transition_claim(claim.id, ClaimStatus.VERIFIED, review_note="PRIVATE verification method")
    assert b"PRIVATE verification method" not in db.path.read_bytes()
    with db.connection_scope() as connection:
        assert connection.execute("SELECT COUNT(*) FROM claim_reviews").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), db.transaction() as connection:
        connection.execute("DELETE FROM claim_reviews")

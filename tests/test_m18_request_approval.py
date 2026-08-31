from __future__ import annotations

import sqlite3

import pytest

from core.application.case_service import CaseService
from core.application.deadline_engine import DeadlineEngine
from core.application.identity_service import IdentityService
from core.application.request_approval_service import RequestApprovalService
from core.application.target_service import TargetService
from core.domain.case import CaseStatus
from core.domain.identity import IdentifierKind
from core.domain.rights import CaseRight, ErasureGround, RightsPolicy
from core.storage.approved_outbound_request_repository import ApprovedOutboundRequestRepository
from core.storage.case_repository import CaseRepository
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.sensitive_store import SensitiveStore
from core.storage.target_repository import TargetRepository

TEST_KEY = b"a" * 32


def build_services(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity = IdentityService(IdentityRepository(database, sensitive))
    targets = TargetService(TargetRepository(database))
    cases = CaseService(
        CaseRepository(database),
        identity,
        targets,
        RightsPolicy(),
        DeadlineEngine(),
    )
    approvals = RequestApprovalService(
        cases,
        ApprovedOutboundRequestRepository(database, sensitive),
    )
    return database, identity, targets, cases, approvals


def create_case(tmp_path, right=CaseRight.ACCESS_PROVENANCE, *, privacy_email="privacy@example.test"):
    database, identity, targets, cases, approvals = build_services(tmp_path)
    identity.set_display_name("Alice Example")
    target = targets.create_target("Example Corp", "example.test", privacy_email)
    assert target.id is not None
    case = cases.create_case(target.id, right)
    assert case.id is not None
    return database, identity, cases, approvals, case


def test_preview_discloses_only_explicitly_selected_identifiers(tmp_path) -> None:
    _database, identity, cases, _approvals, case = create_case(tmp_path)
    email = identity.add_identifier(IdentifierKind.EMAIL, "alice@example.test", "login")
    phone = identity.add_identifier(IdentifierKind.PHONE, "+39 040 1234567", "marketing number")
    assert email.id is not None
    assert phone.id is not None

    empty = cases.preview_request(case.id)
    selected = cases.preview_request(case.id, identifier_ids=(phone.id,))

    assert "alice@example.test" not in empty.body
    assert "+39 040 1234567" not in empty.body
    assert "+39 040 1234567" in selected.body
    assert "marketing number" in selected.body
    assert "alice@example.test" not in selected.body


def test_identifier_disclosure_selection_rejects_duplicates_and_unknown_ids(tmp_path) -> None:
    _database, identity, cases, _approvals, case = create_case(tmp_path)
    identifier = identity.add_identifier(IdentifierKind.EMAIL, "alice@example.test")
    assert identifier.id is not None

    with pytest.raises(ValueError, match="duplicates"):
        cases.preview_request(case.id, identifier_ids=(identifier.id, identifier.id))
    with pytest.raises(ValueError, match="does not belong"):
        cases.preview_request(case.id, identifier_ids=(99999,))


def test_approval_requires_explicit_user_approval_without_partial_persistence(tmp_path) -> None:
    database, _identity, _cases, approvals, case = create_case(tmp_path)

    with pytest.raises(PermissionError, match="explicit user approval"):
        approvals.approve(case.id, approved_by_user=False)

    with database.connection_scope() as connection:
        count = connection.execute("SELECT COUNT(*) FROM approved_outbound_requests").fetchone()[0]
    assert count == 0


def test_approval_requires_draft_case_and_recipient_email(tmp_path) -> None:
    _database, _identity, cases, approvals, case = create_case(tmp_path)
    cases.transition_case(case.id, CaseStatus.CANCELLED)

    with pytest.raises(ValueError, match="Only a draft case"):
        approvals.approve(case.id, approved_by_user=True)

    _database2, _identity2, _cases2, approvals2, case2 = create_case(
        tmp_path / "without_email",
        privacy_email=None,
    )
    with pytest.raises(ValueError, match="privacy email"):
        approvals2.approve(case2.id, approved_by_user=True)


def test_approval_persists_exact_encrypted_payload_and_selected_metadata(tmp_path) -> None:
    database, identity, cases, approvals, case = create_case(tmp_path, CaseRight.ERASURE)
    identifier = identity.add_identifier(IdentifierKind.EMAIL, "alice@example.test", "account")
    assert identifier.id is not None

    preview = cases.preview_request(
        case.id,
        erasure_ground=ErasureGround.UNLAWFUL_PROCESSING,
        identifier_ids=(identifier.id,),
    )
    approved = approvals.approve(
        case.id,
        erasure_ground=ErasureGround.UNLAWFUL_PROCESSING,
        identifier_ids=(identifier.id,),
        approved_by_user=True,
    )

    assert approved.id is not None
    assert approved.recipient_email == preview.recipient_email
    assert approved.subject == preview.subject
    assert approved.body == preview.body
    assert approved.legal_basis == preview.legal_basis
    assert approved.identifier_ids == (identifier.id,)
    assert approved.erasure_ground is ErasureGround.UNLAWFUL_PROCESSING
    assert "alice@example.test" in approved.body

    with database.connection_scope() as connection:
        row = connection.execute(
            """
            SELECT recipient_email_enc, subject_enc, body_enc, identifier_ids_json, erasure_ground
            FROM approved_outbound_requests WHERE id = ?
            """,
            (approved.id,),
        ).fetchone()
    assert row is not None
    assert b"privacy@example.test" not in bytes(row["recipient_email_enc"])
    assert b"Alice Example" not in bytes(row["subject_enc"])
    assert b"alice@example.test" not in bytes(row["body_enc"])
    assert row["identifier_ids_json"] == f"[{identifier.id}]"
    assert row["erasure_ground"] == ErasureGround.UNLAWFUL_PROCESSING.value

    reloaded = approvals.get(approved.id)
    assert reloaded == approved
    assert "alice@example.test" not in repr(reloaded)
    assert preview.subject not in repr(reloaded)


def test_approved_payloads_are_append_only_and_reapproval_preserves_history(tmp_path) -> None:
    database, identity, _cases, approvals, case = create_case(tmp_path)
    first_identifier = identity.add_identifier(IdentifierKind.EMAIL, "first@example.test")
    second_identifier = identity.add_identifier(IdentifierKind.PHONE, "+39 040 7654321")
    assert first_identifier.id is not None
    assert second_identifier.id is not None

    first = approvals.approve(
        case.id,
        identifier_ids=(first_identifier.id,),
        approved_by_user=True,
    )
    second = approvals.approve(
        case.id,
        identifier_ids=(second_identifier.id,),
        approved_by_user=True,
    )

    assert first.id != second.id
    assert first.body != second.body
    assert [item.id for item in approvals.list_for_case(case.id)] == [second.id, first.id]

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute(
            "UPDATE approved_outbound_requests SET legal_basis = 'changed' WHERE id = ?",
            (first.id,),
        )
    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute("DELETE FROM approved_outbound_requests WHERE id = ?", (first.id,))

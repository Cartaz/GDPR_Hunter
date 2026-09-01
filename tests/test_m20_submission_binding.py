from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.application.case_service import CaseService
from core.application.deadline_engine import DeadlineEngine
from core.application.identity_service import IdentityService
from core.application.target_service import TargetService
from core.domain.case import CaseStatus
from core.domain.rights import CaseRight, RightsPolicy
from core.storage.case_repository import CaseRepository
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.sensitive_store import SensitiveStore
from core.storage.target_repository import TargetRepository
from tests.submission_support import create_approved_request_fixture

TEST_KEY = b"s" * 32


def build_case_service(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    identity = IdentityService(IdentityRepository(database, SensitiveStore(TEST_KEY)))
    targets = TargetService(TargetRepository(database))
    cases = CaseService(
        CaseRepository(database),
        identity,
        targets,
        RightsPolicy(),
        DeadlineEngine(),
    )
    return database, targets, cases


def test_submission_binds_the_explicitly_selected_approved_payload(tmp_path) -> None:
    database, targets, cases = build_case_service(tmp_path)
    target = targets.create_target("Example Corp")
    assert target.id is not None
    case = cases.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None

    older_id = create_approved_request_fixture(
        database,
        TEST_KEY,
        case.id,
        approved_at="2026-08-30T10:00:00Z",
    )
    newer_id = create_approved_request_fixture(
        database,
        TEST_KEY,
        case.id,
        approved_at="2026-08-31T10:00:00Z",
    )
    assert older_id != newer_id

    submitted = cases.submit_case(case.id, older_id, date(2026, 9, 1), "IT")
    bindings = cases.list_submission_bindings()

    assert submitted.status is CaseStatus.AWAITING_RESPONSE
    assert submitted.received_on == "2026-09-01"
    assert len(bindings) == 1
    assert bindings[0].case_id == case.id
    assert bindings[0].approved_request_id == older_id
    assert bindings[0].approved_request_id != newer_id
    assert [event.event_type for event in cases.list_timeline(case.id)] == [
        "CREATED",
        "REQUEST_SUBMITTED",
    ]


def test_wrong_case_payload_rolls_back_submission_atomically(tmp_path) -> None:
    database, targets, cases = build_case_service(tmp_path)
    target = targets.create_target("Example Corp")
    assert target.id is not None
    first = cases.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    second = cases.create_case(target.id, CaseRight.ERASURE)
    assert first.id is not None
    assert second.id is not None
    second_payload_id = create_approved_request_fixture(database, TEST_KEY, second.id)

    with pytest.raises(LookupError, match="does not belong"):
        cases.submit_case(first.id, second_payload_id, date(2026, 9, 1), "IT")

    reloaded = cases.get_case(first.id)
    assert reloaded.status is CaseStatus.DRAFT
    assert reloaded.received_on is None
    assert reloaded.deadline_snapshot is None
    assert cases.list_submission_bindings() == []
    assert [event.event_type for event in cases.list_timeline(first.id)] == ["CREATED"]


def test_nonpositive_payload_id_is_rejected_without_mutation(tmp_path) -> None:
    _database, targets, cases = build_case_service(tmp_path)
    target = targets.create_target("Example Corp")
    assert target.id is not None
    case = cases.create_case(target.id, CaseRight.DIRECT_MARKETING_OBJECTION)
    assert case.id is not None

    with pytest.raises(ValueError, match="positive"):
        cases.submit_case(case.id, 0, date(2026, 9, 1), "IT")

    assert cases.get_case(case.id).status is CaseStatus.DRAFT
    assert cases.list_submission_bindings() == []


def test_submission_binding_is_immutable_at_sqlite_boundary(tmp_path) -> None:
    database, targets, cases = build_case_service(tmp_path)
    target = targets.create_target("Example Corp")
    assert target.id is not None
    case = cases.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None
    payload_id = create_approved_request_fixture(database, TEST_KEY, case.id)
    cases.submit_case(case.id, payload_id, date(2026, 9, 1), "IT")

    with pytest.raises(sqlite3.IntegrityError, match="append-only"), database.transaction() as connection:
        connection.execute(
            "UPDATE case_submission_bindings SET confirmed_at = 'changed' WHERE case_id = ?",
            (case.id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), database.transaction() as connection:
        connection.execute(
            "DELETE FROM case_submission_bindings WHERE case_id = ?",
            (case.id,),
        )


def test_v8_migration_does_not_invent_binding_for_historical_submission(tmp_path) -> None:
    database_path = tmp_path / "legacy-v8.sqlite3"
    database = Database(database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO identities(id, display_name_enc, created_at, updated_at) VALUES (1, NULL, 'old', 'old')"
        )
        connection.execute(
            "INSERT INTO targets(id, name, domain, privacy_email, created_at, updated_at) VALUES (1, 'Legacy', NULL, NULL, 'old', 'old')"
        )
        connection.execute(
            """
            INSERT INTO cases(
                id, identity_id, target_id, right_type, status, received_on,
                extension_notified_on, deadline_jurisdiction, initial_due_on,
                extended_due_on, holiday_dates_json, holiday_source,
                holiday_calendar_complete, created_at, updated_at
            ) VALUES (
                1, 1, 1, 'ACCESS_PROVENANCE', 'AWAITING_RESPONSE', '2026-08-01',
                NULL, 'IT', '2026-09-01', '2026-11-02', '[]', 'LEGACY:test', 0,
                'old', 'old'
            )
            """
        )
        connection.execute("DROP TRIGGER case_submission_bindings_no_update")
        connection.execute("DROP TRIGGER case_submission_bindings_no_delete")
        connection.execute("DROP TABLE case_submission_bindings")
        connection.execute("UPDATE schema_meta SET schema_version = 8 WHERE id = 1")

    Database(database_path).initialize()

    with Database(database_path).connection_scope() as connection:
        version = connection.execute(
            "SELECT schema_version FROM schema_meta WHERE id = 1"
        ).fetchone()[0]
        bindings = connection.execute("SELECT * FROM case_submission_bindings").fetchall()
        legacy_case = connection.execute(
            "SELECT status, received_on FROM cases WHERE id = 1"
        ).fetchone()
    assert version == 9
    assert bindings == []
    assert legacy_case["status"] == "AWAITING_RESPONSE"
    assert legacy_case["received_on"] == "2026-08-01"


def test_frontend_and_bridge_submit_only_semantic_binding_inputs() -> None:
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "ui" / "bridge.py").read_text(encoding="utf-8")
    javascript = (root / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")

    submit_slot = bridge.split("def submitCase", 1)[1].split("def recordCaseExtension", 1)[0]
    assert "case_id: int" in submit_slot
    assert "approved_request_id: int" in submit_slot
    assert "received_on: str" in submit_slot
    assert "jurisdiction_code: str" in submit_slot
    assert "confirmed_by_user: bool" in submit_slot
    assert "subject" not in submit_slot
    assert "body" not in submit_slot
    assert "recipient" not in submit_slot

    submit_call = javascript.split("backend.submitCase(", 1)[1].split(");", 1)[0]
    assert "caseId" in submit_call
    assert "approvedRequestId" in submit_call
    assert "receivedOn" in submit_call
    assert "jurisdiction" in submit_call
    assert "confirmed" in submit_call
    assert "requestPreviewSubjectNode.value" not in submit_call
    assert "requestPreviewBodyNode.value" not in submit_call
    assert "actually transmitted" in javascript
    assert "makeSubmissionAction(caseItem.id, approvals)" in javascript

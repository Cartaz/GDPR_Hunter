from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.application.case_service import CaseService
from core.application.deadline_engine import DeadlineEngine
from core.application.identity_service import IdentityService
from core.application.response_intake_service import ResponseIntakeService
from core.application.target_service import TargetService
from core.domain.case import CaseStatus
from core.domain.response import ResponseChannel
from core.domain.rights import CaseRight, RightsPolicy
from core.storage.case_repository import CaseRepository
from core.storage.case_response_repository import CaseResponseRepository
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.sensitive_store import SensitiveStore
from core.storage.target_repository import TargetRepository
from tests.submission_support import create_approved_request_fixture

TEST_KEY = b"r" * 32


def build_submitted_case(tmp_path):
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
    target = targets.create_target("Example Corp")
    assert target.id is not None
    case = cases.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None
    payload_id = create_approved_request_fixture(database, TEST_KEY, case.id)
    submitted = cases.submit_case(case.id, payload_id, date(2026, 9, 1), "IT")
    repository = CaseResponseRepository(database, sensitive)
    service = ResponseIntakeService(cases, repository)
    return database, cases, repository, service, submitted


def test_response_requires_explicit_confirmation_without_persistence(tmp_path) -> None:
    _database, _cases, repository, service, case = build_submitted_case(tmp_path)

    with pytest.raises(PermissionError, match="explicit user confirmation"):
        service.record_response(
            case.id,
            ResponseChannel.EMAIL,
            date(2026, 9, 2),
            "privacy@example.test",
            "GDPR response",
            "We received your request.",
            confirmed_by_user=False,
        )

    assert repository.list_summaries(case.id) == []


def test_response_must_follow_submission_and_waiting_state(tmp_path) -> None:
    _database, cases, repository, service, case = build_submitted_case(tmp_path)

    with pytest.raises(ValueError, match="cannot precede"):
        service.record_response(
            case.id,
            ResponseChannel.EMAIL,
            date(2026, 8, 31),
            None,
            None,
            "Too early",
            confirmed_by_user=True,
        )
    assert repository.list_summaries(case.id) == []

    cases.transition_case(case.id, CaseStatus.COMPLETED)
    with pytest.raises(ValueError, match="awaiting response"):
        service.record_response(
            case.id,
            ResponseChannel.EMAIL,
            date(2026, 9, 2),
            None,
            None,
            "Too late for intake",
            confirmed_by_user=True,
        )


def test_response_round_trips_encrypted_content_and_summary_omits_sensitive_fields(tmp_path) -> None:
    database, _cases, repository, service, case = build_submitted_case(tmp_path)
    sender = "privacy@example.test"
    subject = "Your GDPR request"
    body = "We have located the relevant records."

    recorded = service.record_response(
        case.id,
        ResponseChannel.EMAIL,
        date(2026, 9, 2),
        sender,
        subject,
        body,
        confirmed_by_user=True,
    )
    assert recorded.id is not None

    loaded = service.get_response(recorded.id)
    assert loaded.sender == sender
    assert loaded.subject == subject
    assert loaded.body == body

    summaries = service.list_case_responses(case.id)
    assert len(summaries) == 1
    assert summaries[0].id == recorded.id
    assert not hasattr(summaries[0], "sender")
    assert not hasattr(summaries[0], "subject")
    assert not hasattr(summaries[0], "body")

    with database.connection_scope() as connection:
        row = connection.execute(
            "SELECT sender_enc, subject_enc, body_enc FROM case_responses WHERE id = ?",
            (recorded.id,),
        ).fetchone()
    assert row is not None
    assert bytes(row["sender_enc"]) != sender.encode()
    assert bytes(row["subject_enc"]) != subject.encode()
    assert bytes(row["body_enc"]) != body.encode()
    assert sender.encode() not in bytes(row["sender_enc"])
    assert subject.encode() not in bytes(row["subject_enc"])
    assert body.encode() not in bytes(row["body_enc"])


def test_multiple_responses_do_not_complete_or_recalculate_case(tmp_path) -> None:
    _database, cases, _repository, service, case = build_submitted_case(tmp_path)
    original_deadline = cases.effective_deadline_for(case)

    first = service.record_response(
        case.id,
        ResponseChannel.WEB_PORTAL,
        date(2026, 9, 2),
        None,
        "Acknowledgement",
        "Request acknowledged.",
        confirmed_by_user=True,
    )
    second = service.record_response(
        case.id,
        ResponseChannel.POSTAL_MAIL,
        date(2026, 9, 4),
        "Example Corp Privacy Team",
        None,
        "Postal response received.",
        confirmed_by_user=True,
    )

    summaries = service.list_case_responses(case.id)
    assert [item.id for item in summaries] == [second.id, first.id]
    reloaded = cases.get_case(case.id)
    assert reloaded.status is CaseStatus.AWAITING_RESPONSE
    assert cases.effective_deadline_for(reloaded) == original_deadline


def test_repository_rechecks_case_state_inside_insert_boundary(tmp_path) -> None:
    _database, cases, repository, _service, case = build_submitted_case(tmp_path)
    cases.transition_case(case.id, CaseStatus.CANCELLED)

    with pytest.raises(LookupError, match="no longer awaits"):
        repository.create(
            case.id,
            ResponseChannel.PHONE,
            date(2026, 9, 2),
            None,
            None,
            "Call notes",
        )

    assert repository.list_summaries(case.id) == []


def test_response_schema_v10_migrates_and_remains_append_only(tmp_path) -> None:
    database_path = tmp_path / "legacy-v9.sqlite3"
    database = Database(database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute("DROP TRIGGER case_responses_no_update")
        connection.execute("DROP TRIGGER case_responses_no_delete")
        connection.execute("DROP TABLE case_responses")
        connection.execute("UPDATE schema_meta SET schema_version = 9 WHERE id = 1")

    Database(database_path).initialize()
    with Database(database_path).connection_scope() as connection:
        version = connection.execute(
            "SELECT schema_version FROM schema_meta WHERE id = 1"
        ).fetchone()[0]
        response_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'case_responses'"
        ).fetchone()
    assert version == Database.CURRENT_SCHEMA_VERSION == 10
    assert response_table is not None

    database, _cases, _repository, service, case = build_submitted_case(tmp_path / "append-only")
    recorded = service.record_response(
        case.id,
        ResponseChannel.OTHER,
        date(2026, 9, 2),
        None,
        None,
        "Immutable response",
        confirmed_by_user=True,
    )
    assert recorded.id is not None
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), database.transaction() as connection:
        connection.execute(
            "UPDATE case_responses SET received_on = '2026-09-03' WHERE id = ?",
            (recorded.id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), database.transaction() as connection:
        connection.execute("DELETE FROM case_responses WHERE id = ?", (recorded.id,))


def test_frontend_loads_response_content_on_demand_not_in_bootstrap() -> None:
    root = Path(__file__).resolve().parents[1]
    controller = (root / "core" / "application" / "app_controller.py").read_text(encoding="utf-8")
    bridge = (root / "ui" / "bridge.py").read_text(encoding="utf-8")
    javascript = (root / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")

    bootstrap = controller.split("def get_bootstrap_state", 1)[1].split("def set_display_name", 1)[0]
    assert "list_case_responses" not in bootstrap
    assert "get_case_response" not in bootstrap
    assert '"responseIntake": True' in bootstrap

    record_slot = bridge.split("def recordCaseResponse", 1)[1].split("def listCaseResponses", 1)[0]
    assert "case_id: int" in record_slot
    assert "channel: str" in record_slot
    assert "received_on: str" in record_slot
    assert "sender: str" in record_slot
    assert "subject: str" in record_slot
    assert "body: str" in record_slot
    assert "confirmed_by_user: bool" in record_slot
    assert "filesystem" not in record_slot
    assert "network" not in record_slot

    assert "backend.listCaseResponses(caseId" in javascript
    assert "backend.getCaseResponse(responseId" in javascript
    assert "backend.recordCaseResponse(" in javascript
    assert "loadCaseResponses(selectedResponseCaseId)" in javascript

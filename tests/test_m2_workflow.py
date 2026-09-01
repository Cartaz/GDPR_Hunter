from __future__ import annotations

import sqlite3
from datetime import date

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

TEST_KEY = b"m" * 32


def build_services(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    identity_service = IdentityService(IdentityRepository(database, SensitiveStore(TEST_KEY)))
    target_service = TargetService(TargetRepository(database))
    case_service = CaseService(
        CaseRepository(database),
        identity_service,
        target_service,
        RightsPolicy(),
        DeadlineEngine(),
    )
    return database, target_service, case_service


def test_target_registry_normalizes_domain_and_lists_targets(tmp_path):
    _database, target_service, _case_service = build_services(tmp_path)

    target = target_service.create_target(" Example Corp ", "EXAMPLE.COM.", " privacy@example.com ")

    assert target.name == "Example Corp"
    assert target.domain == "example.com"
    assert target.privacy_email == "privacy@example.com"
    assert target_service.list_targets() == [target]


def test_duplicate_target_domain_becomes_validation_error(tmp_path):
    _database, target_service, _case_service = build_services(tmp_path)
    target_service.create_target("Example Corp", "example.com")

    with pytest.raises(ValueError, match="already registered"):
        target_service.create_target("Example Two", "EXAMPLE.COM")


def test_case_workflow_records_append_only_timeline(tmp_path):
    database, target_service, case_service = build_services(tmp_path)
    target = target_service.create_target("Example Corp", "example.com")
    assert target.id is not None

    case = case_service.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None
    assert case.status is CaseStatus.DRAFT
    approved_request_id = create_approved_request_fixture(database, TEST_KEY, case.id)

    submitted = case_service.submit_case(
        case.id,
        approved_request_id,
        date(2026, 8, 25),
        "IT",
    )
    completed = case_service.transition_case(case.id, CaseStatus.COMPLETED)
    timeline = case_service.list_timeline(case.id)

    assert submitted.status is CaseStatus.AWAITING_RESPONSE
    assert completed.status is CaseStatus.COMPLETED
    assert [event.event_type for event in timeline] == ["CREATED", "REQUEST_SUBMITTED", "STATUS_CHANGED"]
    assert [event.to_status for event in timeline] == [
        CaseStatus.DRAFT,
        CaseStatus.AWAITING_RESPONSE,
        CaseStatus.COMPLETED,
    ]

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute("DELETE FROM case_events WHERE case_id = ?", (case.id,))


def test_invalid_case_transition_does_not_append_event(tmp_path):
    _database, target_service, case_service = build_services(tmp_path)
    target = target_service.create_target("Example Corp")
    assert target.id is not None
    case = case_service.create_case(target.id, CaseRight.ERASURE)
    assert case.id is not None

    with pytest.raises(ValueError, match="Invalid case transition"):
        case_service.transition_case(case.id, CaseStatus.COMPLETED)

    timeline = case_service.list_timeline(case.id)
    assert len(timeline) == 1
    assert timeline[0].event_type == "CREATED"


def test_cancelled_case_is_terminal(tmp_path):
    database, target_service, case_service = build_services(tmp_path)
    target = target_service.create_target("Example Corp")
    assert target.id is not None
    case = case_service.create_case(target.id, CaseRight.DIRECT_MARKETING_OBJECTION)
    assert case.id is not None
    approved_request_id = create_approved_request_fixture(database, TEST_KEY, case.id)

    cancelled = case_service.transition_case(case.id, CaseStatus.CANCELLED)
    assert cancelled.status is CaseStatus.CANCELLED

    with pytest.raises(ValueError, match="Invalid case transition"):
        case_service.submit_case(
            case.id,
            approved_request_id,
            date(2026, 8, 25),
            "IT",
        )

from __future__ import annotations

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

TEST_KEY = b"r" * 32


def build_case_service(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    identity_service = IdentityService(IdentityRepository(database, SensitiveStore(TEST_KEY)))
    target_service = TargetService(TargetRepository(database))
    service = CaseService(
        CaseRepository(database),
        identity_service,
        target_service,
        RightsPolicy(),
        DeadlineEngine(),
    )
    return database, target_service, service


def test_rights_policy_supports_only_initial_m3_rights():
    policy = RightsPolicy()

    rights = policy.supported()

    assert {item.right for item in rights} == {
        CaseRight.ACCESS_PROVENANCE,
        CaseRight.ERASURE,
        CaseRight.DIRECT_MARKETING_OBJECTION,
    }
    assert "source" in policy.get(CaseRight.ACCESS_PROVENANCE).summary
    assert policy.get(CaseRight.ERASURE).requires_case_specific_ground is True
    assert policy.get(CaseRight.DIRECT_MARKETING_OBJECTION).requires_case_specific_ground is False


def test_unspecified_legacy_right_has_no_active_policy():
    with pytest.raises(ValueError, match="Legacy case"):
        RightsPolicy().get(CaseRight.UNSPECIFIED)


def test_deadline_engine_uses_calendar_months_and_month_end():
    engine = DeadlineEngine()

    leap = engine.calculate(date(2024, 1, 31))
    normal = engine.calculate(date(2025, 1, 31))

    assert leap.initial_due_on == date(2024, 2, 29)
    assert leap.extended_due_on == date(2024, 4, 30)
    assert normal.initial_due_on == date(2025, 2, 28)
    assert normal.extended_due_on == date(2025, 4, 30)


def test_deadline_engine_rolls_weekends_and_supplied_public_holidays():
    engine = DeadlineEngine()

    weekend_only = engine.calculate(date(2026, 1, 28))
    with_holiday = engine.calculate(date(2026, 1, 28), public_holidays={date(2026, 3, 2)})

    assert weekend_only.initial_due_on == date(2026, 3, 2)
    assert weekend_only.public_holiday_review_required is True
    assert with_holiday.initial_due_on == date(2026, 3, 3)
    assert with_holiday.public_holiday_review_required is False


def test_submission_persists_immutable_jurisdiction_deadline_snapshot(tmp_path):
    database, target_service, case_service = build_case_service(tmp_path)
    target = target_service.create_target("Example Corp", "example.com")
    assert target.id is not None

    case = case_service.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None
    approved_request_id = create_approved_request_fixture(database, TEST_KEY, case.id)
    submitted = case_service.submit_case(
        case.id,
        approved_request_id,
        date(2026, 1, 31),
        "it",
    )
    schedule = case_service.deadline_for(submitted)

    assert submitted.status is CaseStatus.AWAITING_RESPONSE
    assert submitted.received_on == "2026-01-31"
    assert submitted.deadline_snapshot is not None
    assert submitted.deadline_snapshot.jurisdiction_code == "IT"
    assert submitted.deadline_snapshot.initial_due_on == date(2026, 3, 2)
    assert submitted.deadline_snapshot.extended_due_on == date(2026, 4, 30)
    assert date(2026, 6, 2) in submitted.deadline_snapshot.holiday_dates
    assert date(2026, 10, 4) in submitted.deadline_snapshot.holiday_dates
    assert "L151/2025" in submitted.deadline_snapshot.holiday_source
    assert submitted.deadline_snapshot.holiday_calendar_complete is False
    assert schedule is not None
    assert schedule.initial_due_on == date(2026, 3, 2)
    assert schedule.extended_due_on == date(2026, 4, 30)
    assert schedule.public_holiday_review_required is True

    binding = case_service.list_submission_bindings()[0]
    assert binding.case_id == case.id
    assert binding.approved_request_id == approved_request_id

    extended = case_service.record_extension(case.id, date(2026, 2, 28))
    assert extended.extension_notified_on == "2026-02-28"
    assert [event.event_type for event in case_service.list_timeline(case.id)] == [
        "CREATED",
        "REQUEST_SUBMITTED",
        "EXTENSION_RECORDED",
    ]

    with database.connection_scope() as connection:
        row = connection.execute(
            """
            SELECT deadline_jurisdiction, initial_due_on, extended_due_on,
                   holiday_dates_json, holiday_source, holiday_calendar_complete
            FROM cases WHERE id = ?
            """,
            (case.id,),
        ).fetchone()
    assert row is not None
    assert row["deadline_jurisdiction"] == "IT"
    assert row["initial_due_on"] == "2026-03-02"
    assert row["extended_due_on"] == "2026-04-30"
    assert "2026-10-04" in row["holiday_dates_json"]
    assert "L151/2025" in row["holiday_source"]
    assert row["holiday_calendar_complete"] == 0


def test_extension_notice_before_recorded_receipt_is_rejected_without_mutation(tmp_path):
    database, target_service, case_service = build_case_service(tmp_path)
    target = target_service.create_target("Example Corp")
    assert target.id is not None
    case = case_service.create_case(target.id, CaseRight.ERASURE)
    assert case.id is not None
    approved_request_id = create_approved_request_fixture(database, TEST_KEY, case.id)
    case_service.submit_case(case.id, approved_request_id, date(2026, 1, 31), "IT")

    with pytest.raises(ValueError, match="cannot precede"):
        case_service.record_extension(case.id, date(2026, 1, 30))

    current = case_service.get_case(case.id)
    assert current.extension_notified_on is None
    assert [event.event_type for event in case_service.list_timeline(case.id)] == [
        "CREATED",
        "REQUEST_SUBMITTED",
    ]

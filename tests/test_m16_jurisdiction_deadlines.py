from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from core.application.case_service import CaseService
from core.application.deadline_engine import DeadlineEngine
from core.application.holiday_calendar import (
    HolidayCalendarProvider,
    ItalianHolidayCalendar,
)
from core.application.identity_service import IdentityService
from core.application.target_service import TargetService
from core.domain.rights import CaseRight, RightsPolicy
from core.storage.case_repository import CaseRepository
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.sensitive_store import SensitiveStore
from core.storage.target_repository import TargetRepository

TEST_KEY = b"j" * 32


class MutableCalendar:
    jurisdiction_code = "XX"
    source = "TEST:calendar-v1"
    complete = True

    def __init__(self, holidays: set[date]) -> None:
        self.values = holidays

    def holidays(self, year: int) -> frozenset[date]:
        return frozenset(item for item in self.values if item.year == year)


def build_case_service(tmp_path, provider: HolidayCalendarProvider | None = None):
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
        provider,
    )
    return target_service, service


def test_italian_calendar_encodes_verified_2026_national_holidays_but_requires_local_review():
    calendar = ItalianHolidayCalendar()

    holidays = calendar.holidays(2026)

    assert date(2026, 4, 6) in holidays  # Easter Monday
    assert date(2026, 6, 2) in holidays
    assert date(2026, 10, 4) in holidays
    assert date(2026, 12, 8) in holidays
    assert date(2025, 10, 4) not in calendar.holidays(2025)
    assert calendar.complete is False
    assert "L151/2025" in calendar.source


def test_provider_never_infers_or_fabricates_unsupported_jurisdiction_calendar():
    provider = HolidayCalendarProvider()

    snapshot = provider.snapshot("de", date(2026, 1, 1), date(2026, 12, 31))

    assert snapshot.jurisdiction_code == "DE"
    assert snapshot.holidays == frozenset()
    assert snapshot.source == "UNVERIFIED:DE"
    assert snapshot.complete is False
    assert snapshot.review_required is True

    with pytest.raises(ValueError, match="two-letter"):
        provider.snapshot("DEU", date(2026, 1, 1), date(2026, 12, 31))


def test_italian_submission_rolls_statutory_holiday_and_preserves_review_flag(tmp_path):
    target_service, case_service = build_case_service(tmp_path)
    target = target_service.create_target("Italian Controller")
    assert target.id is not None
    case = case_service.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None

    submitted = case_service.submit_case(case.id, date(2026, 5, 2), "IT")

    assert submitted.deadline_snapshot is not None
    assert submitted.deadline_snapshot.initial_due_on == date(2026, 6, 3)
    assert submitted.deadline_snapshot.public_holiday_review_required is True
    schedule = case_service.deadline_for(submitted)
    assert schedule is not None
    assert schedule.initial_due_on == date(2026, 6, 3)
    assert schedule.public_holiday_review_required is True


def test_unsupported_jurisdiction_is_snapshotted_without_silent_holiday_claim(tmp_path):
    target_service, case_service = build_case_service(tmp_path)
    target = target_service.create_target("German Controller")
    assert target.id is not None
    case = case_service.create_case(target.id, CaseRight.ERASURE)
    assert case.id is not None

    submitted = case_service.submit_case(case.id, date(2026, 5, 2), "DE")

    assert submitted.deadline_snapshot is not None
    assert submitted.deadline_snapshot.jurisdiction_code == "DE"
    assert submitted.deadline_snapshot.initial_due_on == date(2026, 6, 2)
    assert submitted.deadline_snapshot.holiday_dates == ()
    assert submitted.deadline_snapshot.holiday_source == "UNVERIFIED:DE"
    assert submitted.deadline_snapshot.public_holiday_review_required is True


def test_deadline_snapshot_does_not_change_when_calendar_provider_changes(tmp_path):
    calendar = MutableCalendar({date(2026, 6, 2)})
    provider = HolidayCalendarProvider((calendar,))
    target_service, case_service = build_case_service(tmp_path, provider)
    target = target_service.create_target("Snapshot Controller")
    assert target.id is not None
    case = case_service.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None

    submitted = case_service.submit_case(case.id, date(2026, 5, 2), "XX")
    assert submitted.deadline_snapshot is not None
    assert submitted.deadline_snapshot.initial_due_on == date(2026, 6, 3)
    assert submitted.deadline_snapshot.holiday_calendar_complete is True

    calendar.values.clear()
    reloaded = case_service.get_case(case.id)
    schedule = case_service.deadline_for(reloaded)

    assert reloaded.deadline_snapshot is not None
    assert reloaded.deadline_snapshot.holiday_dates == (date(2026, 6, 2),)
    assert schedule is not None
    assert schedule.initial_due_on == date(2026, 6, 3)
    assert schedule.public_holiday_review_required is False


def test_sqlite_rejects_partial_or_rewritten_deadline_snapshots(tmp_path):
    database = Database(tmp_path / "snapshot.sqlite3")
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO identities(id, display_name_enc, created_at, updated_at) VALUES (1, NULL, 'now', 'now')"
        )
        connection.execute(
            "INSERT INTO targets(id, name, domain, privacy_email, created_at, updated_at) VALUES (1, 'Target', NULL, NULL, 'now', 'now')"
        )
        connection.execute(
            """
            INSERT INTO cases(
                id, identity_id, target_id, right_type, status,
                received_on, extension_notified_on, created_at, updated_at
            )
            VALUES (1, 1, 1, 'ERASURE', 'DRAFT', NULL, NULL, 'now', 'now')
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="snapshot must be complete"):
        with database.transaction() as connection:
            connection.execute(
                "UPDATE cases SET deadline_jurisdiction = 'IT' WHERE id = 1"
            )

    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE cases
            SET deadline_jurisdiction = 'IT',
                initial_due_on = '2026-06-03',
                extended_due_on = '2026-08-03',
                holiday_dates_json = '[\"2026-06-02\"]',
                holiday_source = 'TEST:v1',
                holiday_calendar_complete = 1
            WHERE id = 1
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="snapshot is immutable"):
        with database.transaction() as connection:
            connection.execute(
                "UPDATE cases SET initial_due_on = '2026-06-04' WHERE id = 1"
            )

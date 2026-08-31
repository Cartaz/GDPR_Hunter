from __future__ import annotations

from datetime import date

from core.application.deadline_engine import DeadlineEngine, DeadlineSchedule
from core.application.holiday_calendar import HolidayCalendarProvider
from core.application.identity_service import IdentityService
from core.application.target_service import TargetService
from core.domain.case import (
    Case,
    CaseDeadlineSnapshot,
    CaseEvent,
    CaseStatus,
    validate_case_transition,
)
from core.domain.rights import CaseRight, RightPolicy, RightsPolicy
from core.storage.case_repository import CaseRepository


class CaseService:
    """Own GDPR Case creation, lifecycle transitions, rights policy, and deadline inputs."""

    def __init__(
        self,
        repository: CaseRepository,
        identity_service: IdentityService,
        target_service: TargetService,
        rights_policy: RightsPolicy,
        deadline_engine: DeadlineEngine,
        holiday_calendar_provider: HolidayCalendarProvider | None = None,
    ) -> None:
        self._repository = repository
        self._identity_service = identity_service
        self._target_service = target_service
        self._rights_policy = rights_policy
        self._deadline_engine = deadline_engine
        self._holiday_calendar_provider = holiday_calendar_provider or HolidayCalendarProvider()

    def supported_rights(self) -> tuple[RightPolicy, ...]:
        return self._rights_policy.supported()

    def create_case(self, target_id: int, right: CaseRight) -> Case:
        self._rights_policy.get(right)
        target = self._target_service.get_target(target_id)
        if target.id is None:
            raise RuntimeError("Persisted target has no id")
        identity = self._identity_service.get_identity()
        if identity.id is None:
            raise RuntimeError("Persisted identity has no id")
        return self._repository.create(identity.id, target.id, right)

    def submit_case(
        self,
        case_id: int,
        received_on: date,
        jurisdiction_code: str,
    ) -> Case:
        case = self.get_case(case_id)
        if case.right is CaseRight.UNSPECIFIED:
            raise ValueError("Legacy case must be recreated with a GDPR right before submission")
        validate_case_transition(case.status, CaseStatus.AWAITING_RESPONSE)

        _initial_nominal, extended_nominal = self._deadline_engine.nominal_due_dates(received_on)
        calendar_snapshot = self._holiday_calendar_provider.snapshot(
            jurisdiction_code,
            date(received_on.year, 1, 1),
            date(extended_nominal.year, 12, 31),
        )
        schedule = self._deadline_engine.calculate(
            received_on,
            calendar_snapshot.holidays,
            holiday_calendar_complete=calendar_snapshot.complete,
        )
        deadline_snapshot = CaseDeadlineSnapshot(
            jurisdiction_code=calendar_snapshot.jurisdiction_code,
            initial_due_on=schedule.initial_due_on,
            extended_due_on=schedule.extended_due_on,
            holiday_dates=tuple(sorted(calendar_snapshot.holidays)),
            holiday_source=calendar_snapshot.source,
            holiday_calendar_complete=calendar_snapshot.complete,
        )
        return self._repository.submit(
            case_id,
            case.status,
            received_on,
            deadline_snapshot,
        )

    def record_extension(self, case_id: int, notified_on: date) -> Case:
        case = self.get_case(case_id)
        if case.status is not CaseStatus.AWAITING_RESPONSE or case.received_on is None:
            raise ValueError("Only a submitted case awaiting response can record an extension")
        if case.extension_notified_on is not None:
            raise ValueError("An extension has already been recorded")
        schedule = self.deadline_for(case)
        if schedule is None:
            raise RuntimeError("Submitted case has no deadline inputs")
        if not self._deadline_engine.extension_notice_is_timely(notified_on, schedule):
            raise ValueError("Extension notice was not recorded within the initial one-month deadline")
        return self._repository.record_extension(case_id, notified_on)

    def transition_case(self, case_id: int, target_status: CaseStatus) -> Case:
        if target_status is CaseStatus.AWAITING_RESPONSE:
            raise ValueError("Submit the case to enter AWAITING_RESPONSE")
        case = self.get_case(case_id)
        validate_case_transition(case.status, target_status)
        return self._repository.transition(case_id, case.status, target_status)

    def get_case(self, case_id: int) -> Case:
        case = self._repository.get(case_id)
        if case is None:
            raise LookupError("Case not found")
        return case

    def list_cases(self) -> list[Case]:
        return self._repository.list_all()

    def list_timeline(self, case_id: int) -> list[CaseEvent]:
        self.get_case(case_id)
        return self._repository.list_events(case_id)

    def policy_for(self, case: Case) -> RightPolicy | None:
        if case.right is CaseRight.UNSPECIFIED:
            return None
        return self._rights_policy.get(case.right)

    def deadline_for(self, case: Case) -> DeadlineSchedule | None:
        if case.received_on is None:
            return None
        snapshot = case.deadline_snapshot
        if snapshot is not None:
            return DeadlineSchedule(
                received_on=date.fromisoformat(case.received_on),
                initial_due_on=snapshot.initial_due_on,
                extended_due_on=snapshot.extended_due_on,
                public_holiday_review_required=snapshot.public_holiday_review_required,
            )
        # Pre-M16 rows had no immutable jurisdiction/calendar snapshot. Preserve
        # their previous weekend-only display while keeping holiday review explicit.
        return self._deadline_engine.calculate(date.fromisoformat(case.received_on))

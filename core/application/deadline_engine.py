from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class ExtensionNoticeAssessment(str, Enum):
    TIMELY = "TIMELY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    LATE = "LATE"


@dataclass(frozen=True, slots=True)
class DeadlineSchedule:
    received_on: date
    initial_due_on: date
    extended_due_on: date
    public_holiday_review_required: bool


class DeadlineEngine:
    """Calculate Article 12 calendar deadlines without treating a month as 30 days."""

    def calculate(
        self,
        received_on: date,
        public_holidays: Iterable[date] | None = None,
        *,
        holiday_calendar_complete: bool | None = None,
    ) -> DeadlineSchedule:
        holidays = frozenset(public_holidays or ())
        if holiday_calendar_complete is None:
            holiday_calendar_complete = public_holidays is not None
        initial_nominal, extended_nominal = self.nominal_due_dates(received_on)
        return DeadlineSchedule(
            received_on=received_on,
            initial_due_on=self._next_working_day(initial_nominal, holidays),
            extended_due_on=self._next_working_day(extended_nominal, holidays),
            public_holiday_review_required=not holiday_calendar_complete,
        )

    def nominal_due_dates(self, received_on: date) -> tuple[date, date]:
        return self._add_months(received_on, 1), self._add_months(received_on, 3)

    @staticmethod
    def assess_extension_notice(
        notified_on: date,
        schedule: DeadlineSchedule,
    ) -> ExtensionNoticeAssessment:
        if notified_on <= schedule.initial_due_on:
            return ExtensionNoticeAssessment.TIMELY
        if schedule.public_holiday_review_required:
            return ExtensionNoticeAssessment.REVIEW_REQUIRED
        return ExtensionNoticeAssessment.LATE

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    @staticmethod
    def _next_working_day(value: date, public_holidays: frozenset[date]) -> date:
        candidate = value
        while candidate.weekday() >= 5 or candidate in public_holidays:
            candidate += timedelta(days=1)
        return candidate

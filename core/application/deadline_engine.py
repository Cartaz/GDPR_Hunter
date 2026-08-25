from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


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
        public_holidays: Iterable[date] = (),
    ) -> DeadlineSchedule:
        holidays = frozenset(public_holidays)
        initial_nominal = self._add_months(received_on, 1)
        extended_nominal = self._add_months(received_on, 3)
        return DeadlineSchedule(
            received_on=received_on,
            initial_due_on=self._next_working_day(initial_nominal, holidays),
            extended_due_on=self._next_working_day(extended_nominal, holidays),
            public_holiday_review_required=not holidays,
        )

    def extension_notice_is_timely(
        self,
        notified_on: date,
        schedule: DeadlineSchedule,
    ) -> bool:
        return notified_on <= schedule.initial_due_on

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

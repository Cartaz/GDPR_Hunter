from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

_JURISDICTION_PATTERN = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True, slots=True)
class HolidayCalendarSnapshot:
    jurisdiction_code: str
    holidays: frozenset[date]
    source: str
    complete: bool


class JurisdictionHolidayCalendar(Protocol):
    jurisdiction_code: str
    source: str
    complete: bool

    def holidays(self, year: int) -> frozenset[date]: ...


class ItalianHolidayCalendar:
    """Italian national statutory holidays verified for 2001 onward.

    Local patronal holidays are deliberately excluded because they depend on the
    controller's place of action. This calendar therefore never claims complete
    locality coverage. The 4 October national holiday applies from 2026 onward.
    """

    jurisdiction_code = "IT"
    source = "IT:L260/1949;L54/1977;DPR792/1985;L336/2000;L151/2025@2026-08-31"
    complete = False

    def holidays(self, year: int) -> frozenset[date]:
        if year < 2001:
            return frozenset()
        easter_monday = self._gregorian_easter_sunday(year) + timedelta(days=1)
        holidays = {
            date(year, 1, 1),
            date(year, 1, 6),
            date(year, 4, 25),
            easter_monday,
            date(year, 5, 1),
            date(year, 6, 2),
            date(year, 8, 15),
            date(year, 11, 1),
            date(year, 12, 8),
            date(year, 12, 25),
            date(year, 12, 26),
        }
        if year >= 2026:
            holidays.add(date(year, 10, 4))
        return frozenset(holidays)

    @staticmethod
    def _gregorian_easter_sunday(year: int) -> date:
        # Anonymous Gregorian algorithm. Keeping this deterministic avoids a
        # runtime holiday dependency while supporting the statutory Easter Monday.
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)


class HolidayCalendarProvider:
    """Resolve versioned holiday snapshots without inferring jurisdiction."""

    def __init__(self, calendars: Iterable[JurisdictionHolidayCalendar] | None = None) -> None:
        configured = tuple(calendars) if calendars is not None else (ItalianHolidayCalendar(),)
        self._calendars = {calendar.jurisdiction_code: calendar for calendar in configured}
        if len(self._calendars) != len(configured):
            raise ValueError("Duplicate holiday calendar jurisdiction")

    def snapshot(
        self,
        jurisdiction_code: str,
        start_on: date,
        end_on: date,
    ) -> HolidayCalendarSnapshot:
        code = normalize_jurisdiction_code(jurisdiction_code)
        if end_on < start_on:
            raise ValueError("Holiday calendar range is invalid")

        calendar = self._calendars.get(code)
        if calendar is None:
            return HolidayCalendarSnapshot(
                jurisdiction_code=code,
                holidays=frozenset(),
                source=f"UNVERIFIED:{code}",
                complete=False,
            )

        holidays: set[date] = set()
        for year in range(start_on.year, end_on.year + 1):
            holidays.update(
                item for item in calendar.holidays(year) if start_on <= item <= end_on
            )
        return HolidayCalendarSnapshot(
            jurisdiction_code=code,
            holidays=frozenset(holidays),
            source=calendar.source,
            complete=calendar.complete,
        )


def normalize_jurisdiction_code(value: str) -> str:
    normalized = value.strip().upper()
    if not _JURISDICTION_PATTERN.fullmatch(normalized):
        raise ValueError("Jurisdiction must be a two-letter ISO-style country code")
    return normalized

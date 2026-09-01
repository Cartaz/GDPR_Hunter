from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CaseSubmissionBinding:
    """Immutable link between a submitted Case and the exact approved payload confirmed as sent."""

    case_id: int
    approved_request_id: int
    confirmed_at: str

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CaseStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


_ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.DRAFT: frozenset({CaseStatus.OPEN, CaseStatus.CANCELLED}),
    CaseStatus.OPEN: frozenset({CaseStatus.COMPLETED, CaseStatus.CANCELLED}),
    CaseStatus.COMPLETED: frozenset(),
    CaseStatus.CANCELLED: frozenset(),
}


def validate_case_transition(current: CaseStatus, target: CaseStatus) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Invalid case transition: {current.value} -> {target.value}")


@dataclass(frozen=True, slots=True)
class Case:
    id: int | None
    identity_id: int
    target_id: int
    status: CaseStatus
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CaseEvent:
    id: int | None
    case_id: int
    event_type: str
    from_status: CaseStatus | None
    to_status: CaseStatus | None
    created_at: str

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.domain.rights import CaseRight


class CaseStatus(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_RESPONSE = "AWAITING_RESPONSE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


_ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.DRAFT: frozenset({CaseStatus.AWAITING_RESPONSE, CaseStatus.CANCELLED}),
    CaseStatus.AWAITING_RESPONSE: frozenset({CaseStatus.COMPLETED, CaseStatus.CANCELLED}),
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
    right: CaseRight
    status: CaseStatus
    created_at: str
    updated_at: str
    received_on: str | None = None
    extension_notified_on: str | None = None


@dataclass(frozen=True, slots=True)
class CaseEvent:
    id: int | None
    case_id: int
    event_type: str
    from_status: CaseStatus | None
    to_status: CaseStatus | None
    created_at: str

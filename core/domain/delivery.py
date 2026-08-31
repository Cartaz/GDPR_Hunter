from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DeliveryEventType(StrEnum):
    HANDOFF_REQUESTED = "HANDOFF_REQUESTED"
    HANDOFF_ACCEPTED = "HANDOFF_ACCEPTED"
    HANDOFF_REJECTED = "HANDOFF_REJECTED"


@dataclass(frozen=True, slots=True)
class DeliveryEvent:
    """Append-only fact about one approved-request mail-client handoff attempt."""

    id: int | None
    attempt_id: str
    approved_request_id: int
    event_type: DeliveryEventType
    created_at: str


@dataclass(frozen=True, slots=True)
class DeliveryAttemptResult:
    """Result of asking the operating system to open an approved request in a mail client."""

    attempt_id: str
    approved_request_id: int
    accepted: bool

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EgressDecision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True, slots=True)
class OutboundIntent:
    operation: str
    destination: str
    data_class: str
    approved_by_user: bool


class EgressPolicy:
    """Authorize outbound operations before any network-capable service is invoked."""

    def evaluate(self, intent: OutboundIntent) -> EgressDecision:
        if not intent.operation.strip() or not intent.destination.strip():
            raise ValueError("Outbound intent is incomplete")
        if not intent.approved_by_user:
            return EgressDecision.REQUIRE_APPROVAL
        return EgressDecision.ALLOW

    def require_allowed(self, intent: OutboundIntent) -> None:
        if self.evaluate(intent) is not EgressDecision.ALLOW:
            raise PermissionError("Outbound research requires explicit user approval")

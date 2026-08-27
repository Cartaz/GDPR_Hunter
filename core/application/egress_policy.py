from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class EgressDecision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class OutboundActor(StrEnum):
    USER = "USER"
    MODEL = "MODEL"


@dataclass(frozen=True, slots=True)
class OutboundIntent:
    operation: str
    destination: str
    data_class: str
    approved_by_user: bool
    actor: OutboundActor = OutboundActor.USER


class OutboundAuditSink(Protocol):
    def record_decision(self, intent: OutboundIntent, decision: EgressDecision) -> None: ...


class EgressPolicy:
    """Authorize outbound operations and optionally persist every policy decision."""

    def __init__(self, audit_sink: OutboundAuditSink | None = None) -> None:
        self._audit_sink = audit_sink

    def evaluate(self, intent: OutboundIntent) -> EgressDecision:
        if not intent.operation.strip() or not intent.destination.strip() or not intent.data_class.strip():
            raise ValueError("Outbound intent is incomplete")
        decision = EgressDecision.ALLOW if intent.approved_by_user else EgressDecision.REQUIRE_APPROVAL
        if self._audit_sink is not None:
            self._audit_sink.record_decision(intent, decision)
        return decision

    def require_allowed(self, intent: OutboundIntent) -> None:
        if self.evaluate(intent) is not EgressDecision.ALLOW:
            raise PermissionError("Outbound research requires explicit user approval")

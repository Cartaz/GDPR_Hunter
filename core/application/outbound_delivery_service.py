from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from core.application.case_service import CaseService
from core.application.egress_policy import EgressPolicy, OutboundActor, OutboundIntent
from core.application.request_approval_service import RequestApprovalService
from core.domain.case import CaseStatus
from core.domain.delivery import DeliveryAttemptResult, DeliveryEvent, DeliveryEventType
from core.storage.delivery_event_repository import DeliveryEventRepository


class MailClientHandoff(Protocol):
    def open_message(self, recipient_email: str, subject: str, body: str) -> bool: ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class OutboundDeliveryService:
    """Open one immutable approved request in the system mail client after explicit review."""

    def __init__(
        self,
        request_approval_service: RequestApprovalService,
        case_service: CaseService,
        egress_policy: EgressPolicy,
        event_repository: DeliveryEventRepository,
        mail_client: MailClientHandoff,
    ) -> None:
        self._request_approval_service = request_approval_service
        self._case_service = case_service
        self._egress_policy = egress_policy
        self._event_repository = event_repository
        self._mail_client = mail_client

    def handoff_approved_request(
        self,
        approved_request_id: int,
        *,
        approved_by_user: bool,
    ) -> DeliveryAttemptResult:
        if not approved_by_user:
            raise PermissionError("Mail-client handoff requires explicit user approval")
        if approved_request_id <= 0:
            raise ValueError("Approved request id must be positive")

        request = self._request_approval_service.get(approved_request_id)
        case = self._case_service.get_case(request.case_id)
        if case.status is not CaseStatus.DRAFT:
            raise ValueError("Only a draft case can hand off an approved request")

        self._egress_policy.require_allowed(
            OutboundIntent(
                operation="SYSTEM_MAIL_CLIENT_HANDOFF",
                destination=request.recipient_email,
                data_class="APPROVED_GDPR_REQUEST",
                approved_by_user=True,
                actor=OutboundActor.USER,
            )
        )

        attempt_id = uuid4().hex
        self._event_repository.record(
            attempt_id,
            approved_request_id,
            DeliveryEventType.HANDOFF_REQUESTED,
            _utc_now(),
        )
        try:
            accepted = bool(
                self._mail_client.open_message(
                    request.recipient_email,
                    request.subject,
                    request.body,
                )
            )
        except OSError:
            self._event_repository.record(
                attempt_id,
                approved_request_id,
                DeliveryEventType.HANDOFF_REJECTED,
                _utc_now(),
            )
            raise

        self._event_repository.record(
            attempt_id,
            approved_request_id,
            (
                DeliveryEventType.HANDOFF_ACCEPTED
                if accepted
                else DeliveryEventType.HANDOFF_REJECTED
            ),
            _utc_now(),
        )
        return DeliveryAttemptResult(
            attempt_id=attempt_id,
            approved_request_id=approved_request_id,
            accepted=accepted,
        )

    def list_latest_events(self) -> list[DeliveryEvent]:
        return self._event_repository.list_latest_events()

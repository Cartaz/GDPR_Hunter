from __future__ import annotations

from datetime import UTC, datetime

from core.application.case_service import CaseService
from core.domain.case import CaseStatus
from core.domain.outbound_request import ApprovedOutboundRequest, ApprovedOutboundRequestSummary
from core.domain.rights import ErasureGround
from core.storage.approved_outbound_request_repository import ApprovedOutboundRequestRepository


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class RequestApprovalService:
    """Bind explicit user approval to an immutable, exact outbound request payload."""

    def __init__(
        self,
        case_service: CaseService,
        repository: ApprovedOutboundRequestRepository,
    ) -> None:
        self._case_service = case_service
        self._repository = repository

    def approve(
        self,
        case_id: int,
        *,
        identifier_ids: tuple[int, ...] = (),
        erasure_ground: ErasureGround | None = None,
        approved_by_user: bool,
    ) -> ApprovedOutboundRequest:
        if not approved_by_user:
            raise PermissionError("Outbound request approval requires explicit user approval")
        case = self._case_service.get_case(case_id)
        if case.status is not CaseStatus.DRAFT:
            raise ValueError("Only a draft case can create a new approved outbound payload")

        preview = self._case_service.preview_request(
            case_id,
            erasure_ground=erasure_ground,
            identifier_ids=identifier_ids,
        )
        if preview.recipient_email is None:
            raise ValueError("Set a target privacy email before approving an outbound request")

        approved = ApprovedOutboundRequest(
            id=None,
            case_id=case_id,
            recipient_name=preview.recipient_name,
            recipient_email=preview.recipient_email,
            subject=preview.subject,
            body=preview.body,
            legal_basis=preview.legal_basis,
            identifier_ids=tuple(sorted(identifier_ids)),
            erasure_ground=erasure_ground,
            approved_at=_utc_now(),
        )
        return self._repository.create(approved)

    def get(self, request_id: int) -> ApprovedOutboundRequest:
        request = self._repository.get(request_id)
        if request is None:
            raise LookupError("Approved outbound request not found")
        return request

    def list_summaries(self) -> list[ApprovedOutboundRequestSummary]:
        return self._repository.list_summaries()

    def list_for_case(self, case_id: int) -> list[ApprovedOutboundRequest]:
        self._case_service.get_case(case_id)
        return self._repository.list_for_case(case_id)

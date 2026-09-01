from __future__ import annotations

from datetime import date

from core.application.case_service import CaseService
from core.domain.case import CaseStatus
from core.domain.response import CaseResponse, CaseResponseSummary, ResponseChannel
from core.storage.case_response_repository import CaseResponseRepository

_MAX_METADATA_CHARS = 1000
_MAX_BODY_CHARS = 200_000


class ResponseIntakeService:
    """Own manual controller-response intake without interpreting or completing a Case."""

    def __init__(
        self,
        case_service: CaseService,
        repository: CaseResponseRepository,
    ) -> None:
        self._case_service = case_service
        self._repository = repository

    def record_response(
        self,
        case_id: int,
        channel: ResponseChannel,
        received_on: date,
        sender: str | None,
        subject: str | None,
        body: str,
        *,
        confirmed_by_user: bool,
    ) -> CaseResponse:
        if not confirmed_by_user:
            raise PermissionError("Recording a controller response requires explicit user confirmation")
        if isinstance(case_id, bool) or case_id <= 0:
            raise ValueError("Case id must be positive")

        case = self._case_service.get_case(case_id)
        if case.status is not CaseStatus.AWAITING_RESPONSE or case.received_on is None:
            raise ValueError("Only a submitted case awaiting response can record a controller response")
        if received_on < date.fromisoformat(case.received_on):
            raise ValueError("Controller response cannot precede the recorded request receipt date")

        normalized_sender = self._normalize_optional(sender, "Sender")
        normalized_subject = self._normalize_optional(subject, "Subject")
        if not body.strip():
            raise ValueError("Response body is required")
        if len(body) > _MAX_BODY_CHARS:
            raise ValueError("Response body is too large")

        return self._repository.create(
            case_id,
            channel,
            received_on,
            normalized_sender,
            normalized_subject,
            body,
        )

    def get_response(self, response_id: int) -> CaseResponse:
        if isinstance(response_id, bool) or response_id <= 0:
            raise ValueError("Response id must be positive")
        response = self._repository.get(response_id)
        if response is None:
            raise LookupError("Case response not found")
        return response

    def list_case_responses(self, case_id: int) -> list[CaseResponseSummary]:
        if isinstance(case_id, bool) or case_id <= 0:
            raise ValueError("Case id must be positive")
        self._case_service.get_case(case_id)
        return self._repository.list_summaries(case_id)

    @staticmethod
    def _normalize_optional(value: str | None, label: str) -> str | None:
        normalized = value.strip() if value else ""
        if not normalized:
            return None
        if len(normalized) > _MAX_METADATA_CHARS:
            raise ValueError(f"{label} is too long")
        return normalized

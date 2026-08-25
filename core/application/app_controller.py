from __future__ import annotations

from datetime import date

from core.application.case_service import CaseService
from core.application.identity_service import IdentityService
from core.application.target_service import TargetService
from core.domain.case import Case, CaseEvent, CaseStatus
from core.domain.identity import IdentifierKind
from core.domain.rights import CaseRight, RightPolicy
from core.domain.target import Target


class AppController:
    """Coordinate application use cases without owning domain rules."""

    def __init__(
        self,
        identity_service: IdentityService,
        target_service: TargetService,
        case_service: CaseService,
    ) -> None:
        self._identity_service = identity_service
        self._target_service = target_service
        self._case_service = case_service

    def get_bootstrap_state(self) -> dict[str, object]:
        identity = self._identity_service.get_identity()
        identifiers = self._identity_service.list_identifiers()
        targets = self._target_service.list_targets()
        cases = self._case_service.list_cases()
        return {
            "identity": {
                "displayName": identity.display_name,
                "identifierCount": len(identifiers),
            },
            "targets": [self._target_dto(target) for target in targets],
            "rights": [self._right_dto(policy) for policy in self._case_service.supported_rights()],
            "cases": [self._case_dto(case) for case in cases],
            "milestone": "M3 — Rights Policy + Deadline Engine",
            "features": {
                "investigator": False,
                "inference": False,
                "research": False,
                "cases": True,
                "targets": True,
                "rightsPolicy": True,
                "deadlines": True,
            },
        }

    def set_display_name(self, display_name: str | None) -> dict[str, object]:
        identity = self._identity_service.set_display_name(display_name)
        return {"displayName": identity.display_name}

    def add_identifier(self, kind: str, value: str, label: str | None = None) -> dict[str, object]:
        try:
            parsed_kind = IdentifierKind(kind)
        except ValueError as exc:
            raise ValueError("Unsupported identifier kind") from exc
        identifier = self._identity_service.add_identifier(parsed_kind, value, label)
        return {"id": identifier.id, "kind": identifier.kind.value, "label": identifier.label}

    def create_target(self, name: str, domain: str | None, privacy_email: str | None) -> dict[str, object]:
        return self._target_dto(self._target_service.create_target(name, domain, privacy_email))

    def create_case(self, target_id: int, right: str) -> dict[str, object]:
        try:
            parsed_right = CaseRight(right)
        except ValueError as exc:
            raise ValueError("Unsupported GDPR right") from exc
        return self._case_dto(self._case_service.create_case(target_id, parsed_right))

    def submit_case(self, case_id: int, received_on: str) -> dict[str, object]:
        return self._case_dto(self._case_service.submit_case(case_id, self._parse_date(received_on)))

    def record_case_extension(self, case_id: int, notified_on: str) -> dict[str, object]:
        return self._case_dto(
            self._case_service.record_extension(case_id, self._parse_date(notified_on))
        )

    def transition_case(self, case_id: int, target_status: str) -> dict[str, object]:
        try:
            parsed_status = CaseStatus(target_status)
        except ValueError as exc:
            raise ValueError("Unsupported case status") from exc
        return self._case_dto(self._case_service.transition_case(case_id, parsed_status))

    def get_case_timeline(self, case_id: int) -> list[dict[str, object]]:
        return [self._event_dto(event) for event in self._case_service.list_timeline(case_id)]

    @staticmethod
    def _parse_date(value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Date must use YYYY-MM-DD format") from exc

    @staticmethod
    def _target_dto(target: Target) -> dict[str, object]:
        return {
            "id": target.id,
            "name": target.name,
            "domain": target.domain,
            "privacyEmail": target.privacy_email,
        }

    def _case_dto(self, case: Case) -> dict[str, object]:
        policy = self._case_service.policy_for(case)
        schedule = self._case_service.deadline_for(case)
        effective_due_on = None
        if schedule is not None:
            effective_due_on = (
                schedule.extended_due_on if case.extension_notified_on else schedule.initial_due_on
            )
        return {
            "id": case.id,
            "targetId": case.target_id,
            "right": case.right.value,
            "rightTitle": policy.title if policy else "Legacy unspecified case",
            "article": policy.article if policy else None,
            "status": case.status.value,
            "receivedOn": case.received_on,
            "extensionNotifiedOn": case.extension_notified_on,
            "initialDueOn": schedule.initial_due_on.isoformat() if schedule else None,
            "extendedDueOn": schedule.extended_due_on.isoformat() if schedule else None,
            "effectiveDueOn": effective_due_on.isoformat() if effective_due_on else None,
            "publicHolidayReviewRequired": (
                schedule.public_holiday_review_required if schedule else False
            ),
            "createdAt": case.created_at,
            "updatedAt": case.updated_at,
        }

    @staticmethod
    def _right_dto(policy: RightPolicy) -> dict[str, object]:
        return {
            "id": policy.right.value,
            "article": policy.article,
            "title": policy.title,
            "summary": policy.summary,
            "requiresCaseSpecificGround": policy.requires_case_specific_ground,
        }

    @staticmethod
    def _event_dto(event: CaseEvent) -> dict[str, object]:
        return {
            "id": event.id,
            "type": event.event_type,
            "fromStatus": event.from_status.value if event.from_status else None,
            "toStatus": event.to_status.value if event.to_status else None,
            "createdAt": event.created_at,
        }

from __future__ import annotations

from core.application.case_service import CaseService
from core.application.identity_service import IdentityService
from core.application.target_service import TargetService
from core.domain.case import CaseEvent, CaseStatus
from core.domain.identity import IdentifierKind
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
            "cases": [self._case_dto(case) for case in cases],
            "milestone": "M2 — Target Registry + Case Workflow",
            "features": {
                "investigator": False,
                "inference": False,
                "research": False,
                "cases": True,
                "targets": True,
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

    def create_case(self, target_id: int) -> dict[str, object]:
        return self._case_dto(self._case_service.create_case(target_id))

    def transition_case(self, case_id: int, target_status: str) -> dict[str, object]:
        try:
            parsed_status = CaseStatus(target_status)
        except ValueError as exc:
            raise ValueError("Unsupported case status") from exc
        return self._case_dto(self._case_service.transition_case(case_id, parsed_status))

    def get_case_timeline(self, case_id: int) -> list[dict[str, object]]:
        return [self._event_dto(event) for event in self._case_service.list_timeline(case_id)]

    @staticmethod
    def _target_dto(target: Target) -> dict[str, object]:
        return {
            "id": target.id,
            "name": target.name,
            "domain": target.domain,
            "privacyEmail": target.privacy_email,
        }

    @staticmethod
    def _case_dto(case) -> dict[str, object]:
        return {
            "id": case.id,
            "targetId": case.target_id,
            "status": case.status.value,
            "createdAt": case.created_at,
            "updatedAt": case.updated_at,
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

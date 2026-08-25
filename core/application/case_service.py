from __future__ import annotations

from core.application.identity_service import IdentityService
from core.application.target_service import TargetService
from core.domain.case import Case, CaseEvent, CaseStatus, validate_case_transition
from core.storage.case_repository import CaseRepository


class CaseService:
    """Own Case creation and lifecycle transitions."""

    def __init__(
        self,
        repository: CaseRepository,
        identity_service: IdentityService,
        target_service: TargetService,
    ) -> None:
        self._repository = repository
        self._identity_service = identity_service
        self._target_service = target_service

    def create_case(self, target_id: int) -> Case:
        target = self._target_service.get_target(target_id)
        if target.id is None:
            raise RuntimeError("Persisted target has no id")
        identity = self._identity_service.get_identity()
        if identity.id is None:
            raise RuntimeError("Persisted identity has no id")
        return self._repository.create(identity.id, target.id)

    def transition_case(self, case_id: int, target_status: CaseStatus) -> Case:
        case = self.get_case(case_id)
        validate_case_transition(case.status, target_status)
        return self._repository.transition(case_id, case.status, target_status)

    def get_case(self, case_id: int) -> Case:
        case = self._repository.get(case_id)
        if case is None:
            raise LookupError("Case not found")
        return case

    def list_cases(self) -> list[Case]:
        return self._repository.list_all()

    def list_timeline(self, case_id: int) -> list[CaseEvent]:
        self.get_case(case_id)
        return self._repository.list_events(case_id)

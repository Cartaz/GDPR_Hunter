from __future__ import annotations

from datetime import date

from core.application.case_service import CaseService
from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.application.request_approval_service import RequestApprovalService
from core.application.research_service import CancellationCheck
from core.application.target_service import TargetService
from core.domain.case import Case, CaseEvent, CaseStatus
from core.domain.identity import Identifier, IdentifierKind
from core.domain.investigation import (
    Artifact,
    ArtifactKind,
    ArtifactRole,
    Claim,
    ClaimProvenance,
    Evidence,
    EvidenceKind,
    EvidenceProvenance,
    Investigation,
)
from core.domain.outbound_request import ApprovedOutboundRequest
from core.domain.rights import (
    CaseRight,
    ErasureGround,
    ErasureGroundPolicy,
    RightPolicy,
)
from core.domain.target import Target


class AppController:
    """Coordinate application use cases without owning domain rules."""

    def __init__(
        self,
        identity_service: IdentityService,
        target_service: TargetService,
        case_service: CaseService,
        investigation_service: InvestigationService,
        request_approval_service: RequestApprovalService,
    ) -> None:
        self._identity_service = identity_service
        self._target_service = target_service
        self._case_service = case_service
        self._investigation_service = investigation_service
        self._request_approval_service = request_approval_service

    def get_bootstrap_state(self) -> dict[str, object]:
        identity = self._identity_service.get_identity()
        identifiers = self._identity_service.list_identifiers()
        targets = self._target_service.list_targets()
        cases = self._case_service.list_cases()
        investigations = self._investigation_service.list_investigations()
        approvals = self._request_approval_service.list_all()
        return {
            "identity": {
                "displayName": identity.display_name,
                "identifierCount": len(identifiers),
                "identifiers": [self._identifier_dto(item) for item in identifiers],
            },
            "targets": [self._target_dto(target) for target in targets],
            "rights": [self._right_dto(policy) for policy in self._case_service.supported_rights()],
            "erasureGrounds": [
                self._erasure_ground_dto(policy) for policy in self._case_service.erasure_grounds()
            ],
            "cases": [self._case_dto(case) for case in cases],
            "approvedRequests": [self._approved_request_summary_dto(item) for item in approvals],
            "investigations": [self._investigation_dto(item) for item in investigations],
            "milestone": "M18 — Approved Outbound Payloads",
            "features": {
                "investigatorCore": True,
                "artifactAnalysis": True,
                "researchFoundation": True,
                "research": True,
                "inference": True,
                "proposalReview": True,
                "reviewedResearch": True,
                "cases": True,
                "targets": True,
                "rightsPolicy": True,
                "deadlines": True,
                "jurisdictionDeadlines": True,
                "requestComposition": True,
                "requestApproval": True,
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
        return self._identifier_dto(identifier)

    def create_target(self, name: str, domain: str | None, privacy_email: str | None) -> dict[str, object]:
        return self._target_dto(self._target_service.create_target(name, domain, privacy_email))

    def create_case(self, target_id: int, right: str) -> dict[str, object]:
        try:
            parsed_right = CaseRight(right)
        except ValueError as exc:
            raise ValueError("Unsupported GDPR right") from exc
        return self._case_dto(self._case_service.create_case(target_id, parsed_right))

    def preview_case_request(
        self,
        case_id: int,
        erasure_ground: str | None = None,
        identifier_ids: tuple[int, ...] = (),
    ) -> dict[str, object]:
        parsed_ground = self._parse_erasure_ground(erasure_ground)
        preview = self._case_service.preview_request(
            case_id,
            erasure_ground=parsed_ground,
            identifier_ids=identifier_ids,
        )
        return {
            "caseId": preview.case_id,
            "recipientName": preview.recipient_name,
            "recipientEmail": preview.recipient_email,
            "subject": preview.subject,
            "body": preview.body,
            "legalBasis": preview.legal_basis,
            "identifierIds": list(sorted(identifier_ids)),
            "erasureGround": parsed_ground.value if parsed_ground else None,
        }

    def approve_case_request(
        self,
        case_id: int,
        erasure_ground: str | None,
        identifier_ids: tuple[int, ...],
        *,
        approved_by_user: bool,
    ) -> dict[str, object]:
        request = self._request_approval_service.approve(
            case_id,
            erasure_ground=self._parse_erasure_ground(erasure_ground),
            identifier_ids=identifier_ids,
            approved_by_user=approved_by_user,
        )
        return self._approved_request_dto(request)

    def submit_case(
        self,
        case_id: int,
        received_on: str,
        jurisdiction_code: str,
    ) -> dict[str, object]:
        return self._case_dto(
            self._case_service.submit_case(
                case_id,
                self._parse_date(received_on),
                jurisdiction_code,
            )
        )

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

    def create_investigation(self, title: str) -> dict[str, object]:
        return self._investigation_dto(self._investigation_service.create_investigation(title))

    def import_text_artifact(
        self,
        investigation_id: int,
        kind: str,
        role: str,
        text: str,
    ) -> dict[str, object]:
        try:
            artifact_kind = ArtifactKind(kind)
            artifact_role = ArtifactRole(role)
        except ValueError as exc:
            raise ValueError("Unsupported artifact kind or role") from exc
        artifact = self._investigation_service.import_artifact(
            investigation_id,
            artifact_kind,
            artifact_role,
            "text/plain; charset=utf-8",
            text.encode("utf-8"),
        )
        return self._artifact_dto(artifact)

    def analyze_artifact(self, investigation_id: int, artifact_id: int) -> dict[str, object]:
        created = self._investigation_service.analyze_artifact(investigation_id, artifact_id)
        return {
            "createdCount": len(created),
            "evidence": [self._evidence_dto(item) for item in created],
        }

    def research_artifact_urls(
        self,
        investigation_id: int,
        artifact_id: int,
        *,
        approved_by_user: bool,
        cancel_requested: CancellationCheck | None = None,
    ) -> dict[str, object]:
        created = self._investigation_service.research_artifact_urls(
            investigation_id,
            artifact_id,
            approved_by_user=approved_by_user,
            cancel_requested=cancel_requested,
        )
        return {
            "createdCount": len(created),
            "evidence": [self._evidence_dto(item) for item in created],
        }

    def research_model_evidence(
        self,
        investigation_id: int,
        evidence_id: int,
        *,
        approved_by_user: bool,
        cancel_requested: CancellationCheck | None = None,
    ) -> dict[str, object]:
        created = self._investigation_service.research_model_evidence(
            investigation_id,
            evidence_id,
            approved_by_user=approved_by_user,
            cancel_requested=cancel_requested,
        )
        return {
            "createdCount": len(created),
            "evidence": [self._evidence_dto(item) for item in created],
        }

    def add_user_evidence(
        self,
        investigation_id: int,
        artifact_id: int | None,
        value: str | None,
        source_locator: str | None,
    ) -> dict[str, object]:
        evidence = self._investigation_service.add_evidence(
            investigation_id,
            artifact_id,
            EvidenceKind.OBSERVATION,
            EvidenceProvenance.USER_STATEMENT,
            value,
            source_locator,
        )
        return self._evidence_dto(evidence)

    def create_user_claim(self, investigation_id: int, statement: str) -> dict[str, object]:
        claim = self._investigation_service.create_claim(
            investigation_id,
            statement,
            ClaimProvenance.USER,
        )
        return self._claim_dto(claim)

    def get_investigation_detail(self, investigation_id: int) -> dict[str, object]:
        investigations = {
            item.id: item for item in self._investigation_service.list_investigations() if item.id is not None
        }
        investigation = investigations.get(investigation_id)
        if investigation is None:
            raise LookupError("Investigation does not exist")
        return {
            "investigation": self._investigation_dto(investigation),
            "artifacts": [
                self._artifact_dto(item)
                for item in self._investigation_service.list_artifacts(investigation_id)
            ],
            "evidence": [
                self._evidence_dto(item)
                for item in self._investigation_service.list_evidence(investigation_id)
            ],
            "claims": [
                self._claim_dto(item)
                for item in self._investigation_service.list_claims(investigation_id)
            ],
        }

    @staticmethod
    def _parse_date(value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Date must use YYYY-MM-DD format") from exc

    @staticmethod
    def _parse_erasure_ground(value: str | None) -> ErasureGround | None:
        normalized = value.strip() if value else ""
        if not normalized:
            return None
        try:
            return ErasureGround(normalized)
        except ValueError as exc:
            raise ValueError("Unsupported Article 17 erasure ground") from exc

    @staticmethod
    def _identifier_dto(identifier: Identifier) -> dict[str, object]:
        return {
            "id": identifier.id,
            "kind": identifier.kind.value,
            "value": identifier.value,
            "label": identifier.label,
            "active": identifier.active,
        }

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
        effective_due_on = self._case_service.effective_deadline_for(case)
        snapshot = case.deadline_snapshot
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
            "deadlineJurisdiction": snapshot.jurisdiction_code if snapshot else None,
            "holidayCalendarSource": snapshot.holiday_source if snapshot else None,
            "createdAt": case.created_at,
            "updatedAt": case.updated_at,
        }

    @staticmethod
    def _approved_request_summary_dto(request: ApprovedOutboundRequest) -> dict[str, object]:
        return {
            "id": request.id,
            "caseId": request.case_id,
            "recipientName": request.recipient_name,
            "recipientEmail": request.recipient_email,
            "legalBasis": request.legal_basis,
            "identifierIds": list(request.identifier_ids),
            "erasureGround": request.erasure_ground.value if request.erasure_ground else None,
            "approvedAt": request.approved_at,
        }

    @staticmethod
    def _approved_request_dto(request: ApprovedOutboundRequest) -> dict[str, object]:
        result = AppController._approved_request_summary_dto(request)
        result.update({"subject": request.subject, "body": request.body})
        return result

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
    def _erasure_ground_dto(policy: ErasureGroundPolicy) -> dict[str, object]:
        return {
            "id": policy.ground.value,
            "article": policy.article,
            "title": policy.title,
            "summary": policy.summary,
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

    @staticmethod
    def _investigation_dto(investigation: Investigation) -> dict[str, object]:
        return {
            "id": investigation.id,
            "title": investigation.title,
            "status": investigation.status.value,
            "createdAt": investigation.created_at,
            "updatedAt": investigation.updated_at,
        }

    @staticmethod
    def _artifact_dto(artifact: Artifact) -> dict[str, object]:
        return {
            "id": artifact.id,
            "kind": artifact.kind.value,
            "mediaType": artifact.media_type,
            "byteSize": artifact.byte_size,
            "createdAt": artifact.created_at,
        }

    @staticmethod
    def _evidence_dto(evidence: Evidence) -> dict[str, object]:
        return {
            "id": evidence.id,
            "artifactId": evidence.artifact_id,
            "kind": evidence.kind.value,
            "provenance": evidence.provenance.value,
            "value": evidence.value,
            "sourceLocator": evidence.source_locator,
            "createdAt": evidence.created_at,
        }

    @staticmethod
    def _claim_dto(claim: Claim) -> dict[str, object]:
        return {
            "id": claim.id,
            "statement": claim.statement,
            "status": claim.status.value,
            "provenance": claim.provenance.value,
            "confidence": claim.confidence,
            "createdAt": claim.created_at,
            "updatedAt": claim.updated_at,
        }

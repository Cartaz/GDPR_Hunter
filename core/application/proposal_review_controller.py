from __future__ import annotations

from core.application.proposal_review_service import (
    ProposalReviewService,
    ReviewProposal,
)
from core.domain.investigation import Claim
from core.domain.model_proposal import (
    ClaimProposal,
    ModelProposal,
    ResearchEvidenceProposal,
)


class ProposalReviewController:
    """Expose reviewed semantic actions and DTOs without transport or Qt dependencies."""

    def __init__(self, service: ProposalReviewService) -> None:
        self._service = service

    def register(self, investigation_id: int, proposals: tuple[ModelProposal, ...]) -> dict[str, object]:
        return {"proposals": [self._proposal_dto(item) for item in self._service.register(investigation_id, proposals)]}

    def accept_claim(self, token: str, *, approved_by_user: bool) -> dict[str, object]:
        return self._claim_dto(self._service.accept_claim(token, approved_by_user=approved_by_user))

    def accept_research(self, token: str, *, approved_by_user: bool) -> dict[str, object]:
        request = self._service.accept_research(token, approved_by_user=approved_by_user)
        return {"investigationId": request.investigation_id, "evidenceId": request.evidence_id}

    def discard(self, token: str) -> None:
        self._service.discard(token)

    @staticmethod
    def _proposal_dto(reviewed: ReviewProposal) -> dict[str, object]:
        proposal = reviewed.proposal
        if isinstance(proposal, ClaimProposal):
            return {
                "token": reviewed.token,
                "kind": "CLAIM",
                "statement": proposal.statement,
                "evidenceIds": list(proposal.evidence_ids),
                "confidence": proposal.confidence,
            }
        if isinstance(proposal, ResearchEvidenceProposal):
            return {
                "token": reviewed.token,
                "kind": "RESEARCH_EVIDENCE",
                "evidenceId": proposal.evidence_id,
                "rationale": proposal.rationale,
            }
        raise TypeError("Unsupported model proposal type")

    @staticmethod
    def _claim_dto(claim: Claim) -> dict[str, object]:
        return {
            "id": claim.id,
            "statement": claim.statement,
            "status": claim.status.value,
            "provenance": claim.provenance.value,
            "confidence": claim.confidence,
            "humanReviewed": claim.human_reviewed,
            "createdAt": claim.created_at,
            "updatedAt": claim.updated_at,
        }

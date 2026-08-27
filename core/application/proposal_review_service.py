from __future__ import annotations

import secrets
from dataclasses import dataclass

from core.application.investigation_service import InvestigationService
from core.domain.investigation import Claim
from core.domain.model_proposal import ClaimProposal, ModelProposal


@dataclass(frozen=True, slots=True)
class ReviewProposal:
    token: str
    investigation_id: int
    proposal: ModelProposal


class ProposalReviewService:
    """Own ephemeral model proposals and resolve reviewed actions by opaque token."""

    def __init__(self, investigation_service: InvestigationService) -> None:
        self._investigation_service = investigation_service
        self._proposals: dict[str, ReviewProposal] = {}
        self._tokens_by_investigation: dict[int, set[str]] = {}

    def register(
        self,
        investigation_id: int,
        proposals: tuple[ModelProposal, ...],
    ) -> tuple[ReviewProposal, ...]:
        if investigation_id <= 0:
            raise ValueError("Investigation id must be positive")
        self._invalidate_investigation(investigation_id)

        registered: list[ReviewProposal] = []
        tokens: set[str] = set()
        for proposal in proposals:
            token = self._new_token()
            reviewed = ReviewProposal(token, investigation_id, proposal)
            self._proposals[token] = reviewed
            tokens.add(token)
            registered.append(reviewed)
        if tokens:
            self._tokens_by_investigation[investigation_id] = tokens
        return tuple(registered)

    def accept_claim(self, token: str, *, approved_by_user: bool) -> Claim:
        normalized = token.strip()
        if not normalized:
            raise ValueError("Proposal token is required")
        reviewed = self._proposals.get(normalized)
        if reviewed is None:
            raise LookupError("Proposal token is unknown, expired, or already used")
        if not isinstance(reviewed.proposal, ClaimProposal):
            raise TypeError("Only claim proposals can be accepted as claims")

        claim = self._investigation_service.accept_model_claim(
            reviewed.investigation_id,
            reviewed.proposal,
            approved_by_user=approved_by_user,
        )
        self._consume(normalized, reviewed.investigation_id)
        return claim

    def discard(self, token: str) -> None:
        normalized = token.strip()
        reviewed = self._proposals.get(normalized)
        if reviewed is None:
            raise LookupError("Proposal token is unknown, expired, or already used")
        self._consume(normalized, reviewed.investigation_id)

    def _invalidate_investigation(self, investigation_id: int) -> None:
        for token in self._tokens_by_investigation.pop(investigation_id, set()):
            self._proposals.pop(token, None)

    def _consume(self, token: str, investigation_id: int) -> None:
        self._proposals.pop(token, None)
        tokens = self._tokens_by_investigation.get(investigation_id)
        if tokens is None:
            return
        tokens.discard(token)
        if not tokens:
            self._tokens_by_investigation.pop(investigation_id, None)

    def _new_token(self) -> str:
        while True:
            token = secrets.token_urlsafe(24)
            if token not in self._proposals:
                return token

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModelProposalKind(StrEnum):
    CLAIM = "CLAIM"
    RESEARCH_EVIDENCE = "RESEARCH_EVIDENCE"


@dataclass(frozen=True, slots=True)
class ClaimProposal:
    statement: str
    evidence_ids: tuple[int, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class ResearchEvidenceProposal:
    evidence_id: int
    rationale: str


ModelProposal = ClaimProposal | ResearchEvidenceProposal

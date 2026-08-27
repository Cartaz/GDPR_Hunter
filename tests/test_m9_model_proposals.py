from __future__ import annotations

import pytest

from core.application.model_proposal_parser import (
    ModelProposalParser,
    ModelProposalValidationError,
)
from core.domain.model_proposal import ClaimProposal, ResearchEvidenceProposal


def test_parser_accepts_typed_inert_proposals() -> None:
    proposals = ModelProposalParser().parse(
        {
            "proposals": [
                {
                    "kind": "CLAIM",
                    "statement": "The sender appears related to Example Ltd.",
                    "evidence_ids": [3, 7],
                    "confidence": 0.75,
                },
                {
                    "kind": "RESEARCH_EVIDENCE",
                    "evidence_id": 7,
                    "rationale": "The evidence contains a deterministically extracted URL.",
                },
            ]
        },
        available_evidence_ids={3, 7, 9},
    )

    assert proposals == (
        ClaimProposal("The sender appears related to Example Ltd.", (3, 7), 0.75),
        ResearchEvidenceProposal(7, "The evidence contains a deterministically extracted URL."),
    )


def test_parser_rejects_unknown_fields_that_could_smuggle_actions() -> None:
    with pytest.raises(ModelProposalValidationError, match="unexpected or missing"):
        ModelProposalParser().parse(
            {
                "proposals": [
                    {
                        "kind": "RESEARCH_EVIDENCE",
                        "evidence_id": 7,
                        "rationale": "Research it.",
                        "url": "https://attacker.invalid/",
                    }
                ]
            },
            available_evidence_ids={7},
        )


def test_parser_rejects_evidence_not_in_current_context() -> None:
    with pytest.raises(ModelProposalValidationError, match="unavailable evidence"):
        ModelProposalParser().parse(
            {
                "proposals": [
                    {
                        "kind": "CLAIM",
                        "statement": "Unsupported claim",
                        "evidence_ids": [999],
                        "confidence": 0.5,
                    }
                ]
            },
            available_evidence_ids={1, 2},
        )


def test_parser_rejects_claim_without_evidence() -> None:
    with pytest.raises(ModelProposalValidationError, match="cite evidence_ids"):
        ModelProposalParser().parse(
            {
                "proposals": [
                    {
                        "kind": "CLAIM",
                        "statement": "Unsupported claim",
                        "evidence_ids": [],
                        "confidence": 0.5,
                    }
                ]
            },
            available_evidence_ids={1},
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01, True, "0.5"])
def test_parser_rejects_invalid_confidence(confidence: object) -> None:
    with pytest.raises(ModelProposalValidationError):
        ModelProposalParser().parse(
            {
                "proposals": [
                    {
                        "kind": "CLAIM",
                        "statement": "Claim",
                        "evidence_ids": [1],
                        "confidence": confidence,
                    }
                ]
            },
            available_evidence_ids={1},
        )


def test_parser_rejects_unbounded_proposal_count() -> None:
    proposal = {
        "kind": "RESEARCH_EVIDENCE",
        "evidence_id": 1,
        "rationale": "Research existing evidence.",
    }
    with pytest.raises(ModelProposalValidationError, match="Too many"):
        ModelProposalParser().parse(
            {"proposals": [proposal for _ in range(21)]},
            available_evidence_ids={1},
        )

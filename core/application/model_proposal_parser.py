from __future__ import annotations

from typing import Any

from core.domain.model_proposal import (
    ClaimProposal,
    ModelProposal,
    ModelProposalKind,
    ResearchEvidenceProposal,
)


class ModelProposalValidationError(ValueError):
    pass


class ModelProposalParser:
    """Validate model JSON into inert proposals referencing existing evidence only."""

    def parse(self, payload: object, *, available_evidence_ids: set[int]) -> tuple[ModelProposal, ...]:
        root = self._object(payload, "Proposal response")
        self._require_exact_keys(root, {"proposals"}, "Proposal response")
        raw_proposals = root["proposals"]
        if not isinstance(raw_proposals, list):
            raise ModelProposalValidationError("proposals must be a list")
        if len(raw_proposals) > 20:
            raise ModelProposalValidationError("Too many model proposals")

        parsed: list[ModelProposal] = []
        for index, raw in enumerate(raw_proposals):
            item = self._object(raw, f"Proposal {index}")
            kind_value = item.get("kind")
            try:
                kind = ModelProposalKind(kind_value)
            except (TypeError, ValueError) as exc:
                raise ModelProposalValidationError(f"Proposal {index} has unsupported kind") from exc
            if kind is ModelProposalKind.CLAIM:
                parsed.append(self._parse_claim(item, index, available_evidence_ids))
            else:
                parsed.append(self._parse_research(item, index, available_evidence_ids))
        return tuple(parsed)

    def _parse_claim(
        self,
        item: dict[str, Any],
        index: int,
        available_evidence_ids: set[int],
    ) -> ClaimProposal:
        self._require_exact_keys(
            item,
            {"kind", "statement", "evidence_ids", "confidence"},
            f"Proposal {index}",
        )
        statement = self._bounded_text(item["statement"], "statement", 2_000)
        raw_ids = item["evidence_ids"]
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ModelProposalValidationError("Claim proposal must cite evidence_ids")
        evidence_ids = tuple(self._evidence_id(value, available_evidence_ids) for value in raw_ids)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ModelProposalValidationError("Claim proposal contains duplicate evidence_ids")
        confidence = item["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ModelProposalValidationError("confidence must be numeric")
        numeric_confidence = float(confidence)
        if numeric_confidence < 0.0 or numeric_confidence > 1.0:
            raise ModelProposalValidationError("confidence must be between 0 and 1")
        return ClaimProposal(statement, evidence_ids, numeric_confidence)

    def _parse_research(
        self,
        item: dict[str, Any],
        index: int,
        available_evidence_ids: set[int],
    ) -> ResearchEvidenceProposal:
        self._require_exact_keys(
            item,
            {"kind", "evidence_id", "rationale"},
            f"Proposal {index}",
        )
        evidence_id = self._evidence_id(item["evidence_id"], available_evidence_ids)
        rationale = self._bounded_text(item["rationale"], "rationale", 1_000)
        return ResearchEvidenceProposal(evidence_id, rationale)

    @staticmethod
    def _object(value: object, label: str) -> dict[str, Any]:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ModelProposalValidationError(f"{label} must be an object with string keys")
        return value

    @staticmethod
    def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
        if set(value) != expected:
            raise ModelProposalValidationError(f"{label} has unexpected or missing fields")

    @staticmethod
    def _bounded_text(value: object, label: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ModelProposalValidationError(f"{label} must be non-empty text")
        normalized = value.strip()
        if len(normalized) > maximum:
            raise ModelProposalValidationError(f"{label} is too long")
        return normalized

    @staticmethod
    def _evidence_id(value: object, available_evidence_ids: set[int]) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ModelProposalValidationError("Evidence id must be a positive integer")
        if value not in available_evidence_ids:
            raise ModelProposalValidationError("Model proposal references unavailable evidence")
        return value

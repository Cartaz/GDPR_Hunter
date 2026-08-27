from __future__ import annotations

import json
from typing import Protocol

from core.application.egress_policy import EgressPolicy, OutboundIntent
from core.application.investigation_service import InvestigationService
from core.application.model_proposal_parser import ModelProposalParser
from core.domain.model_proposal import ModelProposal


class InferenceClient(Protocol):
    @property
    def destination(self) -> str: ...

    def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, object]: ...


class ModelAnalysisService:
    """Generate inert typed proposals from a bounded snapshot of Investigation Evidence."""

    MAX_EVIDENCE_ITEMS = 50
    MAX_CONTEXT_CHARS = 32_000
    SYSTEM_PROMPT = (
        "You analyse GDPR investigation evidence. Return JSON only with exactly one top-level key "
        "named proposals. Each proposal must be either "
        '{"kind":"CLAIM","statement":string,"evidence_ids":[integer,...],"confidence":number} '
        "or "
        '{"kind":"RESEARCH_EVIDENCE","evidence_id":integer,"rationale":string}. '
        "Use only evidence IDs present in the supplied context. Do not invent URLs, commands, tools, "
        "evidence, or actions. Claims are hypotheses for human review, not facts."
    )

    def __init__(
        self,
        investigation_service: InvestigationService,
        inference: InferenceClient,
        parser: ModelProposalParser,
        egress_policy: EgressPolicy,
        *,
        model: str,
    ) -> None:
        if not model.strip():
            raise ValueError("Inference model is required")
        self._investigation_service = investigation_service
        self._inference = inference
        self._parser = parser
        self._egress_policy = egress_policy
        self._model = model.strip()

    def propose(
        self,
        investigation_id: int,
        *,
        approved_by_user: bool,
    ) -> tuple[ModelProposal, ...]:
        evidence = self._investigation_service.list_evidence(investigation_id)
        if not evidence:
            raise ValueError("Model analysis requires existing evidence")
        if len(evidence) > self.MAX_EVIDENCE_ITEMS:
            raise ValueError("Investigation has too many evidence items for one model analysis")

        evidence_rows = [
            {
                "id": item.id,
                "kind": item.kind.value,
                "provenance": item.provenance.value,
                "value": item.value,
                "source_locator": item.source_locator,
            }
            for item in evidence
            if item.id is not None
        ]
        available_ids = {int(row["id"]) for row in evidence_rows}
        if not available_ids:
            raise ValueError("Model analysis requires persisted evidence")

        user_prompt = json.dumps(
            {"investigation_id": investigation_id, "evidence": evidence_rows},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(user_prompt) > self.MAX_CONTEXT_CHARS:
            raise ValueError("Investigation evidence exceeds the model-analysis context limit")

        self._egress_policy.require_allowed(
            OutboundIntent(
                operation="MODEL_INFERENCE",
                destination=self._inference.destination,
                data_class="INVESTIGATION_EVIDENCE",
                approved_by_user=approved_by_user,
            )
        )
        payload = self._inference.complete_json(
            model=self._model,
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self._parser.parse(payload, available_evidence_ids=available_ids)

from __future__ import annotations

import json

import pytest

from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.egress_policy import EgressDecision, EgressPolicy, OutboundIntent
from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.application.model_analysis_service import ModelAnalysisService
from core.application.model_proposal_parser import (
    ModelProposalParser,
    ModelProposalValidationError,
)
from core.domain.investigation import EvidenceKind, EvidenceProvenance
from core.domain.model_proposal import ClaimProposal, ResearchEvidenceProposal
from core.storage.artifact_store import ArtifactStore
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.investigation_repository import InvestigationRepository
from core.storage.sensitive_store import SensitiveStore

TEST_KEY = b"a" * 32


class RecordingInference:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls: list[tuple[str, str, str]] = []

    @property
    def destination(self) -> str:
        return "http://192.168.1.50:8080"

    def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, object]:
        self.calls.append((model, system_prompt, user_prompt))
        return self._payload


class RecordingAuditSink:
    def __init__(self) -> None:
        self.entries: list[tuple[OutboundIntent, EgressDecision]] = []

    def record_decision(self, intent: OutboundIntent, decision: EgressDecision) -> None:
        self.entries.append((intent, decision))


def build_investigation_service(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity = IdentityService(IdentityRepository(database, sensitive))
    service = InvestigationService(
        InvestigationRepository(database, sensitive),
        ArtifactStore(tmp_path / "artifacts", sensitive),
        identity,
        ArtifactAnalyzer(),
    )
    return database, service


def add_evidence(service: InvestigationService, investigation_id: int, value: str):
    evidence = service.add_evidence(
        investigation_id,
        None,
        EvidenceKind.OBSERVATION,
        EvidenceProvenance.DETERMINISTIC_ANALYSIS,
        value,
        "test.observation",
    )
    assert evidence.id is not None
    return evidence


def test_model_analysis_returns_only_typed_inert_proposals(tmp_path) -> None:
    _database, investigation_service = build_investigation_service(tmp_path)
    investigation = investigation_service.create_investigation("Model analysis")
    assert investigation.id is not None
    first = add_evidence(investigation_service, investigation.id, "Example Ltd sent the SMS")
    second = add_evidence(investigation_service, investigation.id, "Privacy URL points to Example Ltd")
    inference = RecordingInference(
        {
            "proposals": [
                {
                    "kind": "CLAIM",
                    "statement": "Example Ltd may control the campaign",
                    "evidence_ids": [first.id, second.id],
                    "confidence": 0.8,
                },
                {
                    "kind": "RESEARCH_EVIDENCE",
                    "evidence_id": second.id,
                    "rationale": "The cited privacy evidence could justify further reviewed research.",
                },
            ]
        }
    )
    audit = RecordingAuditSink()
    service = ModelAnalysisService(
        investigation_service,
        inference,
        ModelProposalParser(),
        EgressPolicy(audit),
        model="local-model",
    )

    proposals = service.propose(investigation.id, approved_by_user=True)

    assert isinstance(proposals[0], ClaimProposal)
    assert isinstance(proposals[1], ResearchEvidenceProposal)
    assert investigation_service.list_claims(investigation.id) == []
    assert len(inference.calls) == 1
    model, system_prompt, user_prompt = inference.calls[0]
    assert model == "local-model"
    assert "Do not invent URLs" in system_prompt
    context = json.loads(user_prompt)
    assert context["investigation_id"] == investigation.id
    assert {row["id"] for row in context["evidence"]} == {first.id, second.id}
    assert len(audit.entries) == 1
    intent, decision = audit.entries[0]
    assert intent.operation == "MODEL_INFERENCE"
    assert intent.destination == inference.destination
    assert intent.data_class == "INVESTIGATION_EVIDENCE"
    assert decision is EgressDecision.ALLOW


def test_model_analysis_requires_approval_before_inference(tmp_path) -> None:
    _database, investigation_service = build_investigation_service(tmp_path)
    investigation = investigation_service.create_investigation("No approval")
    assert investigation.id is not None
    evidence = add_evidence(investigation_service, investigation.id, "Sensitive investigation evidence")
    inference = RecordingInference({"proposals": []})
    audit = RecordingAuditSink()
    service = ModelAnalysisService(
        investigation_service,
        inference,
        ModelProposalParser(),
        EgressPolicy(audit),
        model="local-model",
    )

    with pytest.raises(PermissionError, match="approval"):
        service.propose(investigation.id, approved_by_user=False)

    assert evidence.id is not None
    assert inference.calls == []
    assert len(audit.entries) == 1
    assert audit.entries[0][1] is EgressDecision.REQUIRE_APPROVAL


def test_model_analysis_rejects_model_reference_to_unavailable_evidence(tmp_path) -> None:
    _database, investigation_service = build_investigation_service(tmp_path)
    investigation = investigation_service.create_investigation("Bad model output")
    assert investigation.id is not None
    add_evidence(investigation_service, investigation.id, "Known evidence")
    inference = RecordingInference(
        {
            "proposals": [
                {
                    "kind": "CLAIM",
                    "statement": "Invented support",
                    "evidence_ids": [999],
                    "confidence": 0.9,
                }
            ]
        }
    )
    service = ModelAnalysisService(
        investigation_service,
        inference,
        ModelProposalParser(),
        EgressPolicy(),
        model="local-model",
    )

    with pytest.raises(ModelProposalValidationError, match="unavailable evidence"):
        service.propose(investigation.id, approved_by_user=True)

    assert investigation_service.list_claims(investigation.id) == []


def test_model_analysis_rejects_empty_and_oversized_context_without_inference(tmp_path) -> None:
    _database, investigation_service = build_investigation_service(tmp_path)
    empty = investigation_service.create_investigation("Empty")
    assert empty.id is not None
    inference = RecordingInference({"proposals": []})
    service = ModelAnalysisService(
        investigation_service,
        inference,
        ModelProposalParser(),
        EgressPolicy(),
        model="local-model",
    )

    with pytest.raises(ValueError, match="existing evidence"):
        service.propose(empty.id, approved_by_user=True)
    assert inference.calls == []

    large = investigation_service.create_investigation("Large")
    assert large.id is not None
    add_evidence(investigation_service, large.id, "x" * ModelAnalysisService.MAX_CONTEXT_CHARS)
    with pytest.raises(ValueError, match="context limit"):
        service.propose(large.id, approved_by_user=True)
    assert inference.calls == []

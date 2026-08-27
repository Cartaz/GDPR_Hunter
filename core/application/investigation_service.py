from __future__ import annotations

from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.egress_policy import EgressPolicy, OutboundIntent
from core.application.identity_service import IdentityService
from core.application.research_service import ResearchService
from core.domain.investigation import (
    Artifact,
    ArtifactKind,
    ArtifactRole,
    Claim,
    ClaimProvenance,
    ClaimStatus,
    Evidence,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRelation,
    Investigation,
    InvestigationStatus,
    validate_claim_transition,
    validate_investigation_transition,
)
from core.domain.model_proposal import ClaimProposal
from core.storage.artifact_store import ArtifactStore
from core.storage.investigation_repository import InvestigationRepository


class InvestigationService:
    """Own investigation state, deterministic analysis, research, evidence, claims, and artifacts."""

    MAX_ARTIFACT_BYTES = 2 * 1024 * 1024

    def __init__(
        self,
        repository: InvestigationRepository,
        artifact_store: ArtifactStore,
        identity_service: IdentityService,
        artifact_analyzer: ArtifactAnalyzer,
        research_service: ResearchService | None = None,
        egress_policy: EgressPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._identity_service = identity_service
        self._artifact_analyzer = artifact_analyzer
        self._research_service = research_service
        self._egress_policy = egress_policy

    def create_investigation(self, title: str | None) -> Investigation:
        identity = self._identity_service.get_identity()
        normalized = title.strip() if title and title.strip() else None
        return self._repository.create_investigation(self._require_id(identity.id), normalized)

    def list_investigations(self) -> list[Investigation]:
        return self._repository.list_investigations()

    def transition(self, investigation_id: int, target: InvestigationStatus) -> Investigation:
        investigation = self._require_investigation(investigation_id)
        validate_investigation_transition(investigation.status, target)
        return self._repository.transition_investigation(investigation_id, investigation.status, target)

    def import_artifact(
        self,
        investigation_id: int,
        kind: ArtifactKind,
        role: ArtifactRole,
        media_type: str,
        payload: bytes,
    ) -> Artifact:
        self._require_investigation(investigation_id)
        if not payload:
            raise ValueError("Artifact payload cannot be empty")
        if len(payload) > self.MAX_ARTIFACT_BYTES:
            raise ValueError("Artifact exceeds the current size limit")
        normalized_media_type = media_type.strip().lower()
        if not normalized_media_type:
            raise ValueError("Artifact media type is required")
        storage_key = self._artifact_store.store(payload)
        try:
            return self._repository.add_artifact_metadata(
                investigation_id, storage_key, kind, normalized_media_type, payload, role
            )
        except Exception:
            self._artifact_store.delete(storage_key)
            raise

    def list_artifacts(self, investigation_id: int) -> list[Artifact]:
        self._require_investigation(investigation_id)
        return self._repository.list_artifacts(investigation_id)

    def analyze_artifact(self, investigation_id: int, artifact_id: int) -> list[Evidence]:
        self._require_investigation(investigation_id)
        artifact = next(
            (item for item in self._repository.list_artifacts(investigation_id) if item.id == artifact_id),
            None,
        )
        if artifact is None:
            raise LookupError("Artifact is not attached to this investigation")
        payload = self._artifact_store.read(artifact.storage_key)
        findings = self._artifact_analyzer.analyze(artifact.kind, payload)
        existing = {
            (item.artifact_id, item.kind, item.provenance, item.value, item.source_locator)
            for item in self._repository.list_evidence(investigation_id)
        }
        created: list[Evidence] = []
        for candidate in findings:
            key = (
                artifact_id,
                candidate.kind,
                candidate.provenance,
                candidate.value,
                candidate.source_locator,
            )
            if key in existing:
                continue
            evidence = self.add_evidence(
                investigation_id,
                artifact_id,
                candidate.kind,
                candidate.provenance,
                candidate.value,
                candidate.source_locator,
            )
            created.append(evidence)
            existing.add(key)
        return created

    def research_artifact_urls(
        self,
        investigation_id: int,
        artifact_id: int,
        *,
        approved_by_user: bool,
    ) -> list[Evidence]:
        self._require_investigation(investigation_id)
        if self._research_service is None or self._egress_policy is None:
            raise RuntimeError("Research capability is not configured")

        source_evidence = [
            item
            for item in self._repository.list_evidence(investigation_id)
            if item.artifact_id == artifact_id
            and item.provenance is EvidenceProvenance.DETERMINISTIC_ANALYSIS
            and item.value is not None
            and item.value.lower().startswith(("http://", "https://"))
        ]
        if not source_evidence:
            raise ValueError("Analyze the artifact before researching its public URLs")

        existing = {
            (item.provenance, item.value, item.source_locator)
            for item in self._repository.list_evidence(investigation_id)
        }
        created: list[Evidence] = []
        for source in source_evidence:
            source_url = source.value
            if source_url is None:
                continue
            marker = f"research.request:{source_url}"
            if (EvidenceProvenance.REMOTE_DOCUMENT, source_url, marker) in existing:
                continue

            self._egress_policy.require_allowed(
                OutboundIntent(
                    operation="PUBLIC_RESEARCH_FETCH",
                    destination=source_url,
                    data_class="PUBLIC_OR_OBSERVED_URL",
                    approved_by_user=approved_by_user,
                )
            )
            document = self._research_service.fetch_public_document(source_url)
            reference = self.import_artifact(
                investigation_id,
                ArtifactKind.TEXT,
                ArtifactRole.REFERENCE,
                document.content_type,
                document.body,
            )
            created.append(
                self.add_evidence(
                    investigation_id,
                    reference.id,
                    EvidenceKind.OBSERVATION,
                    EvidenceProvenance.REMOTE_DOCUMENT,
                    source_url,
                    marker,
                )
            )
            for index, hop in enumerate(document.redirects):
                created.append(
                    self.add_evidence(
                        investigation_id,
                        reference.id,
                        EvidenceKind.OBSERVATION,
                        EvidenceProvenance.REMOTE_DOCUMENT,
                        f"{hop.status} {hop.source_url} -> {hop.destination_url}",
                        f"research.redirect[{index}]",
                    )
                )
            created.append(
                self.add_evidence(
                    investigation_id,
                    reference.id,
                    EvidenceKind.OBSERVATION,
                    EvidenceProvenance.REMOTE_DOCUMENT,
                    document.final_url,
                    "research.final_url",
                )
            )
            if reference.id is not None:
                created.extend(self.analyze_artifact(investigation_id, reference.id))
            existing.add((EvidenceProvenance.REMOTE_DOCUMENT, source_url, marker))
        return created

    def add_evidence(
        self,
        investigation_id: int,
        artifact_id: int | None,
        kind: EvidenceKind,
        provenance: EvidenceProvenance,
        value: str | None,
        source_locator: str | None,
    ) -> Evidence:
        self._require_investigation(investigation_id)
        if value is None and source_locator is None:
            raise ValueError("Evidence requires a value or source locator")
        return self._repository.add_evidence(
            investigation_id, artifact_id, kind, provenance, value, source_locator
        )

    def list_evidence(self, investigation_id: int) -> list[Evidence]:
        self._require_investigation(investigation_id)
        return self._repository.list_evidence(investigation_id)

    def create_claim(
        self,
        investigation_id: int,
        statement: str,
        provenance: ClaimProvenance,
        confidence: float | None = None,
    ) -> Claim:
        self._require_investigation(investigation_id)
        normalized = statement.strip()
        if not normalized:
            raise ValueError("Claim statement is required")
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError("Claim confidence must be between 0 and 1")
        return self._repository.create_claim(investigation_id, normalized, provenance, confidence)

    def accept_model_claim(
        self,
        investigation_id: int,
        proposal: ClaimProposal,
        *,
        approved_by_user: bool,
    ) -> Claim:
        self._require_investigation(investigation_id)
        if not approved_by_user:
            raise PermissionError("Model claim requires explicit user review and approval")
        normalized = proposal.statement.strip()
        if not normalized:
            raise ValueError("Model claim statement is required")
        if not proposal.evidence_ids:
            raise ValueError("Model claim requires supporting evidence")
        if len(set(proposal.evidence_ids)) != len(proposal.evidence_ids):
            raise ValueError("Model claim contains duplicate evidence ids")
        if not 0.0 <= proposal.confidence <= 1.0:
            raise ValueError("Model claim confidence must be between 0 and 1")
        return self._repository.create_model_claim_with_supporting_evidence(
            investigation_id,
            normalized,
            proposal.confidence,
            proposal.evidence_ids,
        )

    def list_claims(self, investigation_id: int) -> list[Claim]:
        self._require_investigation(investigation_id)
        return self._repository.list_claims(investigation_id)

    def attach_evidence(self, claim_id: int, evidence_id: int, relation: EvidenceRelation) -> None:
        self._repository.attach_evidence(claim_id, evidence_id, relation)

    def transition_claim(self, claim_id: int, target: ClaimStatus) -> Claim:
        claim = self._repository.get_claim(claim_id)
        if claim is None:
            raise LookupError("Claim does not exist")
        validate_claim_transition(claim.status, target)
        supporting_count = self._repository.supporting_evidence_count(claim_id)
        if target is ClaimStatus.SUPPORTED and supporting_count < 1:
            raise ValueError("Supported claims require supporting evidence")
        if target in {ClaimStatus.CORROBORATED, ClaimStatus.VERIFIED} and supporting_count < 2:
            raise ValueError("Corroborated or verified claims require at least two supporting evidence items")
        return self._repository.update_claim_status(claim_id, claim.status, target)

    def _require_investigation(self, investigation_id: int) -> Investigation:
        investigation = self._repository.get_investigation(investigation_id)
        if investigation is None:
            raise LookupError("Investigation does not exist")
        return investigation

    @staticmethod
    def _require_id(value: int | None) -> int:
        if value is None:
            raise RuntimeError("Persisted identity is missing an id")
        return value

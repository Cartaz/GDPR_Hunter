from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class InvestigationStatus(StrEnum):
    OPEN = "OPEN"
    ANALYSING = "ANALYSING"
    ACTIONABLE = "ACTIONABLE"
    CONCLUDED = "CONCLUDED"
    INCONCLUSIVE = "INCONCLUSIVE"
    ARCHIVED = "ARCHIVED"


_ALLOWED_INVESTIGATION_TRANSITIONS: dict[InvestigationStatus, frozenset[InvestigationStatus]] = {
    InvestigationStatus.OPEN: frozenset(
        {
            InvestigationStatus.ANALYSING,
            InvestigationStatus.INCONCLUSIVE,
            InvestigationStatus.ARCHIVED,
        }
    ),
    InvestigationStatus.ANALYSING: frozenset(
        {
            InvestigationStatus.OPEN,
            InvestigationStatus.ACTIONABLE,
            InvestigationStatus.CONCLUDED,
            InvestigationStatus.INCONCLUSIVE,
        }
    ),
    InvestigationStatus.ACTIONABLE: frozenset(
        {
            InvestigationStatus.ANALYSING,
            InvestigationStatus.CONCLUDED,
            InvestigationStatus.INCONCLUSIVE,
            InvestigationStatus.ARCHIVED,
        }
    ),
    InvestigationStatus.CONCLUDED: frozenset(
        {InvestigationStatus.ANALYSING, InvestigationStatus.ARCHIVED}
    ),
    InvestigationStatus.INCONCLUSIVE: frozenset(
        {InvestigationStatus.ANALYSING, InvestigationStatus.ARCHIVED}
    ),
    InvestigationStatus.ARCHIVED: frozenset({InvestigationStatus.OPEN}),
}


def validate_investigation_transition(
    current: InvestigationStatus,
    target: InvestigationStatus,
) -> None:
    if target not in _ALLOWED_INVESTIGATION_TRANSITIONS[current]:
        raise ValueError(f"Invalid investigation transition: {current.value} -> {target.value}")


class ArtifactKind(StrEnum):
    SMS = "SMS"
    EMAIL = "EMAIL"
    URL = "URL"
    TEXT = "TEXT"
    COMPANY_RESPONSE = "COMPANY_RESPONSE"


class ArtifactRole(StrEnum):
    TRIGGER = "TRIGGER"
    SUPPORTING = "SUPPORTING"
    RESPONSE = "RESPONSE"
    REFERENCE = "REFERENCE"


class EvidenceKind(StrEnum):
    EXTRACTED_FIELD = "EXTRACTED_FIELD"
    OBSERVATION = "OBSERVATION"
    SOURCE_STATEMENT = "SOURCE_STATEMENT"


class EvidenceProvenance(StrEnum):
    USER_STATEMENT = "USER_STATEMENT"
    DETERMINISTIC_ANALYSIS = "DETERMINISTIC_ANALYSIS"
    REMOTE_DOCUMENT = "REMOTE_DOCUMENT"
    COMPANY_RESPONSE = "COMPANY_RESPONSE"
    AUTHORITATIVE_SOURCE = "AUTHORITATIVE_SOURCE"


class ClaimStatus(StrEnum):
    HYPOTHESIS = "HYPOTHESIS"
    SUPPORTED = "SUPPORTED"
    CORROBORATED = "CORROBORATED"
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    REJECTED = "REJECTED"


_ALLOWED_CLAIM_TRANSITIONS: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.HYPOTHESIS: frozenset(
        {ClaimStatus.SUPPORTED, ClaimStatus.CONTRADICTED, ClaimStatus.REJECTED}
    ),
    ClaimStatus.SUPPORTED: frozenset(
        {ClaimStatus.CORROBORATED, ClaimStatus.CONTRADICTED, ClaimStatus.REJECTED}
    ),
    ClaimStatus.CORROBORATED: frozenset(
        {ClaimStatus.VERIFIED, ClaimStatus.CONTRADICTED, ClaimStatus.REJECTED}
    ),
    ClaimStatus.VERIFIED: frozenset({ClaimStatus.CONTRADICTED}),
    ClaimStatus.CONTRADICTED: frozenset(
        {ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED, ClaimStatus.REJECTED}
    ),
    ClaimStatus.REJECTED: frozenset(),
}


def validate_claim_transition(current: ClaimStatus, target: ClaimStatus) -> None:
    if target not in _ALLOWED_CLAIM_TRANSITIONS[current]:
        raise ValueError(f"Invalid claim transition: {current.value} -> {target.value}")


class ClaimProvenance(StrEnum):
    USER = "USER"
    DETERMINISTIC = "DETERMINISTIC"
    MODEL_INFERENCE = "MODEL_INFERENCE"


class EvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"


@dataclass(frozen=True, slots=True)
class Investigation:
    id: int | None
    identity_id: int
    title: str | None = field(repr=False)
    status: InvestigationStatus
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class Artifact:
    id: int | None
    storage_key: str = field(repr=False)
    kind: ArtifactKind
    media_type: str
    byte_size: int
    created_at: str


@dataclass(frozen=True, slots=True)
class Evidence:
    id: int | None
    investigation_id: int
    artifact_id: int | None
    kind: EvidenceKind
    provenance: EvidenceProvenance
    value: str | None = field(repr=False)
    source_locator: str | None = field(repr=False)
    created_at: str


@dataclass(frozen=True, slots=True)
class Claim:
    id: int | None
    investigation_id: int
    statement: str = field(repr=False)
    status: ClaimStatus
    provenance: ClaimProvenance
    confidence: float | None
    created_at: str
    updated_at: str

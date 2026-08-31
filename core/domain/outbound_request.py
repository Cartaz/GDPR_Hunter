from __future__ import annotations

from dataclasses import dataclass

from core.domain.rights import ErasureGround


@dataclass(frozen=True, slots=True)
class ApprovedOutboundRequest:
    """Immutable user-approved request payload for a future outbound attempt."""

    id: int | None
    case_id: int
    recipient_name: str
    recipient_email: str
    subject: str
    body: str
    legal_basis: str
    identifier_ids: tuple[int, ...]
    erasure_ground: ErasureGround | None
    approved_at: str

    def __repr__(self) -> str:
        return (
            "ApprovedOutboundRequest("
            f"id={self.id!r}, case_id={self.case_id!r}, recipient_name={self.recipient_name!r}, "
            "recipient_email='<redacted>', subject='<redacted>', body='<redacted>', "
            f"legal_basis={self.legal_basis!r}, identifier_ids={self.identifier_ids!r}, "
            f"erasure_ground={self.erasure_ground.value if self.erasure_ground else None!r}, "
            f"approved_at={self.approved_at!r})"
        )

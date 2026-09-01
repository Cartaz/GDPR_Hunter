from __future__ import annotations

from core.domain.outbound_request import ApprovedOutboundRequest
from core.storage.approved_outbound_request_repository import (
    ApprovedOutboundRequestRepository,
)
from core.storage.database import Database
from core.storage.sensitive_store import SensitiveStore


def create_approved_request_fixture(
    database: Database,
    key: bytes,
    case_id: int,
    *,
    approved_at: str = "2026-01-01T00:00:00Z",
) -> int:
    """Persist the minimal valid immutable payload needed by submission-focused tests."""
    persisted = ApprovedOutboundRequestRepository(database, SensitiveStore(key)).create(
        ApprovedOutboundRequest(
            id=None,
            case_id=case_id,
            recipient_name="Fixture Controller",
            recipient_email="privacy@example.test",
            subject="Fixture approved request",
            body="Fixture approved body",
            legal_basis="Fixture legal basis",
            identifier_ids=(),
            erasure_ground=None,
            approved_at=approved_at,
        )
    )
    if persisted.id is None:
        raise RuntimeError("Approved request fixture was not persisted")
    return persisted.id

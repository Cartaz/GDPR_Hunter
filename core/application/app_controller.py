from __future__ import annotations

from core.application.identity_service import IdentityService
from core.domain.identity import IdentifierKind


class AppController:
    """Coordinate application use cases without owning domain rules."""

    def __init__(self, identity_service: IdentityService) -> None:
        self._identity_service = identity_service

    def get_bootstrap_state(self) -> dict[str, object]:
        identity = self._identity_service.get_identity()
        identifiers = self._identity_service.list_identifiers()
        return {
            "identity": {
                "displayName": identity.display_name,
                "identifierCount": len(identifiers),
            },
            "milestone": "M1 — Foundation",
            "features": {
                "investigator": False,
                "inference": False,
                "research": False,
                "cases": False,
            },
        }

    def set_display_name(self, display_name: str | None) -> dict[str, object]:
        identity = self._identity_service.set_display_name(display_name)
        return {"displayName": identity.display_name}

    def add_identifier(self, kind: str, value: str, label: str | None = None) -> dict[str, object]:
        try:
            parsed_kind = IdentifierKind(kind)
        except ValueError as exc:
            raise ValueError("Unsupported identifier kind") from exc
        identifier = self._identity_service.add_identifier(parsed_kind, value, label)
        return {
            "id": identifier.id,
            "kind": identifier.kind.value,
            "label": identifier.label,
        }

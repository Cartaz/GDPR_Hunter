from __future__ import annotations

from core.domain.identity import Identifier, IdentifierKind, Identity
from core.storage.identity_repository import IdentityRepository


class IdentityService:
    """Own identity and identifier mutations."""

    def __init__(self, repository: IdentityRepository) -> None:
        self._repository = repository

    def get_identity(self) -> Identity:
        return self._repository.get_or_create_identity()

    def set_display_name(self, display_name: str | None) -> Identity:
        identity = self.get_identity()
        if identity.id is None:
            raise RuntimeError("Persisted identity has no id")
        normalized = display_name.strip() if display_name else None
        return self._repository.set_display_name(identity.id, normalized or None)

    def add_identifier(
        self,
        kind: IdentifierKind,
        value: str,
        label: str | None = None,
    ) -> Identifier:
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("Identifier value cannot be empty")
        identity = self.get_identity()
        if identity.id is None:
            raise RuntimeError("Persisted identity has no id")
        normalized_label = label.strip() if label else None
        return self._repository.add_identifier(
            identity.id,
            kind,
            normalized_value,
            normalized_label or None,
        )

    def list_identifiers(self) -> list[Identifier]:
        identity = self.get_identity()
        if identity.id is None:
            raise RuntimeError("Persisted identity has no id")
        return self._repository.list_identifiers(identity.id)

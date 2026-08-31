from __future__ import annotations

from core.domain.identity import Identifier, IdentifierKind, Identity
from core.storage.identity_repository import IdentityRepository


class IdentityService:
    """Own identity and identifier mutations and disclosure selection."""

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

    def identifiers_for_disclosure(self, identifier_ids: tuple[int, ...]) -> tuple[Identifier, ...]:
        if len(identifier_ids) != len(set(identifier_ids)):
            raise ValueError("Identifier disclosure selection contains duplicates")
        if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in identifier_ids):
            raise ValueError("Identifier disclosure ids must be positive integers")

        identifiers = {item.id: item for item in self.list_identifiers() if item.id is not None}
        selected: list[Identifier] = []
        for identifier_id in sorted(identifier_ids):
            identifier = identifiers.get(identifier_id)
            if identifier is None:
                raise ValueError("Selected identifier does not belong to the local identity")
            if not identifier.active:
                raise ValueError("Selected identifier is inactive")
            selected.append(identifier)
        return tuple(selected)

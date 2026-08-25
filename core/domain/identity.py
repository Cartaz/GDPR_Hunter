from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IdentifierKind(StrEnum):
    FULL_NAME = "FULL_NAME"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    ADDRESS = "ADDRESS"
    USERNAME = "USERNAME"
    PROFILE_URL = "PROFILE_URL"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True, slots=True)
class Identifier:
    id: int | None
    kind: IdentifierKind
    value: str
    label: str | None = None
    active: bool = True

    def __repr__(self) -> str:
        return (
            f"Identifier(id={self.id!r}, kind={self.kind.value!r}, "
            f"value='<redacted>', label={'<redacted>' if self.label else None!r}, active={self.active!r})"
        )


@dataclass(frozen=True, slots=True)
class Identity:
    id: int | None
    display_name: str | None = None

    def __repr__(self) -> str:
        return f"Identity(id={self.id!r}, display_name={'<redacted>' if self.display_name else None!r})"

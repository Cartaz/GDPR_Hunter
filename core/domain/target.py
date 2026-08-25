from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Target:
    """A data holder or controller the user may exercise rights against."""

    id: int | None
    name: str
    domain: str | None
    privacy_email: str | None
    created_at: str
    updated_at: str

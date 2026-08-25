from __future__ import annotations

import re
import sqlite3

from core.domain.target import Target
from core.storage.target_repository import TargetRepository

_DOMAIN_PATTERN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class TargetService:
    """Own Target registry validation and mutations."""

    def __init__(self, repository: TargetRepository) -> None:
        self._repository = repository

    def create_target(self, name: str, domain: str | None = None, privacy_email: str | None = None) -> Target:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Target name cannot be empty")

        normalized_domain = domain.strip().lower().rstrip(".") if domain else None
        if normalized_domain and not _DOMAIN_PATTERN.fullmatch(normalized_domain):
            raise ValueError("Target domain must be a hostname such as example.com")

        normalized_email = privacy_email.strip() if privacy_email else None
        if normalized_email and (
            normalized_email.count("@") != 1
            or normalized_email.startswith("@")
            or normalized_email.endswith("@")
        ):
            raise ValueError("Privacy email is invalid")

        try:
            return self._repository.create(
                normalized_name,
                normalized_domain or None,
                normalized_email or None,
            )
        except sqlite3.IntegrityError as exc:
            if normalized_domain:
                raise ValueError("Target domain is already registered") from exc
            raise

    def get_target(self, target_id: int) -> Target:
        target = self._repository.get(target_id)
        if target is None:
            raise LookupError("Target not found")
        return target

    def list_targets(self) -> list[Target]:
        return self._repository.list_all()

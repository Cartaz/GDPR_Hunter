from __future__ import annotations

from core.domain.target import Target
from core.storage.database import Database


class TargetRepository:
    """Persist Target records without owning validation or workflow rules."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, name: str, domain: str | None, privacy_email: str | None) -> Target:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO targets(name, domain, privacy_email, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (name, domain, privacy_email),
            )
            target_id = int(cursor.lastrowid)
            row = connection.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
        if row is None:
            raise RuntimeError("Created target could not be reloaded")
        return self._from_row(row)

    def get(self, target_id: int) -> Target | None:
        with self._database.connect() as connection:
            row = connection.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
        return self._from_row(row) if row is not None else None

    def list_all(self) -> list[Target]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT * FROM targets ORDER BY name COLLATE NOCASE, id").fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row) -> Target:
        return Target(
            id=int(row["id"]),
            name=str(row["name"]),
            domain=str(row["domain"]) if row["domain"] is not None else None,
            privacy_email=str(row["privacy_email"]) if row["privacy_email"] is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

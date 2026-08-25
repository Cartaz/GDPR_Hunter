from __future__ import annotations

import sqlite3

from core.domain.case import Case, CaseEvent, CaseStatus
from core.storage.database import Database


class CaseRepository:
    """Persist cases and append-only timeline events atomically."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, identity_id: int, target_id: int) -> Case:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO cases(identity_id, target_id, status, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (identity_id, target_id, CaseStatus.DRAFT.value),
            )
            case_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO case_events(case_id, event_type, from_status, to_status, created_at)
                VALUES (?, 'CREATED', NULL, ?, datetime('now'))
                """,
                (case_id, CaseStatus.DRAFT.value),
            )
            row = connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise RuntimeError("Created case could not be reloaded")
        return self._case_from_row(row)

    def get(self, case_id: int) -> Case | None:
        with self._database.connect() as connection:
            row = connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        return self._case_from_row(row) if row is not None else None

    def list_all(self) -> list[Case]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT * FROM cases ORDER BY created_at DESC, id DESC").fetchall()
        return [self._case_from_row(row) for row in rows]

    def transition(self, case_id: int, expected: CaseStatus, target: CaseStatus) -> Case:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE cases
                SET status = ?, updated_at = datetime('now')
                WHERE id = ? AND status = ?
                """,
                (target.value, case_id, expected.value),
            )
            if cursor.rowcount != 1:
                raise LookupError("Case changed or no longer exists")
            connection.execute(
                """
                INSERT INTO case_events(case_id, event_type, from_status, to_status, created_at)
                VALUES (?, 'STATUS_CHANGED', ?, ?, datetime('now'))
                """,
                (case_id, expected.value, target.value),
            )
            row = connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise RuntimeError("Updated case could not be reloaded")
        return self._case_from_row(row)

    def list_events(self, case_id: int) -> list[CaseEvent]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM case_events WHERE case_id = ? ORDER BY id",
                (case_id,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    @staticmethod
    def _case_from_row(row: sqlite3.Row) -> Case:
        return Case(
            id=int(row["id"]),
            identity_id=int(row["identity_id"]),
            target_id=int(row["target_id"]),
            status=CaseStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> CaseEvent:
        return CaseEvent(
            id=int(row["id"]),
            case_id=int(row["case_id"]),
            event_type=str(row["event_type"]),
            from_status=CaseStatus(str(row["from_status"])) if row["from_status"] is not None else None,
            to_status=CaseStatus(str(row["to_status"])) if row["to_status"] is not None else None,
            created_at=str(row["created_at"]),
        )

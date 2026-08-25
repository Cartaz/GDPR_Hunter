from __future__ import annotations

import sqlite3
from datetime import date

from core.domain.case import Case, CaseEvent, CaseStatus
from core.domain.rights import CaseRight
from core.storage.database import Database


class CaseRepository:
    """Persist cases and append-only timeline events atomically."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, identity_id: int, target_id: int, right: CaseRight) -> Case:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO cases(
                    identity_id, target_id, right_type, status,
                    received_on, extension_notified_on, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, NULL, NULL, datetime('now'), datetime('now'))
                """,
                (identity_id, target_id, right.value, CaseStatus.DRAFT.value),
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
        with self._database.connection_scope() as connection:
            row = connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        return self._case_from_row(row) if row is not None else None

    def list_all(self) -> list[Case]:
        with self._database.connection_scope() as connection:
            rows = connection.execute("SELECT * FROM cases ORDER BY created_at DESC, id DESC").fetchall()
        return [self._case_from_row(row) for row in rows]

    def submit(self, case_id: int, expected: CaseStatus, received_on: date) -> Case:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE cases
                SET status = ?, received_on = ?, updated_at = datetime('now')
                WHERE id = ? AND status = ? AND received_on IS NULL
                """,
                (
                    CaseStatus.AWAITING_RESPONSE.value,
                    received_on.isoformat(),
                    case_id,
                    expected.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError("Case changed, was already submitted, or no longer exists")
            connection.execute(
                """
                INSERT INTO case_events(case_id, event_type, from_status, to_status, created_at)
                VALUES (?, 'REQUEST_SUBMITTED', ?, ?, datetime('now'))
                """,
                (case_id, expected.value, CaseStatus.AWAITING_RESPONSE.value),
            )
            row = connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise RuntimeError("Submitted case could not be reloaded")
        return self._case_from_row(row)

    def record_extension(self, case_id: int, notified_on: date) -> Case:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE cases
                SET extension_notified_on = ?, updated_at = datetime('now')
                WHERE id = ? AND status = ? AND extension_notified_on IS NULL
                """,
                (notified_on.isoformat(), case_id, CaseStatus.AWAITING_RESPONSE.value),
            )
            if cursor.rowcount != 1:
                raise LookupError("Case changed, extension already recorded, or no longer awaits a response")
            connection.execute(
                """
                INSERT INTO case_events(case_id, event_type, from_status, to_status, created_at)
                VALUES (?, 'EXTENSION_RECORDED', ?, ?, datetime('now'))
                """,
                (
                    case_id,
                    CaseStatus.AWAITING_RESPONSE.value,
                    CaseStatus.AWAITING_RESPONSE.value,
                ),
            )
            row = connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise RuntimeError("Extended case could not be reloaded")
        return self._case_from_row(row)

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
        with self._database.connection_scope() as connection:
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
            right=CaseRight(str(row["right_type"])),
            status=CaseStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            received_on=str(row["received_on"]) if row["received_on"] is not None else None,
            extension_notified_on=(
                str(row["extension_notified_on"])
                if row["extension_notified_on"] is not None
                else None
            ),
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

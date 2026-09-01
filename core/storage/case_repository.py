from __future__ import annotations

import json
import sqlite3
from datetime import date

from core.domain.case import Case, CaseDeadlineSnapshot, CaseEvent, CaseStatus
from core.domain.rights import CaseRight
from core.domain.submission import CaseSubmissionBinding
from core.storage.database import Database


class CaseRepository:
    """Persist cases, immutable submission bindings, and append-only timeline events atomically."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, identity_id: int, target_id: int, right: CaseRight) -> Case:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO cases(
                    identity_id, target_id, right_type, status,
                    received_on, extension_notified_on,
                    deadline_jurisdiction, initial_due_on, extended_due_on,
                    holiday_dates_json, holiday_source, holiday_calendar_complete,
                    created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, NULL, NULL,
                    NULL, NULL, NULL, NULL, NULL, NULL,
                    datetime('now'), datetime('now')
                )
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

    def submit(
        self,
        case_id: int,
        expected: CaseStatus,
        approved_request_id: int,
        received_on: date,
        deadline_snapshot: CaseDeadlineSnapshot,
    ) -> Case:
        holiday_dates_json = json.dumps(
            [item.isoformat() for item in deadline_snapshot.holiday_dates],
            separators=(",", ":"),
        )
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE cases
                SET status = ?, received_on = ?,
                    deadline_jurisdiction = ?, initial_due_on = ?, extended_due_on = ?,
                    holiday_dates_json = ?, holiday_source = ?, holiday_calendar_complete = ?,
                    updated_at = datetime('now')
                WHERE id = ? AND status = ? AND received_on IS NULL
                """,
                (
                    CaseStatus.AWAITING_RESPONSE.value,
                    received_on.isoformat(),
                    deadline_snapshot.jurisdiction_code,
                    deadline_snapshot.initial_due_on.isoformat(),
                    deadline_snapshot.extended_due_on.isoformat(),
                    holiday_dates_json,
                    deadline_snapshot.holiday_source,
                    int(deadline_snapshot.holiday_calendar_complete),
                    case_id,
                    expected.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError("Case changed, was already submitted, or no longer exists")

            binding_cursor = connection.execute(
                """
                INSERT INTO case_submission_bindings(case_id, approved_request_id, confirmed_at)
                SELECT ?, id, datetime('now')
                FROM approved_outbound_requests
                WHERE id = ? AND case_id = ?
                """,
                (case_id, approved_request_id, case_id),
            )
            if binding_cursor.rowcount != 1:
                raise LookupError("Approved request not found or does not belong to this case")

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

    def list_submission_bindings(self) -> list[CaseSubmissionBinding]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT case_id, approved_request_id, confirmed_at
                FROM case_submission_bindings
                ORDER BY confirmed_at DESC, case_id DESC
                """
            ).fetchall()
        return [self._submission_binding_from_row(row) for row in rows]

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
            deadline_snapshot=CaseRepository._deadline_snapshot_from_row(row),
        )

    @staticmethod
    def _deadline_snapshot_from_row(row: sqlite3.Row) -> CaseDeadlineSnapshot | None:
        fields = (
            row["deadline_jurisdiction"],
            row["initial_due_on"],
            row["extended_due_on"],
            row["holiday_dates_json"],
            row["holiday_source"],
            row["holiday_calendar_complete"],
        )
        if all(value is None for value in fields):
            return None
        if any(value is None for value in fields):
            raise RuntimeError("Persisted case deadline snapshot is incomplete")
        try:
            raw_dates = json.loads(str(row["holiday_dates_json"]))
            if not isinstance(raw_dates, list) or not all(isinstance(item, str) for item in raw_dates):
                raise ValueError
            holiday_dates = tuple(date.fromisoformat(item) for item in raw_dates)
            initial_due_on = date.fromisoformat(str(row["initial_due_on"]))
            extended_due_on = date.fromisoformat(str(row["extended_due_on"]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Persisted case deadline snapshot is malformed") from exc
        complete = int(row["holiday_calendar_complete"])
        if complete not in {0, 1}:
            raise RuntimeError("Persisted holiday calendar completeness is invalid")
        return CaseDeadlineSnapshot(
            jurisdiction_code=str(row["deadline_jurisdiction"]),
            initial_due_on=initial_due_on,
            extended_due_on=extended_due_on,
            holiday_dates=holiday_dates,
            holiday_source=str(row["holiday_source"]),
            holiday_calendar_complete=bool(complete),
        )

    @staticmethod
    def _submission_binding_from_row(row: sqlite3.Row) -> CaseSubmissionBinding:
        return CaseSubmissionBinding(
            case_id=int(row["case_id"]),
            approved_request_id=int(row["approved_request_id"]),
            confirmed_at=str(row["confirmed_at"]),
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

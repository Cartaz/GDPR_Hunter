from __future__ import annotations

import sqlite3
from datetime import date

from core.domain.response import CaseResponse, CaseResponseSummary, ResponseChannel
from core.storage.database import Database
from core.storage.sensitive_store import SensitiveStore


class CaseResponseRepository:
    """Persist encrypted, append-only controller responses for GDPR Cases."""

    def __init__(self, database: Database, sensitive_store: SensitiveStore) -> None:
        self._database = database
        self._sensitive_store = sensitive_store

    def create(
        self,
        case_id: int,
        channel: ResponseChannel,
        received_on: date,
        sender: str | None,
        subject: str | None,
        body: str,
    ) -> CaseResponse:
        sender_enc = self._sensitive_store.encrypt_text(sender) if sender is not None else None
        subject_enc = self._sensitive_store.encrypt_text(subject) if subject is not None else None
        body_enc = self._sensitive_store.encrypt_text(body)
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO case_responses(
                    case_id, channel, received_on, sender_enc, subject_enc, body_enc, recorded_at
                )
                SELECT id, ?, ?, ?, ?, ?, datetime('now')
                FROM cases
                WHERE id = ? AND status = 'AWAITING_RESPONSE'
                """,
                (
                    channel.value,
                    received_on.isoformat(),
                    sender_enc,
                    subject_enc,
                    body_enc,
                    case_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError("Case changed, does not exist, or no longer awaits a response")
            response_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM case_responses WHERE id = ?",
                (response_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Recorded case response could not be reloaded")
        return self._from_row(row)

    def get(self, response_id: int) -> CaseResponse | None:
        with self._database.connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM case_responses WHERE id = ?",
                (response_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def list_summaries(self, case_id: int) -> list[CaseResponseSummary]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT id, case_id, channel, received_on, recorded_at
                FROM case_responses
                WHERE case_id = ?
                ORDER BY received_on DESC, id DESC
                """,
                (case_id,),
            ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    @staticmethod
    def _summary_from_row(row: sqlite3.Row) -> CaseResponseSummary:
        try:
            channel = ResponseChannel(str(row["channel"]))
            received_on = date.fromisoformat(str(row["received_on"]))
        except ValueError as exc:
            raise RuntimeError("Persisted case response metadata is malformed") from exc
        return CaseResponseSummary(
            id=int(row["id"]),
            case_id=int(row["case_id"]),
            channel=channel,
            received_on=received_on,
            recorded_at=str(row["recorded_at"]),
        )

    def _from_row(self, row: sqlite3.Row) -> CaseResponse:
        summary = self._summary_from_row(row)
        return CaseResponse(
            id=summary.id,
            case_id=summary.case_id,
            channel=summary.channel,
            received_on=summary.received_on,
            sender=(
                self._sensitive_store.decrypt_text(row["sender_enc"])
                if row["sender_enc"] is not None
                else None
            ),
            subject=(
                self._sensitive_store.decrypt_text(row["subject_enc"])
                if row["subject_enc"] is not None
                else None
            ),
            body=self._sensitive_store.decrypt_text(row["body_enc"]),
            recorded_at=summary.recorded_at,
        )

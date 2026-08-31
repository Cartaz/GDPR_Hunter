from __future__ import annotations

import json
import sqlite3

from core.domain.outbound_request import (
    ApprovedOutboundRequest,
    ApprovedOutboundRequestSummary,
)
from core.domain.rights import ErasureGround
from core.storage.database import Database
from core.storage.sensitive_store import SensitiveStore


class ApprovedOutboundRequestRepository:
    """Persist encrypted, append-only user-approved request payloads."""

    def __init__(self, database: Database, sensitive_store: SensitiveStore) -> None:
        self._database = database
        self._sensitive_store = sensitive_store

    def create(self, request: ApprovedOutboundRequest) -> ApprovedOutboundRequest:
        if request.id is not None:
            raise ValueError("Approved outbound request is already persisted")
        identifier_ids_json = json.dumps(list(request.identifier_ids), separators=(",", ":"))
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO approved_outbound_requests(
                    case_id, recipient_name, recipient_email_enc, subject_enc, body_enc,
                    legal_basis, identifier_ids_json, erasure_ground, approved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.case_id,
                    request.recipient_name,
                    self._sensitive_store.encrypt_text(request.recipient_email),
                    self._sensitive_store.encrypt_text(request.subject),
                    self._sensitive_store.encrypt_text(request.body),
                    request.legal_basis,
                    identifier_ids_json,
                    request.erasure_ground.value if request.erasure_ground else None,
                    request.approved_at,
                ),
            )
            request_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM approved_outbound_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Approved outbound request could not be reloaded")
        return self._from_row(row)

    def get(self, request_id: int) -> ApprovedOutboundRequest | None:
        with self._database.connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM approved_outbound_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def list_summaries(self) -> list[ApprovedOutboundRequestSummary]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT id, case_id, recipient_name, legal_basis,
                       identifier_ids_json, erasure_ground, approved_at
                FROM approved_outbound_requests
                ORDER BY approved_at DESC, id DESC
                """
            ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    @staticmethod
    def _metadata_from_row(row: sqlite3.Row) -> tuple[tuple[int, ...], ErasureGround | None]:
        try:
            raw_ids = json.loads(str(row["identifier_ids_json"]))
            if (
                not isinstance(raw_ids, list)
                or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in raw_ids)
                or len(raw_ids) != len(set(raw_ids))
            ):
                raise ValueError
            erasure_ground = (
                ErasureGround(str(row["erasure_ground"]))
                if row["erasure_ground"] is not None
                else None
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Persisted approved outbound request metadata is malformed") from exc
        return tuple(raw_ids), erasure_ground

    def _summary_from_row(self, row: sqlite3.Row) -> ApprovedOutboundRequestSummary:
        identifier_ids, erasure_ground = self._metadata_from_row(row)
        return ApprovedOutboundRequestSummary(
            id=int(row["id"]),
            case_id=int(row["case_id"]),
            recipient_name=str(row["recipient_name"]),
            legal_basis=str(row["legal_basis"]),
            identifier_ids=identifier_ids,
            erasure_ground=erasure_ground,
            approved_at=str(row["approved_at"]),
        )

    def _from_row(self, row: sqlite3.Row) -> ApprovedOutboundRequest:
        identifier_ids, erasure_ground = self._metadata_from_row(row)
        return ApprovedOutboundRequest(
            id=int(row["id"]),
            case_id=int(row["case_id"]),
            recipient_name=str(row["recipient_name"]),
            recipient_email=self._sensitive_store.decrypt_text(row["recipient_email_enc"]),
            subject=self._sensitive_store.decrypt_text(row["subject_enc"]),
            body=self._sensitive_store.decrypt_text(row["body_enc"]),
            legal_basis=str(row["legal_basis"]),
            identifier_ids=identifier_ids,
            erasure_ground=erasure_ground,
            approved_at=str(row["approved_at"]),
        )

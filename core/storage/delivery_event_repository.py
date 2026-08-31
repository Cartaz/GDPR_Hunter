from __future__ import annotations

from core.domain.delivery import DeliveryEvent, DeliveryEventType
from core.storage.database import Database


class DeliveryEventRepository:
    """Persist append-only mail-client handoff events without message contents."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def record(
        self,
        attempt_id: str,
        approved_request_id: int,
        event_type: DeliveryEventType,
        created_at: str,
    ) -> DeliveryEvent:
        normalized_attempt_id = attempt_id.strip()
        if not normalized_attempt_id:
            raise ValueError("Delivery attempt id cannot be empty")
        if approved_request_id <= 0:
            raise ValueError("Approved request id must be positive")
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO outbound_delivery_events(
                    attempt_id, approved_request_id, event_type, created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    normalized_attempt_id,
                    approved_request_id,
                    event_type.value,
                    created_at,
                ),
            )
            event_id = int(cursor.lastrowid)
        return DeliveryEvent(
            id=event_id,
            attempt_id=normalized_attempt_id,
            approved_request_id=approved_request_id,
            event_type=event_type,
            created_at=created_at,
        )

    def list_events(self) -> list[DeliveryEvent]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT id, attempt_id, approved_request_id, event_type, created_at
                FROM outbound_delivery_events
                ORDER BY id DESC
                """
            ).fetchall()
        return [
            DeliveryEvent(
                id=int(row["id"]),
                attempt_id=str(row["attempt_id"]),
                approved_request_id=int(row["approved_request_id"]),
                event_type=DeliveryEventType(str(row["event_type"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

from __future__ import annotations

from dataclasses import dataclass

from core.application.egress_policy import EgressDecision, OutboundActor, OutboundIntent
from core.storage.database import Database
from core.storage.sensitive_store import SensitiveStore


@dataclass(frozen=True, slots=True)
class OutboundAuditEntry:
    id: int
    operation: str
    destination: str
    data_class: str
    actor: OutboundActor
    approved_by_user: bool
    decision: EgressDecision
    created_at: str


class OutboundAuditRepository:
    """Persist append-only outbound policy decisions with encrypted destinations."""

    def __init__(self, database: Database, sensitive_store: SensitiveStore) -> None:
        self._database = database
        self._sensitive_store = sensitive_store

    def record_decision(self, intent: OutboundIntent, decision: EgressDecision) -> None:
        destination_enc = self._sensitive_store.encrypt_text(intent.destination)
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO outbound_audit(
                    operation, destination_enc, data_class, actor,
                    approved_by_user, decision, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    intent.operation,
                    destination_enc,
                    intent.data_class,
                    intent.actor.value,
                    int(intent.approved_by_user),
                    decision.value,
                ),
            )

    def list_entries(self) -> list[OutboundAuditEntry]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT id, operation, destination_enc, data_class, actor,
                       approved_by_user, decision, created_at
                FROM outbound_audit
                ORDER BY id
                """
            ).fetchall()
        return [
            OutboundAuditEntry(
                id=int(row["id"]),
                operation=str(row["operation"]),
                destination=self._sensitive_store.decrypt_text(row["destination_enc"]),
                data_class=str(row["data_class"]),
                actor=OutboundActor(row["actor"]),
                approved_by_user=bool(row["approved_by_user"]),
                decision=EgressDecision(row["decision"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

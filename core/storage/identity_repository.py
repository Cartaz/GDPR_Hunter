from __future__ import annotations

from datetime import UTC, datetime

from core.domain.identity import Identifier, IdentifierKind, Identity
from core.storage.database import Database
from core.storage.sensitive_store import SensitiveStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class IdentityRepository:
    """Persist the identity aggregate without exposing plaintext PII to SQLite."""

    def __init__(self, database: Database, sensitive_store: SensitiveStore) -> None:
        self._database = database
        self._sensitive_store = sensitive_store

    def get_or_create_identity(self) -> Identity:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, display_name_enc FROM identities ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                now = _utc_now()
                cursor = connection.execute(
                    "INSERT INTO identities(display_name_enc, created_at, updated_at) VALUES(NULL, ?, ?)",
                    (now, now),
                )
                return Identity(id=int(cursor.lastrowid), display_name=None)
            display_name = (
                self._sensitive_store.decrypt_text(row["display_name_enc"])
                if row["display_name_enc"] is not None
                else None
            )
            return Identity(id=int(row["id"]), display_name=display_name)

    def set_display_name(self, identity_id: int, display_name: str | None) -> Identity:
        encrypted = self._sensitive_store.encrypt_text(display_name) if display_name else None
        now = _utc_now()
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE identities SET display_name_enc = ?, updated_at = ? WHERE id = ?",
                (encrypted, now, identity_id),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"Identity {identity_id} does not exist")
        return Identity(id=identity_id, display_name=display_name)

    def add_identifier(
        self,
        identity_id: int,
        kind: IdentifierKind,
        value: str,
        label: str | None = None,
    ) -> Identifier:
        now = _utc_now()
        encrypted_value = self._sensitive_store.encrypt_text(value)
        encrypted_label = self._sensitive_store.encrypt_text(label) if label else None
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO identifiers(identity_id, kind, value_enc, label_enc, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (identity_id, kind.value, encrypted_value, encrypted_label, now, now),
            )
            identifier_id = int(cursor.lastrowid)
        return Identifier(id=identifier_id, kind=kind, value=value, label=label, active=True)

    def list_identifiers(self, identity_id: int) -> list[Identifier]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT id, kind, value_enc, label_enc, active
                FROM identifiers
                WHERE identity_id = ?
                ORDER BY id
                """,
                (identity_id,),
            ).fetchall()

        return [
            Identifier(
                id=int(row["id"]),
                kind=IdentifierKind(row["kind"]),
                value=self._sensitive_store.decrypt_text(row["value_enc"]),
                label=(
                    self._sensitive_store.decrypt_text(row["label_enc"])
                    if row["label_enc"] is not None
                    else None
                ),
                active=bool(row["active"]),
            )
            for row in rows
        ]

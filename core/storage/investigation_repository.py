from __future__ import annotations

import hashlib
import sqlite3

from core.domain.investigation import (
    Artifact,
    ArtifactKind,
    ArtifactRole,
    Claim,
    ClaimProvenance,
    ClaimStatus,
    Evidence,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRelation,
    Investigation,
    InvestigationStatus,
)
from core.storage.database import Database
from core.storage.sensitive_store import SensitiveStore


class InvestigationRepository:
    """Persist investigation aggregates while encrypting sensitive fields."""

    def __init__(self, database: Database, sensitive_store: SensitiveStore) -> None:
        self._database = database
        self._sensitive_store = sensitive_store

    def create_investigation(self, identity_id: int, title: str | None) -> Investigation:
        title_enc = self._sensitive_store.encrypt_text(title) if title else None
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO investigations(identity_id, title_enc, status, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (identity_id, title_enc, InvestigationStatus.OPEN.value),
            )
            investigation_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Created investigation could not be reloaded")
        return self._investigation_from_row(row)

    def get_investigation(self, investigation_id: int) -> Investigation | None:
        with self._database.connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
        return self._investigation_from_row(row) if row is not None else None

    def list_investigations(self) -> list[Investigation]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                "SELECT * FROM investigations ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [self._investigation_from_row(row) for row in rows]

    def transition_investigation(
        self,
        investigation_id: int,
        expected: InvestigationStatus,
        target: InvestigationStatus,
    ) -> Investigation:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE investigations
                SET status = ?, updated_at = datetime('now')
                WHERE id = ? AND status = ?
                """,
                (target.value, investigation_id, expected.value),
            )
            if cursor.rowcount != 1:
                raise LookupError("Investigation changed or no longer exists")
            row = connection.execute(
                "SELECT * FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Updated investigation could not be reloaded")
        return self._investigation_from_row(row)

    def add_artifact_metadata(
        self,
        investigation_id: int,
        storage_key: str,
        kind: ArtifactKind,
        media_type: str,
        payload: bytes,
        role: ArtifactRole,
    ) -> Artifact:
        content_hash_enc = self._sensitive_store.encrypt_text(hashlib.sha256(payload).hexdigest())
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO artifacts(storage_key, kind, media_type, byte_size, content_hash_enc, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (storage_key, kind.value, media_type, len(payload), content_hash_enc),
            )
            artifact_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO investigation_artifacts(investigation_id, artifact_id, role, attached_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (investigation_id, artifact_id, role.value),
            )
            row = connection.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            raise RuntimeError("Created artifact metadata could not be reloaded")
        return self._artifact_from_row(row)

    def list_artifacts(self, investigation_id: int) -> list[Artifact]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT a.*
                FROM artifacts AS a
                JOIN investigation_artifacts AS ia ON ia.artifact_id = a.id
                WHERE ia.investigation_id = ?
                ORDER BY ia.attached_at, a.id
                """,
                (investigation_id,),
            ).fetchall()
        return [self._artifact_from_row(row) for row in rows]

    def add_evidence(
        self,
        investigation_id: int,
        artifact_id: int | None,
        kind: EvidenceKind,
        provenance: EvidenceProvenance,
        value: str | None,
        source_locator: str | None,
    ) -> Evidence:
        value_enc = self._sensitive_store.encrypt_text(value) if value is not None else None
        locator_enc = (
            self._sensitive_store.encrypt_text(source_locator) if source_locator is not None else None
        )
        with self._database.transaction() as connection:
            if artifact_id is not None:
                attached = connection.execute(
                    """
                    SELECT 1 FROM investigation_artifacts
                    WHERE investigation_id = ? AND artifact_id = ?
                    """,
                    (investigation_id, artifact_id),
                ).fetchone()
                if attached is None:
                    raise ValueError("Evidence artifact is not attached to this investigation")
            cursor = connection.execute(
                """
                INSERT INTO evidence(
                    investigation_id, artifact_id, kind, provenance, value_enc, source_locator_enc, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    investigation_id,
                    artifact_id,
                    kind.value,
                    provenance.value,
                    value_enc,
                    locator_enc,
                ),
            )
            evidence_id = int(cursor.lastrowid)
            row = connection.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise RuntimeError("Created evidence could not be reloaded")
        return self._evidence_from_row(row)

    def list_evidence(self, investigation_id: int) -> list[Evidence]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence WHERE investigation_id = ? ORDER BY id",
                (investigation_id,),
            ).fetchall()
        return [self._evidence_from_row(row) for row in rows]

    def create_claim(
        self,
        investigation_id: int,
        statement: str,
        provenance: ClaimProvenance,
        confidence: float | None,
    ) -> Claim:
        statement_enc = self._sensitive_store.encrypt_text(statement)
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO claims(
                    investigation_id, statement_enc, status, provenance, confidence, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    investigation_id,
                    statement_enc,
                    ClaimStatus.HYPOTHESIS.value,
                    provenance.value,
                    confidence,
                ),
            )
            claim_id = int(cursor.lastrowid)
            row = connection.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if row is None:
            raise RuntimeError("Created claim could not be reloaded")
        return self._claim_from_row(row)

    def get_claim(self, claim_id: int) -> Claim | None:
        with self._database.connection_scope() as connection:
            row = connection.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        return self._claim_from_row(row) if row is not None else None

    def list_claims(self, investigation_id: int) -> list[Claim]:
        with self._database.connection_scope() as connection:
            rows = connection.execute(
                "SELECT * FROM claims WHERE investigation_id = ? ORDER BY id",
                (investigation_id,),
            ).fetchall()
        return [self._claim_from_row(row) for row in rows]

    def attach_evidence(
        self,
        claim_id: int,
        evidence_id: int,
        relation: EvidenceRelation,
    ) -> None:
        with self._database.transaction() as connection:
            claim_row = connection.execute(
                "SELECT investigation_id FROM claims WHERE id = ?",
                (claim_id,),
            ).fetchone()
            evidence_row = connection.execute(
                "SELECT investigation_id FROM evidence WHERE id = ?",
                (evidence_id,),
            ).fetchone()
            if claim_row is None or evidence_row is None:
                raise LookupError("Claim or evidence does not exist")
            if int(claim_row["investigation_id"]) != int(evidence_row["investigation_id"]):
                raise ValueError("Claim and evidence must belong to the same investigation")
            connection.execute(
                """
                INSERT INTO claim_evidence(claim_id, evidence_id, relation, attached_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(claim_id, evidence_id) DO UPDATE SET
                    relation = excluded.relation,
                    attached_at = excluded.attached_at
                """,
                (claim_id, evidence_id, relation.value),
            )

    def supporting_evidence_count(self, claim_id: int) -> int:
        with self._database.connection_scope() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM claim_evidence
                WHERE claim_id = ? AND relation = ?
                """,
                (claim_id, EvidenceRelation.SUPPORTS.value),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def update_claim_status(
        self,
        claim_id: int,
        expected: ClaimStatus,
        target: ClaimStatus,
    ) -> Claim:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE claims
                SET status = ?, updated_at = datetime('now')
                WHERE id = ? AND status = ?
                """,
                (target.value, claim_id, expected.value),
            )
            if cursor.rowcount != 1:
                raise LookupError("Claim changed or no longer exists")
            row = connection.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if row is None:
            raise RuntimeError("Updated claim could not be reloaded")
        return self._claim_from_row(row)

    def _investigation_from_row(self, row: sqlite3.Row) -> Investigation:
        title = self._sensitive_store.decrypt_text(row["title_enc"]) if row["title_enc"] else None
        return Investigation(
            id=int(row["id"]),
            identity_id=int(row["identity_id"]),
            title=title,
            status=InvestigationStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _artifact_from_row(row: sqlite3.Row) -> Artifact:
        return Artifact(
            id=int(row["id"]),
            storage_key=str(row["storage_key"]),
            kind=ArtifactKind(str(row["kind"])),
            media_type=str(row["media_type"]),
            byte_size=int(row["byte_size"]),
            created_at=str(row["created_at"]),
        )

    def _evidence_from_row(self, row: sqlite3.Row) -> Evidence:
        value = self._sensitive_store.decrypt_text(row["value_enc"]) if row["value_enc"] else None
        locator = (
            self._sensitive_store.decrypt_text(row["source_locator_enc"])
            if row["source_locator_enc"]
            else None
        )
        return Evidence(
            id=int(row["id"]),
            investigation_id=int(row["investigation_id"]),
            artifact_id=int(row["artifact_id"]) if row["artifact_id"] is not None else None,
            kind=EvidenceKind(str(row["kind"])),
            provenance=EvidenceProvenance(str(row["provenance"])),
            value=value,
            source_locator=locator,
            created_at=str(row["created_at"]),
        )

    def _claim_from_row(self, row: sqlite3.Row) -> Claim:
        return Claim(
            id=int(row["id"]),
            investigation_id=int(row["investigation_id"]),
            statement=self._sensitive_store.decrypt_text(row["statement_enc"]),
            status=ClaimStatus(str(row["status"])),
            provenance=ClaimProvenance(str(row["provenance"])),
            confidence=float(row["confidence"]) if row["confidence"] is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

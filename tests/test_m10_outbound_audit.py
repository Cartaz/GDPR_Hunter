from __future__ import annotations

import sqlite3

import pytest

from core.application.egress_policy import (
    EgressDecision,
    EgressPolicy,
    OutboundActor,
    OutboundIntent,
)
from core.storage.database import Database
from core.storage.outbound_audit_repository import OutboundAuditRepository
from core.storage.sensitive_store import SensitiveStore

TEST_KEY = b"a" * 32


def test_v4_database_migrates_to_append_only_outbound_audit(tmp_path) -> None:
    path = tmp_path / "v4.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_migrated_at TEXT NOT NULL
            );
            INSERT INTO schema_meta VALUES (1, 4, 'old', 'old');
            """
        )
        connection.commit()
    finally:
        connection.close()

    database = Database(path)
    database.initialize()

    with database.connection_scope() as migrated:
        assert migrated.execute("SELECT schema_version FROM schema_meta WHERE id = 1").fetchone()[0] == 5
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'outbound_audit'"
        ).fetchone()[0] == 1


def test_policy_persists_allowed_and_denied_decisions_with_encrypted_destination(tmp_path) -> None:
    database = Database(tmp_path / "audit.sqlite3")
    database.initialize()
    repository = OutboundAuditRepository(database, SensitiveStore(TEST_KEY))
    policy = EgressPolicy(repository)

    denied = OutboundIntent(
        operation="PUBLIC_RESEARCH_FETCH",
        destination="https://example.test/private-token",
        data_class="PUBLIC_OR_OBSERVED_URL",
        approved_by_user=False,
        actor=OutboundActor.MODEL,
    )
    allowed = OutboundIntent(
        operation="PUBLIC_RESEARCH_FETCH",
        destination="https://example.test/privacy",
        data_class="PUBLIC_OR_OBSERVED_URL",
        approved_by_user=True,
    )

    assert policy.evaluate(denied) is EgressDecision.REQUIRE_APPROVAL
    assert policy.evaluate(allowed) is EgressDecision.ALLOW

    entries = repository.list_entries()
    assert [entry.decision for entry in entries] == [
        EgressDecision.REQUIRE_APPROVAL,
        EgressDecision.ALLOW,
    ]
    assert entries[0].actor is OutboundActor.MODEL
    assert entries[1].actor is OutboundActor.USER
    assert b"private-token" not in database.path.read_bytes()
    assert b"https://example.test/privacy" not in database.path.read_bytes()


def test_outbound_audit_rows_cannot_be_updated_or_deleted(tmp_path) -> None:
    database = Database(tmp_path / "audit.sqlite3")
    database.initialize()
    repository = OutboundAuditRepository(database, SensitiveStore(TEST_KEY))
    EgressPolicy(repository).evaluate(
        OutboundIntent("OP", "https://example.test/", "PUBLIC", True)
    )

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute("UPDATE outbound_audit SET operation = 'CHANGED' WHERE id = 1")

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute("DELETE FROM outbound_audit WHERE id = 1")

from __future__ import annotations

import sqlite3

import pytest

from core.storage.database import Database, UnsupportedSchemaVersion


def test_database_enables_foreign_keys(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()

    connection = database.connect()
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_orphan_identifier_is_rejected(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO identifiers(identity_id, kind, value_enc, label_enc, active, created_at, updated_at)
            VALUES (999, 'EMAIL', ?, NULL, 1, 'now', 'now')
            """,
            (b"encrypted",),
        )


def test_v1_database_is_migrated_without_losing_existing_rows(tmp_path):
    database_path = tmp_path / "v1.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_migrated_at TEXT NOT NULL
            );
            CREATE TABLE identities (
                id INTEGER PRIMARY KEY,
                display_name_enc BLOB,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE identifiers (
                id INTEGER PRIMARY KEY,
                identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                value_enc BLOB NOT NULL,
                label_enc BLOB,
                active INTEGER NOT NULL CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO schema_meta VALUES (1, 1, 'old', 'old');
            INSERT INTO identities VALUES (1, NULL, 'old', 'old');
            """
        )
        connection.commit()
    finally:
        connection.close()

    database = Database(database_path)
    database.initialize()

    with database.connection_scope() as migrated:
        assert migrated.execute("SELECT schema_version FROM schema_meta WHERE id = 1").fetchone()[0] == 3
        assert migrated.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == 1
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('targets', 'cases', 'case_events')"
        ).fetchone()[0] == 3


def test_v2_open_case_migrates_to_awaiting_response_without_data_loss(tmp_path):
    database_path = tmp_path / "v2.sqlite3"
    database = Database(database_path)
    database.CURRENT_SCHEMA_VERSION = 2
    database.initialize()

    with database.transaction() as connection:
        connection.execute("INSERT INTO identities VALUES (1, NULL, 'old', 'old')")
        connection.execute(
            "INSERT INTO targets VALUES (1, 'Example Corp', 'example.com', NULL, 'old', 'old')"
        )
        connection.execute(
            "INSERT INTO cases VALUES (1, 1, 1, 'OPEN', 'old', 'old')"
        )
        connection.execute(
            "INSERT INTO case_events VALUES (1, 1, 'STATUS_CHANGED', 'DRAFT', 'OPEN', 'old')"
        )

    Database(database_path).initialize()

    with Database(database_path).connection_scope() as migrated:
        case = migrated.execute(
            "SELECT right_type, status, received_on, extension_notified_on FROM cases WHERE id = 1"
        ).fetchone()
        event = migrated.execute(
            "SELECT from_status, to_status FROM case_events WHERE id = 1"
        ).fetchone()
        assert case is not None
        assert case["right_type"] == "UNSPECIFIED"
        assert case["status"] == "AWAITING_RESPONSE"
        assert case["received_on"] is None
        assert case["extension_notified_on"] is None
        assert event["from_status"] == "DRAFT"
        assert event["to_status"] == "AWAITING_RESPONSE"


def test_newer_database_schema_is_rejected_safely(tmp_path):
    database_path = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE schema_meta (
                id INTEGER PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_migrated_at TEXT NOT NULL
            )
            """
        )
        connection.execute("INSERT INTO schema_meta VALUES (1, 999, 'future', 'future')")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(UnsupportedSchemaVersion):
        Database(database_path).initialize()

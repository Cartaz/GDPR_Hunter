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


def test_current_schema_has_case_deadline_snapshot_columns(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()

    with database.connection_scope() as connection:
        version = connection.execute(
            "SELECT schema_version FROM schema_meta WHERE id = 1"
        ).fetchone()[0]
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(cases)").fetchall()}

    assert version == 6
    assert {
        "deadline_jurisdiction",
        "initial_due_on",
        "extended_due_on",
        "holiday_dates_json",
        "holiday_source",
        "holiday_calendar_complete",
    } <= columns


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
        assert migrated.execute("SELECT schema_version FROM schema_meta WHERE id = 1").fetchone()[0] == 6
        assert migrated.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == 1
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('targets', 'cases', 'case_events')"
        ).fetchone()[0] == 3
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('investigations', 'artifacts', 'evidence', 'claims')"
        ).fetchone()[0] == 4
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'outbound_audit'"
        ).fetchone()[0] == 1
        case_columns = {
            row["name"] for row in migrated.execute("PRAGMA table_info(cases)").fetchall()
        }
        assert "deadline_jurisdiction" in case_columns
        assert "holiday_calendar_complete" in case_columns


def test_v2_open_case_migrates_to_awaiting_response_without_data_loss(tmp_path):
    database_path = tmp_path / "v2.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
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
            CREATE TABLE targets (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT UNIQUE,
                privacy_email TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE cases (
                id INTEGER PRIMARY KEY,
                identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
                target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE RESTRICT,
                status TEXT NOT NULL CHECK (status IN ('DRAFT', 'OPEN', 'COMPLETED', 'CANCELLED')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE case_events (
                id INTEGER PRIMARY KEY,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL CHECK (event_type IN ('CREATED', 'STATUS_CHANGED')),
                from_status TEXT,
                to_status TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TRIGGER case_events_no_update BEFORE UPDATE ON case_events
            BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
            CREATE TRIGGER case_events_no_delete BEFORE DELETE ON case_events
            BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
            INSERT INTO schema_meta VALUES (1, 2, 'old', 'old');
            INSERT INTO identities VALUES (1, NULL, 'old', 'old');
            INSERT INTO targets VALUES (1, 'Example Corp', 'example.com', NULL, 'old', 'old');
            INSERT INTO cases VALUES (1, 1, 1, 'OPEN', 'old', 'old');
            INSERT INTO case_events VALUES (1, 1, 'STATUS_CHANGED', 'DRAFT', 'OPEN', 'old');
            """
        )
        connection.commit()
    finally:
        connection.close()

    database = Database(database_path)
    database.initialize()

    with database.connection_scope() as migrated:
        case = migrated.execute(
            """
            SELECT right_type, status, received_on, extension_notified_on,
                   deadline_jurisdiction, initial_due_on, extended_due_on,
                   holiday_dates_json, holiday_source, holiday_calendar_complete
            FROM cases WHERE id = 1
            """
        ).fetchone()
        event = migrated.execute(
            "SELECT from_status, to_status FROM case_events WHERE id = 1"
        ).fetchone()
        assert migrated.execute("SELECT schema_version FROM schema_meta WHERE id = 1").fetchone()[0] == 6
        assert case is not None
        assert case["right_type"] == "UNSPECIFIED"
        assert case["status"] == "AWAITING_RESPONSE"
        assert case["received_on"] is None
        assert case["extension_notified_on"] is None
        assert case["deadline_jurisdiction"] is None
        assert case["initial_due_on"] is None
        assert case["extended_due_on"] is None
        assert case["holiday_dates_json"] is None
        assert case["holiday_source"] is None
        assert case["holiday_calendar_complete"] is None
        assert event["from_status"] == "DRAFT"
        assert event["to_status"] == "AWAITING_RESPONSE"

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as migrated:
        migrated.execute(
            """
            INSERT INTO case_events(case_id, event_type, from_status, to_status, created_at)
            VALUES (1, 'STATUS_CHANGED', 'INVALID', 'COMPLETED', 'now')
            """
        )


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

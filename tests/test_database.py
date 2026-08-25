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
        connection.execute(
            "INSERT INTO schema_meta VALUES (1, 999, 'future', 'future')"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(UnsupportedSchemaVersion):
        Database(database_path).initialize()

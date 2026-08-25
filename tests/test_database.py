from __future__ import annotations

import sqlite3

import pytest

from core.storage.database import Database


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

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO identifiers(identity_id, kind, value_enc, label_enc, active, created_at, updated_at)
                VALUES (999, 'EMAIL', ?, NULL, 1, 'now', 'now')
                """,
                (b"encrypted",),
            )

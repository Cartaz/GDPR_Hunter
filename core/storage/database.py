from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class DatabaseSchemaError(RuntimeError):
    pass


class UnsupportedSchemaVersion(DatabaseSchemaError):
    pass


class Database:
    """Own SQLite connection setup, schema compatibility, and transactions."""

    CURRENT_SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            existing_version = self._existing_schema_version(connection)
            if existing_version is not None and existing_version != self.CURRENT_SCHEMA_VERSION:
                raise UnsupportedSchemaVersion(
                    f"Database schema version {existing_version} is not supported by this application version"
                )

            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    schema_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_migrated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS identities (
                    id INTEGER PRIMARY KEY,
                    display_name_enc BLOB,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS identifiers (
                    id INTEGER PRIMARY KEY,
                    identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    value_enc BLOB NOT NULL,
                    label_enc BLOB,
                    active INTEGER NOT NULL CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_identifiers_identity_id
                    ON identifiers(identity_id);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_meta(id, schema_version, created_at, last_migrated_at)
                VALUES (1, ?, datetime('now'), datetime('now'))
                """,
                (self.CURRENT_SCHEMA_VERSION,),
            )

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        if enabled != 1:
            connection.close()
            raise RuntimeError("SQLite foreign key enforcement could not be enabled")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _existing_schema_version(connection: sqlite3.Connection) -> int | None:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
        ).fetchone()
        if table_exists is None:
            return None

        try:
            row = connection.execute(
                "SELECT schema_version FROM schema_meta WHERE id = 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseSchemaError("Database schema metadata is malformed") from exc

        if row is None or isinstance(row["schema_version"], bool) or not isinstance(row["schema_version"], int):
            raise DatabaseSchemaError("Database schema metadata is missing or invalid")
        return int(row["schema_version"])

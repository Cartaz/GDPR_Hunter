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
    """Own SQLite connection setup, lifecycle, schema compatibility, migrations, and transactions."""

    CURRENT_SCHEMA_VERSION = 6

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection_scope() as connection:
            existing_version = self._existing_schema_version(connection)
            if existing_version is None:
                self._create_current_schema(connection)
                return
            if existing_version > self.CURRENT_SCHEMA_VERSION:
                raise UnsupportedSchemaVersion(
                    f"Database schema version {existing_version} is newer than supported version "
                    f"{self.CURRENT_SCHEMA_VERSION}"
                )
            if existing_version < 1:
                raise UnsupportedSchemaVersion(f"Database schema version {existing_version} is not supported")

            version = existing_version
            while version < self.CURRENT_SCHEMA_VERSION:
                version = self._migrate(connection, version)

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
    def connection_scope(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection_scope() as connection, connection:
            yield connection

    def _create_current_schema(self, connection: sqlite3.Connection) -> None:
        with connection:
            connection.execute(
                """
                CREATE TABLE schema_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    schema_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_migrated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE identities (
                    id INTEGER PRIMARY KEY,
                    display_name_enc BLOB,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE identifiers (
                    id INTEGER PRIMARY KEY,
                    identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    value_enc BLOB NOT NULL,
                    label_enc BLOB,
                    active INTEGER NOT NULL CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX idx_identifiers_identity_id ON identifiers(identity_id)")
            self._create_targets_schema(connection)
            self._create_case_schema_v6(connection)
            self._create_investigation_schema_v4(connection)
            self._create_outbound_audit_schema_v5(connection)
            connection.execute(
                """
                INSERT INTO schema_meta(id, schema_version, created_at, last_migrated_at)
                VALUES (1, ?, datetime('now'), datetime('now'))
                """,
                (self.CURRENT_SCHEMA_VERSION,),
            )

    def _migrate(self, connection: sqlite3.Connection, from_version: int) -> int:
        if from_version == 1:
            with connection:
                self._create_m2_schema(connection)
                self._set_schema_version(connection, expected=1, target=2)
            return 2
        if from_version == 2:
            self._migrate_v2_to_v3(connection)
            return 3
        if from_version == 3:
            with connection:
                self._create_investigation_schema_v4(connection)
                self._set_schema_version(connection, expected=3, target=4)
            return 4
        if from_version == 4:
            with connection:
                self._create_outbound_audit_schema_v5(connection)
                self._set_schema_version(connection, expected=4, target=5)
            return 5
        if from_version == 5:
            self._migrate_v5_to_v6(connection)
            return 6
        raise UnsupportedSchemaVersion(f"No migration path from database schema version {from_version}")

    @staticmethod
    def _set_schema_version(connection: sqlite3.Connection, expected: int, target: int) -> None:
        cursor = connection.execute(
            """
            UPDATE schema_meta
            SET schema_version = ?, last_migrated_at = datetime('now')
            WHERE id = 1 AND schema_version = ?
            """,
            (target, expected),
        )
        if cursor.rowcount != 1:
            raise DatabaseSchemaError("Database schema version changed during migration")

    @staticmethod
    def _create_targets_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE targets (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT UNIQUE,
                privacy_email TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    def _create_m2_schema(self, connection: sqlite3.Connection) -> None:
        self._create_targets_schema(connection)
        statements = (
            """
            CREATE TABLE cases (
                id INTEGER PRIMARY KEY,
                identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
                target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE RESTRICT,
                status TEXT NOT NULL CHECK (status IN ('DRAFT', 'OPEN', 'COMPLETED', 'CANCELLED')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_cases_identity_id ON cases(identity_id)",
            "CREATE INDEX idx_cases_target_id ON cases(target_id)",
            "CREATE INDEX idx_cases_status ON cases(status)",
            """
            CREATE TABLE case_events (
                id INTEGER PRIMARY KEY,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL CHECK (event_type IN ('CREATED', 'STATUS_CHANGED')),
                from_status TEXT CHECK (from_status IS NULL OR from_status IN ('DRAFT', 'OPEN', 'COMPLETED', 'CANCELLED')),
                to_status TEXT CHECK (to_status IS NULL OR to_status IN ('DRAFT', 'OPEN', 'COMPLETED', 'CANCELLED')),
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_case_events_case_id ON case_events(case_id, id)",
            """
            CREATE TRIGGER case_events_no_update
            BEFORE UPDATE ON case_events
            BEGIN
                SELECT RAISE(ABORT, 'case events are append-only');
            END
            """,
            """
            CREATE TRIGGER case_events_no_delete
            BEFORE DELETE ON case_events
            BEGIN
                SELECT RAISE(ABORT, 'case events are append-only');
            END
            """,
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _create_case_schema_v3(connection: sqlite3.Connection) -> None:
        Database._create_case_schema(connection, include_deadline_snapshot=False)

    @staticmethod
    def _create_case_schema_v6(connection: sqlite3.Connection) -> None:
        Database._create_case_schema(connection, include_deadline_snapshot=True)

    @staticmethod
    def _create_case_schema(
        connection: sqlite3.Connection,
        *,
        include_deadline_snapshot: bool,
    ) -> None:
        deadline_columns = """
                deadline_jurisdiction TEXT,
                initial_due_on TEXT,
                extended_due_on TEXT,
                holiday_dates_json TEXT,
                holiday_source TEXT,
                holiday_calendar_complete INTEGER CHECK (
                    holiday_calendar_complete IS NULL OR holiday_calendar_complete IN (0, 1)
                ),
        """ if include_deadline_snapshot else ""
        statements = (
            f"""
            CREATE TABLE cases (
                id INTEGER PRIMARY KEY,
                identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
                target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE RESTRICT,
                right_type TEXT NOT NULL CHECK (
                    right_type IN ('UNSPECIFIED', 'ACCESS_PROVENANCE', 'ERASURE', 'DIRECT_MARKETING_OBJECTION')
                ),
                status TEXT NOT NULL CHECK (
                    status IN ('DRAFT', 'AWAITING_RESPONSE', 'COMPLETED', 'CANCELLED')
                ),
                received_on TEXT,
                extension_notified_on TEXT,
                {deadline_columns}
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_cases_identity_id ON cases(identity_id)",
            "CREATE INDEX idx_cases_target_id ON cases(target_id)",
            "CREATE INDEX idx_cases_status ON cases(status)",
            "CREATE INDEX idx_cases_right_type ON cases(right_type)",
            """
            CREATE TABLE case_events (
                id INTEGER PRIMARY KEY,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL CHECK (
                    event_type IN ('CREATED', 'STATUS_CHANGED', 'REQUEST_SUBMITTED', 'EXTENSION_RECORDED')
                ),
                from_status TEXT CHECK (
                    from_status IS NULL OR from_status IN ('DRAFT', 'AWAITING_RESPONSE', 'COMPLETED', 'CANCELLED')
                ),
                to_status TEXT CHECK (
                    to_status IS NULL OR to_status IN ('DRAFT', 'AWAITING_RESPONSE', 'COMPLETED', 'CANCELLED')
                ),
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_case_events_case_id ON case_events(case_id, id)",
        )
        for statement in statements:
            connection.execute(statement)
        Database._create_case_event_triggers(connection)

    @staticmethod
    def _create_case_event_triggers(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TRIGGER case_events_no_update
            BEFORE UPDATE ON case_events
            BEGIN
                SELECT RAISE(ABORT, 'case events are append-only');
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER case_events_no_delete
            BEFORE DELETE ON case_events
            BEGIN
                SELECT RAISE(ABORT, 'case events are append-only');
            END
            """
        )

    @staticmethod
    def _create_investigation_schema_v4(connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE investigations (
                id INTEGER PRIMARY KEY,
                identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
                title_enc BLOB,
                status TEXT NOT NULL CHECK (
                    status IN ('OPEN', 'ANALYSING', 'ACTIONABLE', 'CONCLUDED', 'INCONCLUSIVE', 'ARCHIVED')
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_investigations_identity_id ON investigations(identity_id)",
            "CREATE INDEX idx_investigations_status ON investigations(status)",
            """
            CREATE TABLE artifacts (
                id INTEGER PRIMARY KEY,
                storage_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL CHECK (kind IN ('SMS', 'EMAIL', 'URL', 'TEXT', 'COMPANY_RESPONSE')),
                media_type TEXT NOT NULL,
                byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                content_hash_enc BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE investigation_artifacts (
                investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE RESTRICT,
                role TEXT NOT NULL CHECK (role IN ('TRIGGER', 'SUPPORTING', 'RESPONSE', 'REFERENCE')),
                attached_at TEXT NOT NULL,
                PRIMARY KEY (investigation_id, artifact_id)
            )
            """,
            "CREATE INDEX idx_investigation_artifacts_artifact_id ON investigation_artifacts(artifact_id)",
            """
            CREATE TABLE evidence (
                id INTEGER PRIMARY KEY,
                investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                artifact_id INTEGER REFERENCES artifacts(id) ON DELETE SET NULL,
                kind TEXT NOT NULL CHECK (kind IN ('EXTRACTED_FIELD', 'OBSERVATION', 'SOURCE_STATEMENT')),
                provenance TEXT NOT NULL CHECK (
                    provenance IN ('USER_STATEMENT', 'DETERMINISTIC_ANALYSIS', 'REMOTE_DOCUMENT', 'COMPANY_RESPONSE', 'AUTHORITATIVE_SOURCE')
                ),
                value_enc BLOB,
                source_locator_enc BLOB,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_evidence_investigation_id ON evidence(investigation_id)",
            "CREATE INDEX idx_evidence_artifact_id ON evidence(artifact_id)",
            """
            CREATE TABLE claims (
                id INTEGER PRIMARY KEY,
                investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                statement_enc BLOB NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('HYPOTHESIS', 'SUPPORTED', 'CORROBORATED', 'VERIFIED', 'CONTRADICTED', 'REJECTED')
                ),
                provenance TEXT NOT NULL CHECK (provenance IN ('USER', 'DETERMINISTIC', 'MODEL_INFERENCE')),
                confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_claims_investigation_id ON claims(investigation_id)",
            "CREATE INDEX idx_claims_status ON claims(status)",
            """
            CREATE TABLE claim_evidence (
                claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
                relation TEXT NOT NULL CHECK (relation IN ('SUPPORTS', 'CONTRADICTS')),
                attached_at TEXT NOT NULL,
                PRIMARY KEY (claim_id, evidence_id)
            )
            """,
            "CREATE INDEX idx_claim_evidence_evidence_id ON claim_evidence(evidence_id)",
            """
            CREATE TRIGGER artifacts_no_update
            BEFORE UPDATE ON artifacts
            BEGIN
                SELECT RAISE(ABORT, 'artifact metadata is immutable');
            END
            """,
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _create_outbound_audit_schema_v5(connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE outbound_audit (
                id INTEGER PRIMARY KEY,
                operation TEXT NOT NULL,
                destination_enc BLOB NOT NULL,
                data_class TEXT NOT NULL,
                actor TEXT NOT NULL CHECK (actor IN ('USER', 'MODEL')),
                approved_by_user INTEGER NOT NULL CHECK (approved_by_user IN (0, 1)),
                decision TEXT NOT NULL CHECK (decision IN ('ALLOW', 'REQUIRE_APPROVAL')),
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_outbound_audit_created_at ON outbound_audit(created_at, id)",
            """
            CREATE TRIGGER outbound_audit_no_update
            BEFORE UPDATE ON outbound_audit
            BEGIN
                SELECT RAISE(ABORT, 'outbound audit is append-only');
            END
            """,
            """
            CREATE TRIGGER outbound_audit_no_delete
            BEFORE DELETE ON outbound_audit
            BEGIN
                SELECT RAISE(ABORT, 'outbound audit is append-only');
            END
            """,
        )
        for statement in statements:
            connection.execute(statement)

    def _migrate_v2_to_v3(self, connection: sqlite3.Connection) -> None:
        with connection:
            connection.execute(
                """
                CREATE TABLE cases_v3 (
                    id INTEGER PRIMARY KEY,
                    identity_id INTEGER NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
                    target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE RESTRICT,
                    right_type TEXT NOT NULL CHECK (
                        right_type IN ('UNSPECIFIED', 'ACCESS_PROVENANCE', 'ERASURE', 'DIRECT_MARKETING_OBJECTION')
                    ),
                    status TEXT NOT NULL CHECK (
                        status IN ('DRAFT', 'AWAITING_RESPONSE', 'COMPLETED', 'CANCELLED')
                    ),
                    received_on TEXT,
                    extension_notified_on TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE case_events_v3 (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER NOT NULL REFERENCES cases_v3(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN ('CREATED', 'STATUS_CHANGED', 'REQUEST_SUBMITTED', 'EXTENSION_RECORDED')
                    ),
                    from_status TEXT CHECK (
                        from_status IS NULL OR from_status IN ('DRAFT', 'AWAITING_RESPONSE', 'COMPLETED', 'CANCELLED')
                    ),
                    to_status TEXT CHECK (
                        to_status IS NULL OR to_status IN ('DRAFT', 'AWAITING_RESPONSE', 'COMPLETED', 'CANCELLED')
                    ),
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO cases_v3(
                    id, identity_id, target_id, right_type, status,
                    received_on, extension_notified_on, created_at, updated_at
                )
                SELECT
                    id, identity_id, target_id, 'UNSPECIFIED',
                    CASE status WHEN 'OPEN' THEN 'AWAITING_RESPONSE' ELSE status END,
                    NULL, NULL, created_at, updated_at
                FROM cases
                """
            )
            connection.execute(
                """
                INSERT INTO case_events_v3(id, case_id, event_type, from_status, to_status, created_at)
                SELECT
                    id,
                    case_id,
                    event_type,
                    CASE from_status WHEN 'OPEN' THEN 'AWAITING_RESPONSE' ELSE from_status END,
                    CASE to_status WHEN 'OPEN' THEN 'AWAITING_RESPONSE' ELSE to_status END,
                    created_at
                FROM case_events
                """
            )
            connection.execute("DROP TRIGGER case_events_no_update")
            connection.execute("DROP TRIGGER case_events_no_delete")
            connection.execute("DROP TABLE case_events")
            connection.execute("DROP TABLE cases")
            connection.execute("ALTER TABLE cases_v3 RENAME TO cases")
            connection.execute("ALTER TABLE case_events_v3 RENAME TO case_events")
            connection.execute("CREATE INDEX idx_cases_identity_id ON cases(identity_id)")
            connection.execute("CREATE INDEX idx_cases_target_id ON cases(target_id)")
            connection.execute("CREATE INDEX idx_cases_status ON cases(status)")
            connection.execute("CREATE INDEX idx_cases_right_type ON cases(right_type)")
            connection.execute("CREATE INDEX idx_case_events_case_id ON case_events(case_id, id)")
            self._create_case_event_triggers(connection)
            self._set_schema_version(connection, expected=2, target=3)

    def _migrate_v5_to_v6(self, connection: sqlite3.Connection) -> None:
        with connection:
            connection.execute("ALTER TABLE cases ADD COLUMN deadline_jurisdiction TEXT")
            connection.execute("ALTER TABLE cases ADD COLUMN initial_due_on TEXT")
            connection.execute("ALTER TABLE cases ADD COLUMN extended_due_on TEXT")
            connection.execute("ALTER TABLE cases ADD COLUMN holiday_dates_json TEXT")
            connection.execute("ALTER TABLE cases ADD COLUMN holiday_source TEXT")
            connection.execute(
                """
                ALTER TABLE cases ADD COLUMN holiday_calendar_complete INTEGER
                CHECK (holiday_calendar_complete IS NULL OR holiday_calendar_complete IN (0, 1))
                """
            )
            self._set_schema_version(connection, expected=5, target=6)

    @staticmethod
    def _existing_schema_version(connection: sqlite3.Connection) -> int | None:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
        ).fetchone()
        if table_exists is None:
            return None

        try:
            row = connection.execute("SELECT schema_version FROM schema_meta WHERE id = 1").fetchone()
        except sqlite3.Error as exc:
            raise DatabaseSchemaError("Database schema metadata is malformed") from exc

        if row is None or isinstance(row["schema_version"], bool) or not isinstance(row["schema_version"], int):
            raise DatabaseSchemaError("Database schema metadata is missing or invalid")
        return int(row["schema_version"])

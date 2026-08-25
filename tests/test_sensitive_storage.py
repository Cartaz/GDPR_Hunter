from __future__ import annotations

import sqlite3

from core.domain.identity import IdentifierKind
from core.storage.artifact_store import ArtifactStore
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.sensitive_store import SensitiveStore

TEST_KEY = b"k" * 32


def test_sensitive_store_round_trip_and_no_plaintext():
    store = SensitiveStore(TEST_KEY)
    plaintext = "sensitive@example.com"

    encrypted = store.encrypt_text(plaintext)

    assert plaintext.encode("utf-8") not in encrypted
    assert store.decrypt_text(encrypted) == plaintext


def test_artifact_store_writes_only_encrypted_bytes(tmp_path):
    sensitive_store = SensitiveStore(TEST_KEY)
    artifact_store = ArtifactStore(tmp_path / "artifacts", sensitive_store)
    payload = b"SMS body with private phone +39 333 123 4567"

    storage_key = artifact_store.store(payload)
    stored_files = list((tmp_path / "artifacts").rglob("*.dat"))

    assert len(stored_files) == 1
    assert payload not in stored_files[0].read_bytes()
    assert artifact_store.read(storage_key) == payload

    artifact_store.delete(storage_key)
    assert not stored_files[0].exists()


def test_identity_repository_never_persists_identifier_plaintext(tmp_path):
    database_path = tmp_path / "gdpr_hunter.sqlite3"
    database = Database(database_path)
    database.initialize()
    repository = IdentityRepository(database, SensitiveStore(TEST_KEY))
    identity = repository.get_or_create_identity()
    assert identity.id is not None

    email = "private-person@example.com"
    repository.add_identifier(identity.id, IdentifierKind.EMAIL, email)

    raw_database = database_path.read_bytes()
    assert email.encode("utf-8") not in raw_database

    connection = sqlite3.connect(database_path)
    try:
        stored = connection.execute("SELECT value_enc FROM identifiers").fetchone()[0]
    finally:
        connection.close()
    assert email.encode("utf-8") not in stored

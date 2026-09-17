from __future__ import annotations

import hashlib
import io
import sqlite3
import stat
import zipfile
from pathlib import Path

import pytest

from core.application.archive_lock import ArchiveBusy, ArchiveLock
from core.application.paths import AppPaths
from core.storage import archive_recovery as recovery
from core.storage.archive_recovery import ArchiveError, create_backup, restore_backup
from core.storage.artifact_store import ArtifactStore
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.secret_store import SecretStore
from core.storage.sensitive_store import SensitiveStore

KEY = b"r" * 32
PASSWORD = "a very long private recovery password"


@pytest.fixture
def credential_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    credentials: dict[str, str] = {}
    monkeypatch.setattr(
        "core.storage.secret_store.keyring.get_password",
        lambda service, name: credentials.get(f"{service}/{name}"),
    )
    monkeypatch.setattr(
        "core.storage.secret_store.keyring.set_password",
        lambda service, name, value: credentials.__setitem__(f"{service}/{name}", value),
    )
    return credentials


def _paths(tmp_path: Path, name: str = "source") -> AppPaths:
    return AppPaths(data_dir=tmp_path / name, config_dir=tmp_path / "settings")


def _seed(tmp_path: Path, *, artifact: bool = True) -> tuple[AppPaths, str | None]:
    paths = _paths(tmp_path)
    database = Database(paths.database_path)
    database.initialize()
    repository = IdentityRepository(database, SensitiveStore(KEY))
    identity = repository.get_or_create_identity()
    assert identity.id is not None
    repository.set_display_name(identity.id, "Extremely private name")
    if not artifact:
        return paths, None
    payload = b"Private evidence from a controller"
    storage_key = ArtifactStore(paths.artifacts_dir, SensitiveStore(KEY)).store(payload)
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO artifacts(storage_key, kind, media_type, byte_size, content_hash_enc, created_at)
               VALUES (?, 'EMAIL', 'text/plain', ?, ?, datetime('now'))""",
            (storage_key, len(payload), SensitiveStore(KEY).encrypt_text(hashlib.sha256(payload).hexdigest())),
        )
    return paths, storage_key


def _backup(tmp_path: Path, credential_store: dict[str, str]) -> tuple[AppPaths, Path, str | None]:
    paths, key = _seed(tmp_path)
    SecretStore().store_master_key_if_absent(KEY)
    package = tmp_path / "archive.ghbackup"
    create_backup(paths, package, PASSWORD)
    return paths, package, key


def test_roundtrip_encrypts_entire_package_and_restores_artifact(tmp_path, credential_store):
    paths, package, storage_key = _backup(tmp_path, credential_store)
    raw = package.read_bytes()
    assert b"Extremely private name" not in raw
    assert b"Private evidence from a controller" not in raw
    assert KEY not in raw
    assert b"SQLite format 3" not in raw
    assert storage_key.encode() not in raw
    target = _paths(tmp_path, "restored")
    credential_store.clear()
    restore_backup(target, package, PASSWORD)
    with Database(target.database_path).connection_scope() as connection:
        encrypted = connection.execute("SELECT display_name_enc FROM identities").fetchone()[0]
    assert SensitiveStore(KEY).decrypt_text(encrypted) == "Extremely private name"
    assert ArtifactStore(target.artifacts_dir, SensitiveStore(KEY)).read(storage_key) == (
        b"Private evidence from a controller"
    )
    assert SecretStore().get_existing_master_key() == KEY
    assert paths.database_path.exists()


def test_wrong_passphrase_does_not_install_key_or_data(tmp_path, credential_store):
    _, package, _ = _backup(tmp_path, credential_store)
    credential_store.clear()
    target = _paths(tmp_path, "restored")
    with pytest.raises(ArchiveError, match="passphrase or modified"):
        restore_backup(target, package, "not the same recovery password")
    assert not target.data_dir.exists()
    assert credential_store == {}


def test_modified_or_truncated_package_fails_closed(tmp_path, credential_store):
    _, package, _ = _backup(tmp_path, credential_store)
    credential_store.clear()
    raw = bytearray(package.read_bytes())
    raw[-20] ^= 1
    package.write_bytes(raw)
    with pytest.raises(ArchiveError):
        restore_backup(_paths(tmp_path, "restored"), package, PASSWORD)
    package.write_bytes(bytes(raw[:25]))
    with pytest.raises(ArchiveError):
        restore_backup(_paths(tmp_path, "restored"), package, PASSWORD)
    assert credential_store == {}


def test_backup_requires_original_master_key(tmp_path, credential_store):
    paths, _ = _seed(tmp_path)
    with pytest.raises(ArchiveError, match="key is missing"):
        create_backup(paths, tmp_path / "missing.ghbackup", PASSWORD)
    assert not (tmp_path / "missing.ghbackup").exists()


def test_backup_rejects_present_but_wrong_master_key(tmp_path, credential_store):
    paths, _ = _seed(tmp_path)
    SecretStore().store_master_key_if_absent(b"w" * 32)
    with pytest.raises(ArchiveError, match="could not be verified"):
        create_backup(paths, tmp_path / "bad.ghbackup", PASSWORD)


def test_restore_rejects_different_existing_key_without_data_loss(tmp_path, credential_store):
    paths, package, _ = _backup(tmp_path, credential_store)
    credential_store.clear()
    SecretStore().store_master_key_if_absent(b"x" * 32)
    with pytest.raises(ArchiveError, match="different archive key"):
        restore_backup(_paths(tmp_path, "restored"), package, PASSWORD)
    assert SecretStore().get_existing_master_key() == b"x" * 32
    assert paths.database_path.exists()
    assert not _paths(tmp_path, "restored").data_dir.exists()


def test_existing_destination_and_output_cannot_be_overwritten(tmp_path, credential_store):
    _, package, _ = _backup(tmp_path, credential_store)
    with pytest.raises(ArchiveError, match="already exists"):
        create_backup(_paths(tmp_path), package, PASSWORD)
    target = _paths(tmp_path, "restored")
    target.data_dir.mkdir()
    (target.data_dir / "important.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ArchiveError, match="overwrite"):
        restore_backup(target, package, PASSWORD)
    assert (target.data_dir / "important.txt").read_text() == "keep"


def test_unreferenced_or_missing_artifacts_block_backup(tmp_path, credential_store):
    paths, key = _seed(tmp_path)
    SecretStore().store_master_key_if_absent(KEY)
    assert key is not None
    file = paths.artifacts_dir / key[:2] / f"{key[2:]}.dat"
    file.unlink()
    with pytest.raises(ArchiveError, match="missing"):
        create_backup(paths, tmp_path / "missing.ghbackup", PASSWORD)


def test_changed_artifact_is_detected(tmp_path, credential_store):
    paths, key = _seed(tmp_path)
    SecretStore().store_master_key_if_absent(KEY)
    assert key is not None
    file = paths.artifacts_dir / key[:2] / f"{key[2:]}.dat"
    file.write_bytes(SensitiveStore(KEY).encrypt_bytes(b"modified evidence"))
    with pytest.raises(ArchiveError, match="provenance"):
        create_backup(paths, tmp_path / "changed.ghbackup", PASSWORD)


def test_symlinked_artifact_and_unexpected_files_are_refused(tmp_path, credential_store):
    paths, key = _seed(tmp_path)
    SecretStore().store_master_key_if_absent(KEY)
    assert key is not None
    file = paths.artifacts_dir / key[:2] / f"{key[2:]}.dat"
    original = file.read_bytes()
    file.unlink()
    alternate = tmp_path / "alternative.dat"
    alternate.write_bytes(original)
    file.symlink_to(alternate)
    with pytest.raises(ArchiveError, match="unsafe artifact"):
        create_backup(paths, tmp_path / "symlink.ghbackup", PASSWORD)
    file.unlink()
    file.write_bytes(original)
    (paths.data_dir / "untracked.bin").write_bytes(b"not a backup candidate")
    with pytest.raises(ArchiveError, match="Unexpected files"):
        create_backup(paths, tmp_path / "unexpected.ghbackup", PASSWORD)


def test_lock_refuses_concurrent_backup(tmp_path, credential_store):
    paths, _ = _seed(tmp_path)
    SecretStore().store_master_key_if_absent(KEY)
    with ArchiveLock(paths.data_dir), pytest.raises(ArchiveBusy):
        create_backup(paths, tmp_path / "busy.ghbackup", PASSWORD)


def test_failed_restore_is_retryable_without_erasing_matching_key(tmp_path, credential_store, monkeypatch):
    _, package, _ = _backup(tmp_path, credential_store)
    credential_store.clear()
    target = _paths(tmp_path, "restored")
    original_install = recovery._install_directory_no_replace

    def interrupted_install(staging, destination):
        raise OSError("simulated interruption")

    monkeypatch.setattr(recovery, "_install_directory_no_replace", interrupted_install)
    with pytest.raises(OSError, match="simulated interruption"):
        restore_backup(target, package, PASSWORD)
    assert not target.data_dir.exists()
    assert SecretStore().get_existing_master_key() == KEY
    monkeypatch.setattr(recovery, "_install_directory_no_replace", original_install)
    restore_backup(target, package, PASSWORD)
    assert target.database_path.exists()


def test_raced_restore_destination_cannot_be_replaced(tmp_path, credential_store, monkeypatch):
    _, package, _ = _backup(tmp_path, credential_store)
    credential_store.clear()
    target = _paths(tmp_path, "restored")
    original_install = recovery._install_directory_no_replace

    def raced_install(staging, destination):
        destination.mkdir()
        (destination / "important.txt").write_text("keep", encoding="utf-8")
        original_install(staging, destination)

    monkeypatch.setattr(recovery, "_install_directory_no_replace", raced_install)
    with pytest.raises(ArchiveError, match="no data was overwritten"):
        restore_backup(target, package, PASSWORD)
    assert (target.data_dir / "important.txt").read_text(encoding="utf-8") == "keep"
    assert not target.database_path.exists()
    assert not list(tmp_path.glob(".gdpr-restore-*"))


def test_empty_legacy_archive_does_not_blindly_accept_any_key(tmp_path, credential_store):
    paths = _paths(tmp_path)
    Database(paths.database_path).initialize()
    SecretStore().store_master_key_if_absent(KEY)
    with pytest.raises(ArchiveError, match="no ciphertext"):
        create_backup(paths, tmp_path / "unverified.ghbackup", PASSWORD)


def test_sqlite_wal_rows_are_included_in_consistent_snapshot(tmp_path, credential_store):
    paths, _ = _seed(tmp_path, artifact=False)
    SecretStore().store_master_key_if_absent(KEY)
    writer = sqlite3.connect(paths.database_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(
            "INSERT INTO identifiers(identity_id, kind, value_enc, active, created_at, updated_at) "
            "VALUES (1, 'EMAIL', ?, 1, datetime('now'), datetime('now'))",
            (SensitiveStore(KEY).encrypt_text("wal-only@example.com"),),
        )
        writer.commit()
        package = tmp_path / "wal.ghbackup"
        create_backup(paths, package, PASSWORD)
    finally:
        writer.close()
    credential_store.clear()
    target = _paths(tmp_path, "restored")
    restore_backup(target, package, PASSWORD)
    with Database(target.database_path).connection_scope() as connection:
        row = connection.execute("SELECT value_enc FROM identifiers").fetchone()
    assert SensitiveStore(KEY).decrypt_text(row[0]) == "wal-only@example.com"


def _forged_internal_zip(members: list[tuple[str, bytes, int | None]]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, value, file_type in members:
            info = zipfile.ZipInfo(name)
            if file_type is not None:
                info.external_attr = (file_type | 0o600) << 16
            archive.writestr(info, value)
    return stream.getvalue()


@pytest.mark.parametrize("unsafe_name", ["../escape", "artifacts/../escape", "/absolute/path"])
def test_internal_zip_rejects_unsafe_member_paths(unsafe_name):
    payload = _forged_internal_zip(
        [(recovery.MANIFEST_MEMBER, b"{}", None), (recovery.KEY_MEMBER, KEY, None),
         (recovery.DB_MEMBER, b"sqlite", None), (unsafe_name, b"bad", None)]
    )
    with pytest.raises(ArchiveError, match="unsafe archive member"):
        recovery._read_plaintext(payload)


def test_internal_zip_rejects_symlink_member():
    name = "artifacts/aa/" + "b" * 30 + ".dat"
    payload = _forged_internal_zip(
        [(recovery.MANIFEST_MEMBER, b"{}", None), (recovery.KEY_MEMBER, KEY, None),
         (recovery.DB_MEMBER, b"sqlite", None), (name, b"bad", stat.S_IFLNK)]
    )
    with pytest.raises(ArchiveError, match="unsafe archive member"):
        recovery._read_plaintext(payload)


def test_internal_zip_total_member_sizes_are_bounded(monkeypatch):
    monkeypatch.setattr(recovery, "MAX_BYTES", 8192)
    name = "artifacts/aa/" + "b" * 30 + ".dat"
    payload = _forged_internal_zip(
        [(recovery.MANIFEST_MEMBER, b"{}", None), (recovery.KEY_MEMBER, KEY, None),
         (recovery.DB_MEMBER, b"a" * 5000, None), (name, b"b" * 5000, None)]
    )
    with pytest.raises(ArchiveError, match="oversized"):
        recovery._read_plaintext(payload)

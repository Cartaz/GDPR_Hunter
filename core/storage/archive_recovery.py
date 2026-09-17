"""Offline, whole-envelope encrypted backup and empty-destination restore.

The bounded in-memory format refuses large archives instead of writing a
plaintext database or master key to a temporary recovery file.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from core.application.archive_lock import ArchiveLock
from core.application.paths import AppPaths
from core.storage.database import Database
from core.storage.secret_store import SecretStore
from core.storage.sensitive_store import SensitiveStore


class ArchiveError(RuntimeError):
    """A recovery operation failed without exposing archive contents."""


MAGIC = b"GDPR-HUNTER-RECOVERY-1\n"
SALT_BYTES = 16
NONCE_BYTES = 12
MAX_BYTES = 128 * 1024 * 1024
MAX_ARTIFACTS = 2000
KEY_MEMBER = "master-key.bin"
DB_MEMBER = "database.sqlite3"
MANIFEST_MEMBER = "manifest.json"
_ARTIFACT_NAME = re.compile(r"artifacts/([0-9a-f]{2})/([0-9a-f]{30})\.dat\Z")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _derive(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < 16:
        raise ArchiveError("Recovery passphrase must contain at least 16 characters")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def _safe_artifact_name(name: str) -> bool:
    return _ARTIFACT_NAME.fullmatch(name) is not None


def _source_artifacts(paths: AppPaths) -> dict[str, bytes]:
    root = paths.artifacts_dir
    if not root.exists():
        return {}
    if root.is_symlink() or not root.is_dir():
        raise ArchiveError("Unsafe artifact directory")
    found: dict[str, bytes] = {}
    total = 0
    for folder in sorted(root.iterdir()):
        if folder.is_symlink() or not folder.is_dir() or not re.fullmatch(r"[0-9a-f]{2}", folder.name):
            raise ArchiveError("Unexpected or unsafe artifact directory entry")
        for file in sorted(folder.iterdir()):
            name = f"artifacts/{folder.name}/{file.name}"
            if file.is_symlink() or not file.is_file() or not _safe_artifact_name(name):
                raise ArchiveError("Unexpected or unsafe artifact entry")
            if len(found) >= MAX_ARTIFACTS or file.stat().st_size > MAX_BYTES - total:
                raise ArchiveError("Archive exceeds recovery size or file-count limits")
            payload = file.read_bytes()
            total += len(payload)
            if total > MAX_BYTES:
                raise ArchiveError("Archive exceeds recovery size limit")
            found[name] = payload
    return found


def _snapshot_database(paths: AppPaths) -> bytes:
    path = paths.database_path
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ArchiveError("Missing, unsafe or oversized archive database")
    source = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    snapshot = sqlite3.connect(":memory:")
    try:
        source.backup(snapshot)
        payload = snapshot.serialize()
    finally:
        snapshot.close()
        source.close()
    if len(payload) > MAX_BYTES:
        raise ArchiveError("Database snapshot exceeds recovery size limit")
    if len(payload) < 100 or not payload.startswith(b"SQLite format 3\x00"):
        raise ArchiveError("Invalid SQLite snapshot")
    # backup() copies committed WAL pages into the self-contained in-memory DB,
    # but serialize() retains the source's WAL header (bytes 18/19). A standalone
    # image has no -wal/-shm files: change only its documented read/write version
    # bytes to rollback-journal format before integrity checking or restoring.
    if payload[18:20] == b"\x02\x02":
        payload = payload[:18] + b"\x01\x01" + payload[20:]
    elif payload[18:20] != b"\x01\x01":
        raise ArchiveError("Unsupported SQLite snapshot journal format")
    return payload


def _check_contents(database: bytes, artifacts: dict[str, bytes], key: bytes) -> int:
    """Verify SQLite, each encrypted value, and exact artifact-to-row provenance."""
    cipher = SensitiveStore(key)
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(database)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ArchiveError("Archive database integrity check failed")
        version_row = connection.execute("SELECT schema_version FROM schema_meta WHERE id = 1").fetchone()
        if version_row is None or not 1 <= version_row[0] <= Database.CURRENT_SCHEMA_VERSION:
            raise ArchiveError("Unsupported archive database schema")
        verified = 0
        for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            quoted_table = '"' + table.replace('"', '""') + '"'
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({quoted_table})")]
            encrypted = [name for name in columns if name.endswith("_enc")]
            if not encrypted:
                continue
            quoted_columns = ", ".join('"' + name.replace('"', '""') + '"' for name in encrypted)
            for row in connection.execute(f"SELECT {quoted_columns} FROM {quoted_table}"):
                for value in row:
                    if value is not None:
                        cipher.decrypt_bytes(value)
                        verified += 1
        referenced: set[str] = set()
        tables = {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "artifacts" in tables:
            for storage_key, size, hash_enc in connection.execute(
                "SELECT storage_key, byte_size, content_hash_enc FROM artifacts"
            ):
                if not isinstance(storage_key, str) or not re.fullmatch(r"[0-9a-f]{32}", storage_key):
                    raise ArchiveError("Invalid artifact reference in database")
                name = f"artifacts/{storage_key[:2]}/{storage_key[2:]}.dat"
                if name in referenced or name not in artifacts:
                    raise ArchiveError("Archive has missing or duplicate evidence")
                referenced.add(name)
                plaintext = cipher.decrypt_bytes(artifacts[name])
                if len(plaintext) != size or not hmac.compare_digest(
                    _digest(plaintext), cipher.decrypt_text(hash_enc)
                ):
                    raise ArchiveError("Artifact content disagrees with stored provenance")
                verified += 1
        if set(artifacts) != referenced:
            raise ArchiveError("Archive contains unreferenced or missing artifact files")
        if verified == 0:
            raise ArchiveError("Legacy archive has no ciphertext to authenticate its original key")
        return int(version_row[0])
    except (sqlite3.Error, InvalidTag, UnicodeError, ValueError, TypeError) as exc:
        raise ArchiveError("Archive data or encryption key could not be verified") from exc
    finally:
        connection.close()


def _build_plaintext(database: bytes, artifacts: dict[str, bytes], key: bytes, version: int) -> bytes:
    manifest = {
        "format": 1,
        "schema": version,
        "database": {"sha256": _digest(database), "bytes": len(database)},
        "artifacts": {
            name: {"sha256": _digest(payload), "bytes": len(payload)}
            for name, payload in sorted(artifacts.items())
        },
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.writestr(MANIFEST_MEMBER, json.dumps(manifest, sort_keys=True).encode("utf-8"))
        archive.writestr(KEY_MEMBER, key)
        archive.writestr(DB_MEMBER, database)
        for name, payload in sorted(artifacts.items()):
            archive.writestr(name, payload)
    payload = output.getvalue()
    if len(payload) > MAX_BYTES:
        raise ArchiveError("Complete archive exceeds the 128 MiB encrypted recovery limit")
    return payload


def _read_plaintext(payload: bytes) -> tuple[bytes, dict[str, bytes], bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            names = [item.filename for item in entries]
            if len(entries) > MAX_ARTIFACTS + 3 or len(names) != len(set(names)):
                raise ArchiveError("Unexpected or duplicated archive members")
            if not {MANIFEST_MEMBER, KEY_MEMBER, DB_MEMBER} <= set(names):
                raise ArchiveError("Archive has missing required members")
            total = 0
            for item in entries:
                total += item.file_size
                member_type = (item.external_attr >> 16) & 0o170000
                if (
                    total > MAX_BYTES
                    or item.is_dir()
                    or member_type not in (0, stat.S_IFREG)
                    or item.flag_bits & 1
                    or item.compress_type != zipfile.ZIP_STORED
                    or item.file_size != item.compress_size
                    or item.file_size > MAX_BYTES
                    or (
                        item.filename not in {MANIFEST_MEMBER, KEY_MEMBER, DB_MEMBER}
                        and not _safe_artifact_name(item.filename)
                    )
                ):
                    raise ArchiveError("Unexpected, oversized or unsafe archive member")
            manifest = json.loads(archive.read(MANIFEST_MEMBER))
            key = archive.read(KEY_MEMBER)
            database = archive.read(DB_MEMBER)
            artifacts = {
                name: archive.read(name)
                for name in names
                if name not in {MANIFEST_MEMBER, KEY_MEMBER, DB_MEMBER}
            }
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError, OSError) as exc:
        raise ArchiveError("Recovery package has invalid internal structure") from exc
    if len(key) != 32 or not isinstance(manifest, dict) or manifest.get("format") != 1:
        raise ArchiveError("Unsupported recovery package contents")
    expected = {
        "format": 1,
        "schema": manifest.get("schema"),
        "database": {"sha256": _digest(database), "bytes": len(database)},
        "artifacts": {
            name: {"sha256": _digest(data), "bytes": len(data)}
            for name, data in sorted(artifacts.items())
        },
    }
    if manifest != expected:
        raise ArchiveError("Recovery manifest checksum or member list disagrees")
    version = _check_contents(database, artifacts, key)
    if version != manifest["schema"]:
        raise ArchiveError("Recovery manifest schema disagrees with SQLite")
    return database, artifacts, key


def _validate_data_dir(paths: AppPaths) -> None:
    if paths.data_dir.is_symlink() or not paths.data_dir.is_dir():
        raise ArchiveError("Archive data directory is missing or unsafe")
    allowed = {
        paths.database_path.name,
        f"{paths.database_path.name}-wal",
        f"{paths.database_path.name}-shm",
        "artifacts",
    }
    if {item.name for item in paths.data_dir.iterdir()} - allowed:
        raise ArchiveError("Unexpected files in the data directory; nothing will be omitted")
    for item in paths.data_dir.iterdir():
        if item.is_symlink():
            raise ArchiveError("Symlinks in the archive are not supported")


def create_backup(
    paths: AppPaths, destination: Path, passphrase: str, *, secrets: SecretStore | None = None
) -> None:
    """Create an encrypted package without replacing an existing destination."""
    if destination.is_symlink() or destination.exists() or destination.parent.is_symlink():
        raise ArchiveError("Recovery output already exists or is unsafe")
    if len(passphrase) < 16:
        raise ArchiveError("Recovery passphrase must contain at least 16 characters")
    store = secrets if secrets is not None else SecretStore()
    with ArchiveLock(paths.data_dir):
        _validate_data_dir(paths)
        if destination.resolve().is_relative_to(paths.data_dir.resolve()):
            raise ArchiveError("Recovery package must be outside the application data directory")
        key = store.get_existing_master_key()
        if key is None:
            raise ArchiveError("Original archive encryption key is missing")
        database = _snapshot_database(paths)
        artifacts = _source_artifacts(paths)
        version = _check_contents(database, artifacts, key)
        plaintext = _build_plaintext(database, artifacts, key, version)
        salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
        encrypted = AESGCM(_derive(passphrase, salt)).encrypt(nonce, plaintext, MAGIC)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".gdpr-recovery-", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(MAGIC + salt + nonce + encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _install_directory_no_replace(staging: Path, destination: Path) -> None:
    """Linux renameat2(RENAME_NOREPLACE), never replace a raced destination."""
    if not sys.platform.startswith("linux"):
        raise ArchiveError("Safe directory installation is not supported on this platform")
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise ArchiveError("Safe no-replace directory installation is unavailable") from exc
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    # AT_FDCWD=-100; RENAME_NOREPLACE=1. Never fall back to rename() here.
    result = renameat2(-100, os.fsencode(staging), -100, os.fsencode(destination), 1)
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in (errno.EEXIST, errno.ENOTEMPTY):
        raise ArchiveError("Restore destination appeared during installation; no data was overwritten")
    raise OSError(error, "Safe restore installation failed")


def restore_backup(
    paths: AppPaths, source: Path, passphrase: str, *, secrets: SecretStore | None = None
) -> None:
    """Verify the entire package first, then install into a new data directory."""
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_BYTES + 1024:
        raise ArchiveError("Missing, unsafe or oversized recovery package")
    store = secrets if secrets is not None else SecretStore()
    with ArchiveLock(paths.data_dir):
        if paths.data_dir.exists() or paths.data_dir.is_symlink():
            raise ArchiveError("Restore refuses to overwrite an existing data directory")
        package = source.read_bytes()
        if len(package) > MAX_BYTES + 1024:
            raise ArchiveError("Recovery package exceeds the supported size limit")
        header_size = len(MAGIC) + SALT_BYTES + NONCE_BYTES
        if not package.startswith(MAGIC) or len(package) < header_size + 16:
            raise ArchiveError("Recovery package header or authentication tag is invalid")
        salt = package[len(MAGIC) : len(MAGIC) + SALT_BYTES]
        nonce = package[len(MAGIC) + SALT_BYTES : header_size]
        try:
            decrypted = AESGCM(_derive(passphrase, salt)).decrypt(nonce, package[header_size:], MAGIC)
        except InvalidTag as exc:
            raise ArchiveError("Incorrect passphrase or modified recovery package") from exc
        database, artifacts, key = _read_plaintext(decrypted)
        existing = store.get_existing_master_key()
        if existing is not None and not hmac.compare_digest(existing, key):
            raise ArchiveError("Credential store contains a different archive key; restore refused")
        paths.data_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".gdpr-restore-", dir=paths.data_dir.parent))
        try:
            _write_restricted(staging / paths.database_path.name, database)
            for name, payload in sorted(artifacts.items()):
                target_file = staging / name
                target_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                _write_restricted(target_file, payload)
            if paths.data_dir.exists() or paths.data_dir.is_symlink():
                raise ArchiveError("Restore destination appeared during validation")
            store.store_master_key_if_absent(key)
            # The matching key may remain on an interrupted rename: retrying the
            # same archive is safe, while a raced directory can never be replaced.
            _install_directory_no_replace(staging, paths.data_dir)
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def _write_restricted(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

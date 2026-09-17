from __future__ import annotations

import base64
import binascii
import hmac
import secrets

import keyring
from keyring.errors import KeyringError, NoKeyringError


class SecretStoreUnavailable(RuntimeError):
    pass


class ExistingArchiveKeyMissing(SecretStoreUnavailable):
    """An existing archive must never be paired with a replacement master key."""


class ArchiveKeyConflict(SecretStoreUnavailable):
    """Never replace another archive's existing credential-store key."""


class SecretStore:
    """Own the master key's operating-system credential-store lifecycle."""

    SERVICE_NAME = "gdpr-hunter"
    MASTER_KEY_NAME = "master-encryption-key-v1"

    def get_existing_master_key(self) -> bytes | None:
        try:
            encoded = keyring.get_password(self.SERVICE_NAME, self.MASTER_KEY_NAME)
            if encoded is None:
                return None
            key = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except (KeyringError, NoKeyringError, ValueError, UnicodeError, binascii.Error) as exc:
            raise SecretStoreUnavailable("No usable operating-system credential store is available") from exc
        if len(key) != 32:
            raise SecretStoreUnavailable("Stored master key has an invalid length")
        return key

    def store_master_key_if_absent(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("Master key must be 32 bytes")
        existing = self.get_existing_master_key()
        if existing is not None:
            if not hmac.compare_digest(existing, master_key):
                raise ArchiveKeyConflict("Existing credential-store key differs from recovery archive")
            return
        encoded = base64.urlsafe_b64encode(master_key).decode("ascii")
        try:
            keyring.set_password(self.SERVICE_NAME, self.MASTER_KEY_NAME, encoded)
        except (KeyringError, NoKeyringError, ValueError) as exc:
            raise SecretStoreUnavailable("Could not store archive encryption key") from exc
        saved = self.get_existing_master_key()
        if saved is None or not hmac.compare_digest(saved, master_key):
            raise ArchiveKeyConflict("Credential store did not preserve the recovery key")

    def get_or_create_master_key(self, *, create_if_missing: bool) -> bytes:
        key = self.get_existing_master_key()
        if key is not None:
            return key
        if not create_if_missing:
            raise ExistingArchiveKeyMissing(
                "Existing GDPR Hunter data was found, but its encryption key is missing"
            )
        key = secrets.token_bytes(32)
        self.store_master_key_if_absent(key)
        return key

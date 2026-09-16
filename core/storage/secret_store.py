from __future__ import annotations

import base64
import secrets

import keyring
from keyring.errors import KeyringError, NoKeyringError


class SecretStoreUnavailable(RuntimeError):
    pass


class ExistingArchiveKeyMissing(SecretStoreUnavailable):
    """An existing archive must never be paired with a replacement master key."""


class SecretStore:
    """Store application secrets in the operating-system credential backend."""

    SERVICE_NAME = "gdpr-hunter"
    MASTER_KEY_NAME = "master-encryption-key-v1"

    def get_or_create_master_key(self, *, create_if_missing: bool) -> bytes:
        try:
            encoded = keyring.get_password(self.SERVICE_NAME, self.MASTER_KEY_NAME)
            if encoded is None:
                if not create_if_missing:
                    raise ExistingArchiveKeyMissing(
                        "Existing GDPR Hunter data was found, but its encryption key is missing"
                    )
                key = secrets.token_bytes(32)
                encoded = base64.urlsafe_b64encode(key).decode("ascii")
                keyring.set_password(self.SERVICE_NAME, self.MASTER_KEY_NAME, encoded)
                return key
            key = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except (KeyringError, NoKeyringError, ValueError) as exc:
            raise SecretStoreUnavailable(
                "No usable operating-system credential store is available"
            ) from exc

        if len(key) != 32:
            raise SecretStoreUnavailable("Stored master key has an invalid length")
        return key

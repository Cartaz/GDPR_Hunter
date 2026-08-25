from __future__ import annotations

import os
import secrets
from pathlib import Path

from core.storage.sensitive_store import SensitiveStore


class ArtifactStore:
    """Own encrypted artifact bytes and opaque filesystem locations."""

    def __init__(self, root: Path, sensitive_store: SensitiveStore) -> None:
        self._root = root
        self._sensitive_store = sensitive_store

    def store(self, payload: bytes) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        storage_key = secrets.token_hex(16)
        destination = self._path_for(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary = destination.with_suffix(".tmp")
        encrypted = self._sensitive_store.encrypt_bytes(payload)
        with temporary.open("xb") as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
        return storage_key

    def read(self, storage_key: str) -> bytes:
        path = self._path_for(storage_key)
        return self._sensitive_store.decrypt_bytes(path.read_bytes())

    def delete(self, storage_key: str) -> None:
        path = self._path_for(storage_key)
        path.unlink(missing_ok=True)
        self._remove_empty_parent(path.parent)

    def _path_for(self, storage_key: str) -> Path:
        if len(storage_key) != 32 or any(character not in "0123456789abcdef" for character in storage_key):
            raise ValueError("Invalid artifact storage key")
        return self._root / storage_key[:2] / f"{storage_key[2:]}.dat"

    def _remove_empty_parent(self, directory: Path) -> None:
        try:
            directory.rmdir()
        except OSError:
            pass

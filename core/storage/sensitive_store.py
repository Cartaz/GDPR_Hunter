from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SensitiveStore:
    """Encrypt and authenticate sensitive values before persistence."""

    VERSION = b"GH1"
    NONCE_SIZE = 12

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("SensitiveStore requires a 256-bit master key")
        self._cipher = AESGCM(master_key)

    def encrypt_bytes(self, plaintext: bytes) -> bytes:
        nonce = os.urandom(self.NONCE_SIZE)
        ciphertext = self._cipher.encrypt(nonce, plaintext, self.VERSION)
        return self.VERSION + nonce + ciphertext

    def decrypt_bytes(self, payload: bytes) -> bytes:
        minimum_size = len(self.VERSION) + self.NONCE_SIZE + 16
        if len(payload) < minimum_size or not payload.startswith(self.VERSION):
            raise ValueError("Unsupported or malformed encrypted payload")
        start = len(self.VERSION)
        nonce = payload[start : start + self.NONCE_SIZE]
        ciphertext = payload[start + self.NONCE_SIZE :]
        return self._cipher.decrypt(nonce, ciphertext, self.VERSION)

    def encrypt_text(self, plaintext: str) -> bytes:
        return self.encrypt_bytes(plaintext.encode("utf-8"))

    def decrypt_text(self, payload: bytes) -> str:
        return self.decrypt_bytes(payload).decode("utf-8")

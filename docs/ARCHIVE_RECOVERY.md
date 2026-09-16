# Archive recovery and key ownership

GDPR Hunter stores its SQLite database and encrypted artifacts under the user's XDG data directory. The master encryption key is a separate secret in the operating-system credential store (`gdpr-hunter` / `master-encryption-key-v1`). The application does **not** store that key in the database, settings or repository.

## If startup reports that an existing archive has no key

Stop. Do not delete the database, the artifacts directory, or the credential-store entry in an attempt to reset the application. GDPR Hunter now refuses to generate a replacement master key when either the database file or the artifacts directory already exists. This check occurs before database initialization or migration. It does not decrypt or modify the archive.

Recover the **original** credential-store key using your operating system's supported recovery procedure, together with the matching database and encrypted artifacts. A newly generated key cannot decrypt the existing data. Do not publish the key, include it in an issue, or send it to a remote inference service.

The guard prevents accidental key replacement; it is **not** a backup or recovery implementation. A missing database and missing artifacts directory are interpreted as first launch. Therefore, a partial restore that introduces old data only *after* a new first launch is not supported and may leave mismatched keys. Restore and check the complete archive and original key before launching the application.

## Current limitations and release gate

There is not yet an application-level, tested backup/restore workflow that captures a consistent SQLite snapshot, all encrypted artifact files, and a separately protected matching key. Copying the SQLite file while the application is running is not a guaranteed consistent backup. The application also does not yet verify an existing master key against a database key-check sentinel at startup, and a present but incorrect 32-byte key can cause decryption failures when records are read.

Do not rely on GDPR Hunter as the only copy of legally significant correspondence or evidence. Before a production release, implement and test a complete backup/restore procedure, an authenticated key check, and safe user-facing handling of corrupted ciphertext and missing artifacts. Use disposable test archives when validating recovery; do not test by deleting the only production key.

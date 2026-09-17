# Archive recovery and key ownership

GDPR Hunter stores SQLite operational data and encrypted artifacts under the user's XDG data directory (normally `~/.local/share/gdpr-hunter`). Its matching 256-bit master key is held separately in the operating-system credential store as `gdpr-hunter` / `master-encryption-key-v1`. Some Target metadata in SQLite is plaintext. Neither that metadata nor the master key should ever be published or uploaded.

## Offline recovery tool (development feature)

The offline maintenance tool produces **one entirely AES-256-GCM-encrypted package** containing a SQLite backup-API snapshot, encrypted artifacts, their names and checksum manifest, and the original master key. The envelope key is derived from an independently chosen passphrase with scrypt (N=32768, r=8, p=1, random 16-byte salt). The passphrase is entered via a non-echoing terminal prompt and is never accepted as a command-line argument. There is no model or network connection. ZIP members exist only inside the authenticated encrypted envelope; an unencrypted ZIP and the key reside in process memory, not a temporary recovery file. The package contains highly sensitive personal information: protect both it and an independent copy of its passphrase.

**Close GDPR Hunter before running these commands**, and use a terminal on your own machine. New app instances and the offline tool share an exclusive process lock. The lock cannot stop older builds that did not participate in it, another process directly writing SQLite, or external modification of artifact files. Stop those processes as well.

Backup to a new path *outside* the app data directory:

```bash
.venv/bin/python archive_tool.py backup /path/outside/data/gdpr-archive.ghbackup
```

The tool prompts twice for a passphrase of at least 16 characters. It will not replace an existing package. Check for successful completion and retain the package and passphrase separately. SQLite's backup API includes committed WAL changes. When the self-contained snapshot inherits a WAL-format SQLite header, the two SQLite read/write version bytes are normalized to rollback-journal format; the payload is then checked for integrity and authenticated against encrypted data.

Restore only onto an installation whose **data directory does not yet exist** (for example a new disposable XDG profile, not the original populated profile):

```bash
.venv/bin/python archive_tool.py restore /path/outside/data/gdpr-archive.ghbackup
```

The tool prompts for the passphrase, authenticates the envelope, checks the bounded ZIP members and manifest, validates SQLite integrity, verifies encrypted database values and artifact provenance, and refuses an existing data directory or an unrelated key already in the credential store. It stages data before installing the matching key and moving the directory into place. On Linux, the final directory move uses `renameat2(RENAME_NOREPLACE)` and never falls back to a rename that can replace an unexpectedly created destination. **Restore currently fails closed on other platforms** until an equally safe no-replace directory-installation primitive is implemented. The tool does not delete or overwrite existing archives or keys. Validate recovery first with disposable profiles; never delete the last original copy just to make space for restoration.

An interrupted restore may leave the matching key in the credential store but no data directory. Re-run restore with the same package/key; a matching key is intentionally reused. If an unrelated key is present, restore fails. Use an isolated operating-system profile or an officially supported credential-store recovery procedure instead of deleting an existing key blindly. The XDG configuration directory (`settings.json`) is not included: the package restores operational data, evidence and its key, not machine-specific inference/UI preferences.

## If startup reports a missing original key

Do not delete SQLite, the artifacts directory or the keyring entry. Startup refuses to generate a replacement key when archive files exist, before database initialization/migration. Recover the original credential-store key or restore the complete verified package in an empty profile. A newly generated key cannot decrypt old evidence. Never send packages, passwords or keys to GitHub, an LLM or support providers.

## Explicit limits and unresolved release blockers

- **128 MiB maximum unencrypted internal package and at most 2,000 artifacts.** Both individual and aggregate ZIP member sizes are checked before extraction; unexpected paths, symlinks, compression and duplicate entries are rejected. The implementation holds the complete SQLite snapshot and ZIP/envelope in bounded memory instead of writing a plaintext recovery archive to disk. Larger archives fail closed. This is not yet a production-scale streaming backup solution, and several in-memory copies may coexist near the limit.
- Backup refuses legacy archives that contain **no encrypted record or artifact capable of authenticating the original key**. It does not bless an arbitrary 32-byte key. A separate explicitly verified migration/key-check procedure is still required for such archives.
- The application does **not** yet persist and verify a dedicated key-check sentinel at every GUI startup. The offline tool checks existing ciphertext and detects wrong keys during backup/restore, but an incorrect present key can still evade detection until the GUI reads encrypted data. Implement the startup sentinel before production release.
- Artifact consistency depends on an exclusive lock shared by participating processes and an operator stopping non-participating writers. An adversarial external process racing artifact path checks, an unsafe ancestor directory, or other filesystem mutation is outside the current threat model. Review descriptor-based artifact reads and ancestor-directory validation before production release.
- The process may hold sensitive content in memory/swap. Restore writes an ordinary SQLite file containing some unencrypted Target metadata into a private staging directory before installation. At-rest disk/swap encryption is recommended; Python cannot guarantee zeroization of in-memory copies or secure deletion of staging files on flash media after a crash.
- The Linux final directory install prevents a race from replacing a newly appeared **destination entry**, but not malicious modifications to writable ancestor directories. The keyring and filesystem are not atomically committed together: if interrupted after installing a matching key but before installing data, restore can be retried without deleting that key.
- No CachyOS/KDE native validation with KWallet/Secret Service has been performed here. Ubuntu CI is not a native acceptance test. The backup tool remains in development and must not be the sole copy of legally significant correspondence.

Manual CachyOS/KDE checks: verify keyring unlock; create a disposable archive with encrypted identity, artifact and correspondence; back it up with the app closed; inspect the package for recognizable plaintext; restore to an isolated empty XDG data/profile with matching or absent key; open the restored application and inspect the evidence; test wrong passphrase/key, simultaneous application/maintenance, two-instance locking, interrupted restore and retry, and refusal to overwrite a destination created just before installation. Never test by deleting the only real production key.

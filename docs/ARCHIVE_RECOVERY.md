# Archive recovery and key ownership

GDPR Hunter stores operational SQLite data and encrypted artifacts under the user's XDG data directory (normally `~/.local/share/gdpr-hunter`). The matching 256-bit master key is held separately in the operating-system credential store as `gdpr-hunter` / `master-encryption-key-v1`. Some Target metadata in SQLite is plaintext. Neither that metadata nor the master key should ever be published or uploaded.

## Offline recovery tool (development feature)

The experimental offline maintenance command produces **one entirely AES-256-GCM-encrypted package** containing a SQLite backup-API snapshot, encrypted artifacts, their names and checksum manifest, and the original master key. It derives an envelope key from a separately chosen passphrase with scrypt (N=32768, r=8, p=1, random 16-byte salt). The passphrase is entered with a non-echoing terminal prompt and is never accepted as a command-line argument. No model or network connection is involved. All ZIP members exist only inside an authenticated encrypted envelope; the unencrypted ZIP and key exist in process memory, not a temporary file. The resulting package still contains highly sensitive personal information: store it securely and keep an independent copy of its passphrase.

**Close GDPR Hunter before running these commands** and use a terminal on your own machine. New app instances and the offline tool share a process-wide archive lock. This cannot detect an older application build that did not participate in the lock, or another process manually writing the database. Stop those processes too.

Backup to a new path *outside* the app data directory:

```bash
.venv/bin/python archive_tool.py backup /path/outside/data/gdpr-archive.ghbackup
```

The tool prompts twice for a passphrase of at least 16 characters. The output must not already exist and will not be replaced. Confirm that the command succeeds and retain the package and passphrase separately.

Restore only onto an installation whose **data directory does not yet exist** (for example a new disposable XDG profile, not the original populated profile):

```bash
.venv/bin/python archive_tool.py restore /path/outside/data/gdpr-archive.ghbackup
```

The tool prompts for the backup passphrase, authenticates the whole envelope, checks the manifest and SQLite integrity, verifies encrypted database values and artifact provenance, and refuses an existing data directory or a different key already in the operating-system credential store. It stages data before installing the key and moving the directory into place. It does not delete or overwrite existing archives or keys. Never delete the only original copy to make a restore possible; validate recovery first with disposable profiles.

A crashed restore may leave the matching key in the credential store but no data directory. Re-running restore with the same package/key is intentionally safe. If an unrelated key is already present, restore fails; use an isolated operating-system profile or an appropriate officially supported keyring recovery procedure rather than deleting a key blindly. The XDG configuration directory (`settings.json`) is not included: this package restores operational data, evidence and the encryption key, not machine-specific inference/UI preferences.

## If startup reports a missing original key

Do not delete the SQLite archive, artifacts directory or keyring entry. Startup refuses to generate a replacement key whenever an archive already exists, before SQLite initialization/migration. Recover the original credential-store key or use the complete verified package above in an empty profile; a newly generated key cannot decrypt old evidence. Do not send packages or keys to GitHub, an LLM or external support.

## Explicit limits and unresolved release blockers

- **128 MiB maximum unencrypted internal package and at most 2,000 artifacts.** The offline implementation deliberately holds a complete SQLite snapshot and ZIP/envelope in bounded memory rather than writing a plaintext recovery archive to disk. Larger archives are rejected, not silently truncated. This is an initial development limitation, not a production-scale streaming backup solution.
- Backup refuses legacy archives with **no encrypted record or artifact to authenticate the original key**. It does not silently bless a random 32-byte key. Such archives require a separately designed authenticated migration/key-check procedure.
- No dedicated persistent key-check sentinel is yet verified during normal GUI startup. The offline tool checks existing encrypted values, but normal application startup may still defer detection of a wrong present key until decryption; this remains a release blocker.
- The database is backed up via SQLite's backup API; WAL content is captured. Filesystem artifact consistency relies on the GUI's exclusive lock and the operator closing old/non-participating writers.
- The process may hold sensitive material in memory/swap. The restored application's SQLite database still contains existing plaintext Target metadata, and briefly exists in its private staging directory during restore. At-rest disk/swap encryption is recommended; Python cannot guarantee zeroization of copies in memory or securely erase an interrupted plaintext staging file on flash storage.
- A malicious external process racing the empty-destination check is not yet defended by a platform-specific no-replace directory rename. Keep the destination private; this race must be fixed before production release.
- Keyring and filesystem cannot be atomically committed together. If interrupted after key installation but before moving data, recovery is retryable with the same key and package. There is no automatic deletion of credentials or existing data.
- This implementation has not been validated on CachyOS/KDE with KWallet/Secret Service; CI on Ubuntu is not a substitute for native testing. Do not treat it as production-ready or as the only copy of significant correspondence.

Manual CachyOS/KDE checklist: verify that the keyring unlocks, create a disposable populated archive with an artifact and correspondence, back it up while the app is closed, verify the package contains no recognizable plaintext, restore into an isolated empty XDG data/profile with a matching or absent key, open the restored app and read evidence, then test wrong passphrase/key, simultaneous running app and two-instance lock, interrupted restore and successful retry. Never test by deleting the only real production key.

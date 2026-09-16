"""Offline GDPR Hunter recovery: no GUI, model, or network permissions."""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from core.application.archive_lock import ArchiveBusy
from core.application.paths import default_app_paths
from core.storage.archive_recovery import ArchiveError, create_backup, restore_backup
from core.storage.secret_store import SecretStoreUnavailable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GDPR Hunter offline encrypted backup and restore")
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("package", type=Path, help="Path to encrypted recovery package")
    arguments = parser.parse_args(argv)
    try:
        password = getpass.getpass("Recovery passphrase: ")
        if arguments.action == "backup":
            confirmation = getpass.getpass("Repeat recovery passphrase: ")
            if password != confirmation:
                raise ArchiveError("Recovery passphrases do not match")
            create_backup(default_app_paths(), arguments.package, password)
        else:
            restore_backup(default_app_paths(), arguments.package, password)
    except (ArchiveError, ArchiveBusy, SecretStoreUnavailable) as exc:
        print(f"Recovery failed: {exc}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, RuntimeError, ValueError):
        print("Recovery failed: local storage or credential operation failed; check permissions and retry.", file=sys.stderr)
        return 1
    print("Encrypted archive backup completed." if arguments.action == "backup" else "Archive restore completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Cross-process lock shared by the GUI and offline archive maintenance."""

from __future__ import annotations

import errno
import os
from pathlib import Path


class ArchiveBusy(RuntimeError):
    """Another GDPR Hunter process owns the archive."""


class ArchiveLock:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir.parent / f".{data_dir.name}.lock"
        self._descriptor: int | None = None

    def __enter__(self) -> ArchiveLock:
        if self._descriptor is not None:
            raise RuntimeError("Archive lock already held")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.parent.is_symlink() or self._path.is_symlink():
            raise RuntimeError("Unsafe archive lock path")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self._path, flags, 0o600)
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(descriptor)
            if getattr(exc, "errno", None) in (errno.EAGAIN, errno.EACCES, errno.EDEADLK):
                raise ArchiveBusy("Close GDPR Hunter before archive maintenance") from exc
            raise
        self._descriptor = descriptor
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

"""Single-host interprocess exclusive lock, RELEASED ON PROCESS DEATH.

Round-7 finding 6: the O_EXCL sentinel-file lock survived a killed
process forever, blocking even recovery. This implementation locks a
byte range of a PERSISTENT lock file through the OS lock table
(msvcrt.locking on Windows, fcntl.flock on POSIX) — the operating
system releases the lock automatically when the holder dies, so an
orphaned lock cannot exist. The lock file itself is never deleted;
its presence carries no meaning, only the OS lock does.

Shared by the raw store (whole write transaction) and the acquisition
ledger (append transaction). Advisory and single-host by design.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from qlir import QlirError

LOCK_TIMEOUT_S = 10.0

if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:  # POSIX
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class ExclusiveLock:
    def __init__(self, target: Path, timeout_s: float = LOCK_TIMEOUT_S) -> None:
        self.lock_path = Path(str(target) + ".lock")
        self.timeout_s = timeout_s
        self._fd: int | None = None

    def __enter__(self) -> ExclusiveLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")  # the byte the OS lock covers
        deadline = time.monotonic() + self.timeout_s
        while True:
            if _try_lock(fd):
                self._fd = fd
                return self
            if time.monotonic() >= deadline:
                os.close(fd)
                raise QlirError(
                    f"resource is locked by another LIVE writer ({self.lock_path}); "
                    "a killed process cannot hold this lock — the OS releases it "
                    "on process death"
                )
            time.sleep(0.02)

    def __exit__(self, *exc_info: object) -> None:
        if self._fd is not None:
            try:
                _unlock(self._fd)
            finally:
                os.close(self._fd)
                self._fd = None

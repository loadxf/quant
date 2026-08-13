"""Single-host interprocess exclusive lock (O_CREAT|O_EXCL lock file).

Shared by the raw store (whole write transaction) and the acquisition
ledger (append transaction). Advisory and single-host by design — this
matches the one-machine acquisition reality and is stated, not hidden.
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

from qlir import QlirError

LOCK_TIMEOUT_S = 10.0


class ExclusiveLock:
    def __init__(self, target: Path, timeout_s: float = LOCK_TIMEOUT_S) -> None:
        self.lock_path = Path(str(target) + ".lock")
        self.timeout_s = timeout_s
        self._fd: int | None = None

    def __enter__(self) -> ExclusiveLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                self._fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise QlirError(
                        f"resource is locked by another writer ({self.lock_path}); "
                        "remove the stale lock only if you are certain no writer "
                        "is active"
                    ) from None
                time.sleep(0.02)

    def __exit__(self, *exc_info: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        with contextlib.suppress(OSError):
            os.unlink(self.lock_path)

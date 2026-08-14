"""Round-7 finding 6: a KILLED process must not orphan the lock. The
lock lives in the OS lock table (msvcrt.locking / fcntl.flock) and is
released automatically on process death — proven by an actual killed
subprocess, not an exception."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from qlir import QlirError
from qlir.locks import ExclusiveLock

SRC = Path(__file__).resolve().parents[1] / "src"

HOLDER = """
import sys, time
sys.path.insert(0, {src!r})
from qlir.locks import ExclusiveLock
with ExclusiveLock({target!r}):
    print("HELD", flush=True)
    time.sleep(60)
"""


def spawn_holder(target: Path) -> subprocess.Popen:
    code = HOLDER.format(src=str(SRC), target=str(target))
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    line = proc.stdout.readline().strip()
    assert line == "HELD", (line, proc.stderr.read() if proc.stderr else "")
    return proc


class TestProcessDeath:
    def test_killed_holder_releases_the_lock(self, tmp_path) -> None:
        """Sol's reproduction inverted: kill the holding process, then
        acquire successfully — no orphaned sentinel, no manual cleanup."""
        target = tmp_path / "acquisition.jsonl"
        holder = spawn_holder(target)
        try:
            # While the subprocess LIVES, acquisition must time out.
            with (
                pytest.raises(QlirError, match="LIVE writer"),
                ExclusiveLock(target, timeout_s=0.5),
            ):
                pass  # pragma: no cover
            holder.kill()
            holder.wait(timeout=10)
            # After death the OS releases the lock: acquisition succeeds.
            deadline = time.monotonic() + 10
            acquired = False
            while time.monotonic() < deadline:
                try:
                    with ExclusiveLock(target, timeout_s=1.0):
                        acquired = True
                    break
                except QlirError:  # pragma: no cover - OS release latency
                    time.sleep(0.1)
            assert acquired, "lock was not released by process death"
        finally:
            if holder.poll() is None:  # pragma: no cover
                holder.kill()

    def test_recovery_possible_after_killed_append(self, tmp_path) -> None:
        """The round-7 wedge end-to-end: recover_ledger must be callable
        after the previous locker died mid-transaction."""
        target = tmp_path / "acquisition.jsonl"
        holder = spawn_holder(target)
        holder.kill()
        holder.wait(timeout=10)
        from qlir.manifest import recover_ledger

        deadline = time.monotonic() + 10
        while True:
            try:
                recover_ledger(target)  # empty ledger: recovery is a no-op
                break
            except QlirError:  # pragma: no cover - OS release latency
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    def test_live_holder_still_blocks(self, tmp_path) -> None:
        target = tmp_path / "acquisition.jsonl"
        with (
            ExclusiveLock(target),
            pytest.raises(QlirError, match="LIVE writer"),
            ExclusiveLock(target, timeout_s=0.3),
        ):
            pass  # pragma: no cover

    def test_reentry_after_clean_exit(self, tmp_path) -> None:
        target = tmp_path / "acquisition.jsonl"
        with ExclusiveLock(target):
            pass
        with ExclusiveLock(target, timeout_s=1.0):
            pass  # immediate re-acquisition

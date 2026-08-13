"""Immutable raw-file store with a sha256 manifest.

The MANIFEST is the identity record, not the file: once a logical path
(dataset/schema/symbol/date) has a recorded hash, only byte-identical
content may ever occupy it again — even if the file itself was deleted
(round 4, blocker 2: delete-then-rewrite must not silently mutate raw
history). Restoring a lost file with its original bytes is legal;
anything else raises. Corrections happen by adding a new dataset
version directory, never by mutating raw history.

Writes are ATOMIC and TRANSACTIONAL: the whole read-check-install-record
sequence runs under one interprocess exclusive lock (round 5, defect 2 —
atomic file replacement alone does not make the multi-file sequence
atomic; two racing writers could both see an absent identity and both
"succeed"). Under a same-path/different-digest race exactly one writer
succeeds; distinct-path writers serialize and both entries survive.
Payloads land in a temp file installed with os.replace, so an
interrupted write can never leave a half-written file or truncated
manifest. The lock is single-host advisory — the acquisition reality.

``manifests/files.sha256`` uses sha256sum format (``<hex>  <relpath>``,
sorted, unique) so any later tamper or bit-rot is detectable by
``verify()``.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from pathlib import Path

from qlir import QlirError
from qlir.locks import ExclusiveLock

MANIFEST_NAME = "files.sha256"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


class RawStore:
    """`root` is the q_lir data root (contains raw/ and manifests/)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.manifest_path = self.root / "manifests" / MANIFEST_NAME

    def path_for(self, dataset: str, schema: str, symbol: str, date: str) -> Path:
        for part in (dataset, schema, symbol, date):
            if not part or "/" in part or "\\" in part or ".." in part:
                raise QlirError(f"unsafe path component {part!r}")
        return self.raw_dir / dataset / schema / symbol / f"{date}.dbn.zst"

    # -- manifest ---------------------------------------------------------
    def _read_manifest(self) -> dict[str, str]:
        if not self.manifest_path.exists():
            return {}
        entries: dict[str, str] = {}
        for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                digest, relpath = line.split("  ", 1)
            except ValueError:
                raise QlirError(f"malformed manifest line: {line!r}") from None
            if relpath in entries:
                raise QlirError(f"duplicate manifest entry for {relpath!r}")
            entries[relpath] = digest
        return entries

    def _write_manifest(self, entries: dict[str, str]) -> None:
        lines = [f"{digest}  {relpath}" for relpath, digest in sorted(entries.items())]
        _atomic_write_bytes(self.manifest_path, ("\n".join(lines) + "\n").encode("utf-8"))

    # -- writes -----------------------------------------------------------
    def write_raw(self, dataset: str, schema: str, symbol: str, date: str, payload: bytes) -> Path:
        """Write one immutable raw file and record its hash.

        Identity law: the MANIFEST hash for a logical path is permanent.
        - New identity: install atomically, record the hash.
        - Existing identity + identical bytes: idempotent (also restores
          a deleted file from the original bytes).
        - Existing identity + different bytes: QlirError, even when the
          file on disk is missing — raw history never mutates.
        - Untracked file already at the target: adopted only if the
          payload is byte-identical; otherwise refused.
        """
        if not payload:
            raise QlirError("refusing to write an empty raw file")
        path = self.path_for(dataset, schema, symbol, date)
        relpath = path.relative_to(self.root).as_posix()
        new_digest = hashlib.sha256(payload).hexdigest()
        # ONE lock spans manifest read, path inspection, install, and
        # manifest update — the transaction, not just the file writes.
        with ExclusiveLock(self.manifest_path):
            entries = self._read_manifest()
            recorded = entries.get(relpath)
            if recorded is not None:
                if recorded != new_digest:
                    raise QlirError(
                        f"IMMUTABLE raw identity {relpath} is recorded with hash "
                        f"{recorded[:12]}…; refusing different bytes ({new_digest[:12]}…) "
                        "even though the file "
                        + ("exists." if path.exists() else "was deleted.")
                        + " Corrections require a new dataset version directory."
                    )
                if path.exists() and sha256_file(path) == new_digest:
                    return path  # fully idempotent
                _atomic_write_bytes(path, payload)  # legal restore of original bytes
                return path
            if path.exists():
                existing = sha256_file(path)
                if existing != new_digest:
                    raise QlirError(
                        f"untracked file already at {relpath} with hash {existing[:12]}… "
                        f"differs from the payload ({new_digest[:12]}…) — refusing to "
                        "overwrite or adopt it; investigate its provenance"
                    )
                # Byte-identical untracked file: adopt it into the manifest.
            else:
                _atomic_write_bytes(path, payload)
            entries[relpath] = new_digest
            self._write_manifest(entries)
            return path

    # -- verification -----------------------------------------------------
    def verify(self) -> list[str]:
        """Return problems (empty list == everything checks out):
        missing files, hash mismatches, and untracked raw files."""
        problems: list[str] = []
        entries = self._read_manifest()
        for relpath, digest in entries.items():
            path = self.root / relpath
            if not path.exists():
                problems.append(f"MISSING: {relpath}")
            elif sha256_file(path) != digest:
                problems.append(f"HASH MISMATCH: {relpath}")
        if self.raw_dir.exists():
            tracked = set(entries)
            for path in sorted(self.raw_dir.rglob("*.dbn.zst")):
                relpath = path.relative_to(self.root).as_posix()
                if relpath not in tracked:
                    problems.append(f"UNTRACKED: {relpath}")
        return problems

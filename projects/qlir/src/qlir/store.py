"""Immutable raw-file store with a sha256 manifest.

Raw DBN files are written exactly once. Re-writing identical bytes is a
no-op; re-writing different bytes RAISES — corrections happen by adding
a new dataset version, never by mutating raw history. Every file's hash
lives in ``manifests/files.sha256`` (sha256sum format: ``<hex>  <relpath>``,
sorted, unique) so any later tamper or bit-rot is detectable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from qlir import QlirError

MANIFEST_NAME = "files.sha256"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{digest}  {relpath}" for relpath, digest in sorted(entries.items())]
        self.manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # -- writes -----------------------------------------------------------
    def write_raw(self, dataset: str, schema: str, symbol: str, date: str, payload: bytes) -> Path:
        """Write one immutable raw file and record its hash.

        Identical re-write: no-op. Different bytes for an existing path:
        QlirError — raw history is immutable.
        """
        if not payload:
            raise QlirError("refusing to write an empty raw file")
        path = self.path_for(dataset, schema, symbol, date)
        new_digest = hashlib.sha256(payload).hexdigest()
        if path.exists():
            existing = sha256_file(path)
            if existing != new_digest:
                raise QlirError(
                    f"IMMUTABLE raw file {path} already exists with hash {existing[:12]}…; "
                    f"refusing to overwrite with different bytes ({new_digest[:12]}…). "
                    "Corrections require a new dataset version directory."
                )
            return path  # identical bytes — idempotent
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        entries = self._read_manifest()
        relpath = path.relative_to(self.root).as_posix()
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

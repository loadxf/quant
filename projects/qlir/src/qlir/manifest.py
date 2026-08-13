"""Hash-chained, append-only acquisition ledger (acquisition.jsonl).

Round-4 redesign (Sol blockers): the ledger is a JSONL file written by
O_APPEND single-line writes under an exclusive lock file — existing
bytes are never rewritten, so it is genuinely append-only and safe
against concurrent writers and interrupted replacement. Every line is

    {"prev_hash": <hex>, "record_hash": <hex>, "record": {...}}

where record_hash = sha256(prev_hash + canonical_json(record)) and the
first line chains from GENESIS. Any edit, reorder, or deletion of a
prior line breaks the chain and every subsequent read fails closed.

The LOCKED PERIOD is enforced from the parsed UTC dates, not the
caller-supplied split label: any record whose range touches 2025-01-01
or later is refused outright, and the split label must agree with the
dates (development: entirely before 2024-01-01; validation: entirely
inside 2024; ranges crossing 2024-01-01 must be split per period).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from qlir import QlirError

GENESIS = "0" * 64
LOCKED_START_UTC = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
VALIDATION_START_UTC = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
LOCK_TIMEOUT_S = 10.0

REQUIRED_FIELDS: tuple[str, ...] = (
    "dataset",
    "schema",
    "requested_symbols",
    "stype_in",
    "stype_out",
    "resolved_contracts",
    "start_utc",
    "end_utc",
    "request_cost_usd",
    "record_count",
    "billable_size_bytes",
    "client_version",
    "file_hashes",
    "dataset_conditions",
    "derivation_code_commit",
    "split",
)


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)


def _link_hash(prev_hash: str, record: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical(record)).encode("utf-8")).hexdigest()


def _parse_utc(value: str, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise QlirError(f"{field} is not an ISO-8601 datetime: {value!r}") from None
    if parsed.tzinfo is None:
        raise QlirError(f"{field} must be timezone-aware UTC (got naive {value!r})")
    return parsed.astimezone(dt.UTC)


def split_for_range(start: dt.datetime, end: dt.datetime) -> str:
    """Date-derived split classification; the LOCK comes from dates."""
    if end <= start:
        raise QlirError("end_utc must be after start_utc")
    if end > LOCKED_START_UTC:
        raise QlirError(
            "LOCKED PERIOD: the requested range touches 2025-01-01 or later; "
            "locked-test data may not be acquired until validation decisions "
            "are frozen (Sol/Fable protocol) — this lock is date-derived and "
            "cannot be bypassed with a split label"
        )
    if end <= VALIDATION_START_UTC:
        return "development"
    if start >= VALIDATION_START_UTC:
        return "validation"
    raise QlirError(
        "range crosses 2024-01-01 (development/validation boundary) — split "
        "the acquisition into one request per period"
    )


def validate_record(record: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise QlirError(f"acquisition record missing required fields: {missing}")
    if not isinstance(record["requested_symbols"], list) or not record["requested_symbols"]:
        raise QlirError("requested_symbols must be a non-empty list")
    start = _parse_utc(record["start_utc"], "start_utc")
    end = _parse_utc(record["end_utc"], "end_utc")
    derived = split_for_range(start, end)  # raises on any locked-period touch
    if record["split"] != derived:
        raise QlirError(
            f"split label {record['split']!r} contradicts the date-derived "
            f"classification {derived!r} — labels never override dates"
        )


class _LedgerLock:
    """Exclusive advisory lock via O_CREAT|O_EXCL lock file."""

    def __init__(self, ledger_path: Path, timeout_s: float = LOCK_TIMEOUT_S) -> None:
        self.lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
        self.timeout_s = timeout_s
        self._fd: int | None = None

    def __enter__(self) -> _LedgerLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                self._fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise QlirError(
                        f"acquisition ledger is locked by another writer "
                        f"({self.lock_path}); remove the stale lock only if you "
                        "are certain no writer is active"
                    ) from None
                time.sleep(0.05)

    def __exit__(self, *exc_info: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        with contextlib.suppress(OSError):
            os.unlink(self.lock_path)


def _read_links(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    links: list[dict[str, Any]] = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            link = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QlirError(f"ledger line {i} is not valid JSON: {exc}") from exc
        if not isinstance(link, dict) or {"prev_hash", "record_hash", "record"} - set(link):
            raise QlirError(f"ledger line {i} lacks the chain envelope")
        links.append(link)
    return links


def verify_ledger(path: Path) -> list[dict[str, Any]]:
    """Verify the full hash chain; return the wrapped links. Any tamper,
    reorder, or deletion of a prior line fails closed."""
    links = _read_links(Path(path))
    prev = GENESIS
    for i, link in enumerate(links):
        if link["prev_hash"] != prev:
            raise QlirError(
                f"ledger chain broken at line {i}: prev_hash {link['prev_hash'][:12]}… "
                f"does not match expected {prev[:12]}…"
            )
        expected = _link_hash(prev, link["record"])
        if link["record_hash"] != expected:
            raise QlirError(
                f"ledger record {i} hash mismatch — the record was modified after it was chained"
            )
        prev = link["record_hash"]
    return links


def load_ledger(path: Path) -> list[dict[str, Any]]:
    """Chain-verified records (unwrapped)."""
    return [link["record"] for link in verify_ledger(path)]


def append_acquisition(path: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate and append one record under an exclusive lock via a pure
    O_APPEND write — prior bytes are never rewritten."""
    validate_record(record)
    path = Path(path)
    with _LedgerLock(path):
        links = verify_ledger(path)  # refuses to extend a corrupt chain
        prev = links[-1]["record_hash"] if links else GENESIS
        link = {
            "prev_hash": prev,
            "record_hash": _link_hash(prev, record),
            "record": record,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(link, sort_keys=True, separators=(",", ":"), default=str) + "\n"
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
    return [*(link_["record"] for link_ in links), record]

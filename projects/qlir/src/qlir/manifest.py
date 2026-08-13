"""Hash-chained, anchored, RECOVERABLE append-only acquisition ledger
(round 6).

Structure: `acquisition.jsonl` — one JSON line per receipt:

    {"prev_hash": <hex>, "record_hash": <hex>, "record": {...}}

chained from GENESIS, plus a sibling ANCHOR (`.anchor`: expected count +
terminal hash) and, transiently, a PENDING journal (`.pending`) that
makes the two-file append a RECOVERABLE transaction (round 6, finding
4: an anchor-write failure between the two operations used to wedge the
ledger permanently).

Append protocol (all under one exclusive lock):
  1. verify current chain+anchor (recovering any pending transaction);
  2. atomically write `.pending` = {prev_anchor, line, new_anchor};
  3. O_APPEND the line to the ledger (fsync);
  4. atomically write the anchor;
  5. delete `.pending`.
Recovery is deterministic from the journal: ledger still at the prior
count → roll BACK (delete pending); line fully present → roll FORWARD
(write anchor, delete pending); a TORN last line (the only non-atomic
step) → strip the uncommitted bytes back to the journaled prior state.
Unlocked reads refuse while a pending journal exists (call
`recover_ledger`). Failure-injection tests cover every boundary.

RECEIPT BINDING (round 6, finding 1): a receipt is refused unless
  - set(requested_symbols) == set(resolved_contracts keys);
  - the contract map covers every date in [start_utc, end_utc);
  - `files` is an immutable per-acquisition list of
    {relative_path, sha256, size_bytes, record_count} (never a pointer
    to a mutable cumulative manifest);
  - record_count equals the sum of per-file counts; cost/size are
    finite and non-negative;
  - at append time, every attested file EXISTS on disk under data_root
    with the exact hash and size.

GUARANTEE, STATED EXACTLY: ledger+anchor are tamper-EVIDENT against any
edit, reorder, interior deletion, tail truncation, or file deletion
that does not rewrite BOTH files consistently; not proof against a
fully local adversary who rewrites both — mirror the anchor off-host
for that. Records are REVALIDATED on every read. The locked period is
enforced from PARSED UTC DATES, never the split label.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from qlir import QlirError
from qlir.locks import ExclusiveLock
from qlir.mapping import ContractMap
from qlir.spec import AcquiredFile
from qlir.store import sha256_file

GENESIS = "0" * 64
LOCKED_START_UTC = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
VALIDATION_START_UTC = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
ANCHOR_SUFFIX = ".anchor"
PENDING_SUFFIX = ".pending"

SUPPORTED_STYPE_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("continuous", "instrument_id"),
        ("parent", "instrument_id"),
        ("raw_symbol", "instrument_id"),
        ("instrument_id", "raw_symbol"),
    }
)

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
    "files",
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


def _end_date_exclusive(end: dt.datetime) -> dt.date:
    midnight = end.replace(hour=0, minute=0, second=0, microsecond=0)
    return end.date() if end == midnight else end.date() + dt.timedelta(days=1)


def validate_record(record: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise QlirError(f"acquisition record missing required fields: {missing}")
    if not isinstance(record["requested_symbols"], list) or not record["requested_symbols"]:
        raise QlirError("requested_symbols must be a non-empty list")
    pair = (str(record["stype_in"]), str(record["stype_out"]))
    if pair not in SUPPORTED_STYPE_PAIRS:
        raise QlirError(
            f"unsupported symbology pair stype_in={pair[0]!r} -> stype_out={pair[1]!r}; "
            f"supported: {sorted(SUPPORTED_STYPE_PAIRS)} — the ledger must never "
            "attest to the invalid direct continuous->raw_symbol contract"
        )
    contract_map = ContractMap.from_record(record["resolved_contracts"])
    start = _parse_utc(record["start_utc"], "start_utc")
    end = _parse_utc(record["end_utc"], "end_utc")
    derived = split_for_range(start, end)  # raises on any locked-period touch
    if record["split"] != derived:
        raise QlirError(
            f"split label {record['split']!r} contradicts the date-derived "
            f"classification {derived!r} — labels never override dates"
        )
    # --- receipt binding (round 6, finding 1) --------------------------
    requested = {str(symbol) for symbol in record["requested_symbols"]}
    resolved = contract_map.symbols()
    if requested != resolved:
        raise QlirError(
            f"requested_symbols {sorted(requested)} do not equal the resolved "
            f"mapping symbols {sorted(resolved)} — the receipt binds unrelated "
            "objects"
        )
    end_exclusive = _end_date_exclusive(end)
    for symbol in sorted(requested):
        contract_map.assert_covers(symbol, start.date(), end_exclusive)
    files = record["files"]
    if not isinstance(files, list) or not files:
        raise QlirError(
            "files must be a non-empty list of immutable per-acquisition "
            "attestations {relative_path, sha256, size_bytes, record_count} — "
            "a pathname to a mutable cumulative manifest is not an attestation"
        )
    attested = [AcquiredFile.from_dict(item) for item in files]
    paths = [entry.relative_path for entry in attested]
    if len(set(paths)) != len(paths):
        raise QlirError("files list contains duplicate relative paths")
    total_count = sum(entry.record_count for entry in attested)
    if int(record["record_count"]) != total_count:
        raise QlirError(
            f"record_count {record['record_count']} does not equal the sum of "
            f"per-file counts ({total_count})"
        )
    for field, minimum in (("request_cost_usd", 0.0), ("billable_size_bytes", 0)):
        value = record[field]
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise QlirError(f"{field} is not numeric: {value!r}") from None
        if not (number == number and abs(number) != float("inf")) or number < minimum:
            raise QlirError(f"{field} must be finite and >= {minimum} (got {value!r})")


def verify_receipt_files(record: dict[str, Any], data_root: Path) -> None:
    """Disk verification: every attested file exists under data_root with
    the exact hash and size (run inside the append transaction)."""
    for item in record["files"]:
        entry = AcquiredFile.from_dict(item)
        full = Path(data_root) / entry.relative_path
        if not full.exists():
            raise QlirError(f"attested file missing on disk: {full}")
        actual_size = full.stat().st_size
        if actual_size != entry.size_bytes:
            raise QlirError(
                f"attested size mismatch for {entry.relative_path}: "
                f"disk {actual_size} != receipt {entry.size_bytes}"
            )
        actual_hash = sha256_file(full)
        if actual_hash != entry.sha256:
            raise QlirError(
                f"attested hash mismatch for {entry.relative_path}: "
                f"disk {actual_hash[:12]}… != receipt {entry.sha256[:12]}…"
            )


# -- anchor + pending journal ---------------------------------------------
def _anchor_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ANCHOR_SUFFIX)


def _pending_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + PENDING_SUFFIX)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_anchor(path: Path) -> dict[str, Any] | None:
    anchor_path = _anchor_path(path)
    if not anchor_path.exists():
        return None
    try:
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QlirError(f"anchor file {anchor_path} is not valid JSON: {exc}") from exc
    if not isinstance(anchor, dict) or {"count", "terminal_hash"} - set(anchor):
        raise QlirError(f"anchor file {anchor_path} lacks count/terminal_hash")
    return anchor


def _write_anchor(path: Path, count: int, terminal_hash: str) -> None:
    _atomic_json(_anchor_path(path), {"count": count, "terminal_hash": terminal_hash})


def _raw_lines(path: Path) -> list[str]:
    if not Path(path).exists():
        return []
    return [line for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_link(line: str, index: int) -> dict[str, Any]:
    try:
        link = json.loads(line)
    except json.JSONDecodeError as exc:
        raise QlirError(f"ledger line {index} is not valid JSON: {exc}") from exc
    if not isinstance(link, dict) or {"prev_hash", "record_hash", "record"} - set(link):
        raise QlirError(f"ledger line {index} lacks the chain envelope")
    return link


def _recover(path: Path) -> None:
    """Deterministically complete or roll back an interrupted append.
    MUST be called under the exclusive lock."""
    pending_path = _pending_path(path)
    if not pending_path.exists():
        return
    try:
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # The pending journal is written atomically — a torn journal
        # means something beyond an interrupted append happened.
        raise QlirError(f"pending journal is corrupt ({exc}) — manual audit required") from exc
    required = {"prev_count", "prev_terminal", "line", "new_count", "new_terminal"}
    if not isinstance(pending, dict) or required - set(pending):
        raise QlirError("pending journal lacks required fields — manual audit required")
    lines = _raw_lines(path)
    prev_count = int(pending["prev_count"])
    if len(lines) == prev_count:
        # The append never reached the ledger: roll back.
        pending_path.unlink()
        return
    if len(lines) == prev_count + 1:
        if lines[-1] == pending["line"]:
            # Ledger append landed; the anchor write was interrupted:
            # roll forward.
            _write_anchor(path, int(pending["new_count"]), str(pending["new_terminal"]))
            pending_path.unlink()
            return
        # TORN final line — the only non-atomic step. The journal proves
        # the committed prior state; strip the uncommitted bytes.
        committed = lines[:prev_count]
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(("\n".join(committed) + "\n") if committed else "", encoding="utf-8")
        os.replace(tmp, path)
        pending_path.unlink()
        return
    raise QlirError(
        f"pending journal expects {prev_count}(+1) ledger line(s), found "
        f"{len(lines)} — manual audit required"
    )


def recover_ledger(path: Path) -> None:
    """Public recovery entry point (takes the lock itself)."""
    path = Path(path)
    with ExclusiveLock(path):
        _recover(path)


def verify_ledger(path: Path) -> list[dict[str, Any]]:
    """Verify chain integrity AND the anchor AND record validity.

    Refuses while a pending journal exists (run recover_ledger); fails
    closed on broken links, modified records, tail truncation, ledger or
    anchor deletion, and any record failing read-time revalidation."""
    path = Path(path)
    if _pending_path(path).exists():
        raise QlirError(
            f"ledger {path} has an unresolved pending transaction — run "
            "qlir.manifest.recover_ledger(path) (or the next locked append "
            "will recover it) before reading"
        )
    lines = _raw_lines(path)
    links = [_parse_link(line, i) for i, line in enumerate(lines)]
    anchor = _read_anchor(path)
    if anchor is None:
        if links:
            raise QlirError(
                f"ledger {path} has {len(links)} record(s) but no anchor — "
                "the anchor was deleted or never written; refusing to trust "
                "the tail"
            )
        return []
    if len(links) != int(anchor["count"]):
        raise QlirError(
            f"ledger tail mismatch: anchor expects {anchor['count']} record(s), "
            f"found {len(links)} — tail truncation or ledger deletion"
        )
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
        validate_record(link["record"])  # read-time revalidation
        prev = link["record_hash"]
    terminal = links[-1]["record_hash"] if links else GENESIS
    if terminal != anchor["terminal_hash"]:
        raise QlirError("ledger terminal hash does not match the anchor — tail truncation")
    return links


def load_ledger(path: Path) -> list[dict[str, Any]]:
    """Chain-and-anchor-verified, revalidated records (unwrapped)."""
    return [link["record"] for link in verify_ledger(path)]


def append_acquisition(
    path: Path, record: dict[str, Any], data_root: Path | None = None
) -> list[dict[str, Any]]:
    """Validate, DISK-VERIFY the attested files, and append one receipt
    via the recoverable pending-journal transaction.

    `data_root` is the q_lir data root the receipt's relative paths
    resolve against; defaults to the ledger's grandparent (the standard
    `<root>/manifests/acquisition.jsonl` layout)."""
    validate_record(record)
    path = Path(path)
    root = Path(data_root) if data_root is not None else path.parent.parent
    with ExclusiveLock(path):
        _recover(path)
        verify_receipt_files(record, root)
        links = verify_ledger(path)  # refuses corrupt or truncated state
        prev = links[-1]["record_hash"] if links else GENESIS
        link = {
            "prev_hash": prev,
            "record_hash": _link_hash(prev, record),
            "record": record,
        }
        line = json.dumps(link, sort_keys=True, separators=(",", ":"), default=str)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            _pending_path(path),
            {
                "prev_count": len(links),
                "prev_terminal": prev,
                "line": line,
                "new_count": len(links) + 1,
                "new_terminal": link["record_hash"],
            },
        )
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        _write_anchor(path, len(links) + 1, link["record_hash"])
        with contextlib.suppress(OSError):
            _pending_path(path).unlink()
    return [*(link_["record"] for link_ in links), record]

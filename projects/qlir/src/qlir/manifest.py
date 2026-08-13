"""Hash-chained, anchored, append-only acquisition ledger (round 5).

Structure: `acquisition.jsonl` — one JSON line per record:

    {"prev_hash": <hex>, "record_hash": <hex>, "record": {...}}

with record_hash = sha256(prev_hash + canonical_json(record)), chained
from GENESIS, written by O_APPEND single-line writes under an exclusive
lock. A sibling ANCHOR file (`acquisition.jsonl.anchor`) stores the
expected record count and terminal hash and is updated atomically
inside the same locked transaction — so removing the tail line(s), or
the whole ledger, no longer reads back clean (round 5, defect 3: an
unanchored chain cannot detect tail truncation).

GUARANTEE, STATED EXACTLY: the ledger+anchor pair is tamper-EVIDENT
against any edit, reorder, interior deletion, tail truncation, or
whole-file deletion that does not rewrite BOTH files consistently. It
is NOT proof against a fully local adversary who rewrites ledger and
anchor together — that requires mirroring the anchor off-host, which is
an operational step, not a property this code can provide. Records are
REVALIDATED on every read: a ledger can never attest to an unsupported
symbology pairing or an untyped resolved_contracts structure.

Locked-period rule: enforced from PARSED UTC DATES, never the split
label — any range touching 2025-01-01+ is refused; labels must match
the date-derived classification; dev/val-spanning ranges are refused.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from qlir import QlirError
from qlir.locks import ExclusiveLock
from qlir.mapping import ContractMap

GENESIS = "0" * 64
LOCKED_START_UTC = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
VALIDATION_START_UTC = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
ANCHOR_SUFFIX = ".anchor"

# The supported symbology conversions this protocol may record. The
# invalid direct continuous->raw_symbol pairing is refused here so the
# ledger can never attest to it (round 5, defect 3).
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
    pair = (str(record["stype_in"]), str(record["stype_out"]))
    if pair not in SUPPORTED_STYPE_PAIRS:
        raise QlirError(
            f"unsupported symbology pair stype_in={pair[0]!r} -> stype_out={pair[1]!r}; "
            f"supported: {sorted(SUPPORTED_STYPE_PAIRS)} — the ledger must never "
            "attest to the invalid direct continuous->raw_symbol contract"
        )
    # resolved_contracts must round-trip through the TYPED ContractMap
    # structure — "garbage" or a serialized surrogate shape is refused.
    ContractMap.from_record(record["resolved_contracts"])
    start = _parse_utc(record["start_utc"], "start_utc")
    end = _parse_utc(record["end_utc"], "end_utc")
    derived = split_for_range(start, end)  # raises on any locked-period touch
    if record["split"] != derived:
        raise QlirError(
            f"split label {record['split']!r} contradicts the date-derived "
            f"classification {derived!r} — labels never override dates"
        )


def _anchor_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ANCHOR_SUFFIX)


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
    anchor_path = _anchor_path(path)
    payload = json.dumps({"count": count, "terminal_hash": terminal_hash}) + "\n"
    tmp = anchor_path.with_suffix(anchor_path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, anchor_path)


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
    """Verify chain integrity AND the anchor AND record validity.

    Fails closed on: broken links, modified records, tail truncation
    (anchor count/terminal mismatch), a deleted ledger with a surviving
    anchor, a populated ledger with no anchor, and any record that no
    longer passes validate_record (read-time revalidation)."""
    path = Path(path)
    links = _read_links(path)
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


def append_acquisition(path: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate and append one record under the exclusive lock: verify
    the existing chain+anchor, O_APPEND the new line, update the anchor
    atomically inside the same transaction."""
    validate_record(record)
    path = Path(path)
    with ExclusiveLock(path):
        links = verify_ledger(path)  # refuses corrupt or truncated state
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
        _write_anchor(path, len(links) + 1, link["record_hash"])
    return [*(link_["record"] for link_ in links), record]

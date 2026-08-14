"""The acquisition COORDINATOR (round 7): the receipt is DERIVED from
the decoded bytes and the server batch manifest — never asserted.

    spec → exact API responses (strict envelopes; step-two symbols must
    equal the instrument ids step one produced) → server file manifest →
    contained immutable files → DBN decoding with derived per-file
    counts → aggregate symbol/range coverage from the bytes → ledger
    append (disk-verified, recoverable transaction).

What `build_verified_receipt` refuses, each a round-7 reproduction:
  - arbitrary non-DBN bytes (they cannot decode, so they cannot be
    counted, so they cannot be attested);
  - caller-claimed record counts (counts come from decoding);
  - files that do not exactly match the server batch manifest (names
    and sizes; hashes too when the server provides them);
  - receipts whose spec symbols have no decoded records (an ES-only
    file cannot receipt an ES+NQ acquisition);
  - records outside the spec's half-open interval on ts_recv;
  - a single instrument_id appearing under multiple publisher_ids in
    one acquisition (ids are only unique per publisher/day).

HONEST LIMIT, stated plainly: local code can prove the download matches
the server's own manifest and that the decoded bytes cover every
requested symbol inside the requested range. Whether the SERVER's batch
was itself complete for the request is attested by that manifest plus
the dataset-condition record — the first real batch is additionally
quarantined as calibration, not research data.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd

from qlir import QlirError
from qlir.loader import load_events
from qlir.mapping import ContractMap
from qlir.spec import AcquiredFile, AcquisitionSpec, EnvelopeCheck, validate_envelope
from qlir.store import sha256_file


def compose_contract_map(
    spec: AcquisitionSpec,
    step_one_response: object,
    step_two_response: object,
    allow_unverified: bool = False,
) -> ContractMap:
    """Spec-validated composition. Step two's envelope symbols must equal
    the instrument ids derived from step one (round 7, finding 4)."""
    step_one = validate_envelope(
        step_one_response,
        spec,
        EnvelopeCheck(stype_in=spec.stype_in, stype_out=spec.stype_out, symbols=spec.symbols),
        "step one (continuous→instrument_id)",
        allow_unverified=allow_unverified,
    )
    step_one_ids = tuple(
        sorted(
            {
                str(interval["s"])
                for intervals in step_one.values()
                if isinstance(intervals, list)
                for interval in intervals
                if isinstance(interval, dict) and "s" in interval
            }
        )
    )
    step_two = validate_envelope(
        step_two_response,
        spec,
        EnvelopeCheck(
            stype_in="instrument_id",
            stype_out="raw_symbol",
            symbols=step_one_ids if not allow_unverified else None,
        ),
        "step two (instrument_id→raw_symbol)",
        allow_unverified=allow_unverified,
    )
    unknown = sorted(set(step_one) - set(spec.symbols))
    if unknown:
        raise QlirError(f"step one resolved symbols {unknown} that the spec never requested")
    missing = sorted(set(spec.symbols) - set(step_one))
    if missing:
        raise QlirError(f"step one is missing spec symbols {missing}")
    contract_map = ContractMap.compose_many(step_one, step_two)
    for symbol in spec.symbols:
        contract_map.assert_covers(symbol, spec.start_date, spec.end_date_exclusive)
    return contract_map


def load_acquired_file(
    path: str | Path, spec: AcquisitionSpec, contract_map: ContractMap
) -> pd.DataFrame:
    """Load one per-date raw file with the full identity binding: DBN
    metadata vs spec, records inside the SPEC interval on ts_recv,
    unambiguous publisher identity, and per-record raw_symbol AND
    requested-symbol binding by (instrument_id, event_date)."""
    path = Path(path)
    if set(contract_map.symbols()) != set(spec.symbols):
        raise QlirError(
            f"contract map symbols {sorted(contract_map.symbols())} do not equal "
            f"the spec symbols {sorted(spec.symbols)}"
        )
    probe = load_events(path, spec=spec, id_to_raw=None, allow_unresolved=True)
    # Round-7 finding 5: exact half-open containment on ts_recv (the
    # historical filter timestamp), not merely the calendar date.
    ts_ns = pd.to_datetime(probe["ts_recv"], utc=True).astype("int64")
    spec_start_ns = int(spec.start_utc.timestamp() * 1_000_000_000)
    spec_end_ns = int(spec.end_utc.timestamp() * 1_000_000_000)
    outside = int(((ts_ns < spec_start_ns) | (ts_ns >= spec_end_ns)).sum())
    if outside:
        raise QlirError(
            f"{path}: {outside} record(s) fall outside the spec's half-open interval on ts_recv"
        )
    # Ids are only unique per publisher (and per day for some
    # publishers): one id under two publishers in one file is ambiguous.
    per_id_publishers = probe.groupby("instrument_id")["publisher_id"].nunique()
    ambiguous = per_id_publishers[per_id_publishers > 1]
    if len(ambiguous):
        raise QlirError(
            f"{path}: instrument_id(s) {sorted(ambiguous.index.tolist())} appear "
            "under multiple publisher_ids — identity is ambiguous"
        )
    event_dates = sorted({ts.date() for ts in probe["ts_event"]})
    if len(event_dates) != 1:
        raise QlirError(
            f"{path}: records span {len(event_dates)} event dates {event_dates[:4]} — "
            "the store layout is one file per date; split the file or fix the request"
        )
    event_date = event_dates[0]
    if not (spec.start_date <= event_date < spec.end_date_exclusive):
        raise QlirError(
            f"{path}: event date {event_date} lies outside the spec range "
            f"[{spec.start_date} .. {spec.end_date_exclusive})"
        )
    flat = contract_map.flat_map_for_date(event_date)
    frame = load_events(path, spec=spec, id_to_raw=flat, allow_unresolved=True)
    for instrument_id in frame["instrument_id"].unique():
        expected_raw = contract_map.raw_for(int(instrument_id), event_date)
        expected_symbol = contract_map.symbol_for(int(instrument_id), event_date)
        rows = frame["instrument_id"] == instrument_id
        got_raw = list(frame.loc[rows, "raw_symbol"].unique())
        if got_raw != [expected_raw]:
            raise QlirError(
                f"{path}: raw identity mismatch for instrument_id {instrument_id}: "
                f"{got_raw} != {expected_raw}"
            )
        frame.loc[rows, "symbol"] = expected_symbol
    return frame


def build_verified_receipt(
    *,
    spec: AcquisitionSpec,
    contract_map: ContractMap,
    data_root: str | Path,
    stored_files: list[tuple[str, str]],  # (relative_path, server_filename)
    server_manifest: list[dict[str, Any]],  # server batch manifest entries
    request_cost_usd: float,
    billable_size_bytes: int,
    client_version: str,
    dataset_conditions: dict[str, Any],
    derivation_code_commit: str,
    split: str,
) -> dict[str, Any]:
    """DERIVE the receipt from the bytes and the server manifest.

    Per-file record counts come from DECODING each file through the
    full identity binding — arbitrary bytes and caller-claimed counts
    are unrepresentable. The attested files must exactly match the
    server batch manifest (names, sizes, hashes when provided), and the
    decoded bytes must cover every spec symbol inside the spec range.
    """
    data_root = Path(data_root)
    if not stored_files:
        raise QlirError("an acquisition must contain at least one stored file")
    if not isinstance(server_manifest, list) or not server_manifest:
        raise QlirError("server_manifest must be the server's non-empty batch file list")
    manifest_by_name: dict[str, dict[str, Any]] = {}
    for entry in server_manifest:
        if not isinstance(entry, dict) or "filename" not in entry or "size_bytes" not in entry:
            raise QlirError(f"server_manifest entry malformed: {entry!r}")
        name = str(entry["filename"])
        if name in manifest_by_name:
            raise QlirError(f"server_manifest lists {name!r} twice")
        manifest_by_name[name] = entry
    stored_names = [server_filename for _, server_filename in stored_files]
    if len(set(stored_names)) != len(stored_names):
        raise QlirError("stored_files bind one server filename twice")
    if set(stored_names) != set(manifest_by_name):
        raise QlirError(
            f"stored files {sorted(set(stored_names))} do not exactly match the "
            f"server manifest {sorted(manifest_by_name)} — the download is not "
            "the complete batch"
        )

    attested: list[AcquiredFile] = []
    seen_symbols: set[str] = set()
    for relative_path, server_filename in stored_files:
        full = data_root / relative_path
        if not full.exists():
            raise QlirError(f"stored file does not exist: {full}")
        manifest_entry = manifest_by_name[server_filename]
        actual_size = full.stat().st_size
        if int(manifest_entry["size_bytes"]) != actual_size:
            raise QlirError(
                f"{relative_path}: size {actual_size} does not match the server "
                f"manifest ({manifest_entry['size_bytes']}) for {server_filename}"
            )
        actual_hash = sha256_file(full)
        server_hash = manifest_entry.get("hash")
        if server_hash and str(server_hash).lower().removeprefix("sha256:") != actual_hash:
            raise QlirError(
                f"{relative_path}: hash does not match the server manifest for {server_filename}"
            )
        # DERIVED count: the bytes must decode through the full binding.
        frame = load_acquired_file(full, spec, contract_map)
        seen_symbols.update(frame["symbol"].unique())
        attested.append(
            AcquiredFile(
                relative_path=str(Path(relative_path).as_posix()),
                sha256=actual_hash,
                size_bytes=actual_size,
                record_count=len(frame),
                server_filename=server_filename,
            )
        )
    uncovered = sorted(set(spec.symbols) - seen_symbols)
    if uncovered:
        raise QlirError(
            f"decoded bytes contain no records for spec symbol(s) {uncovered} — "
            "mapping coverage is not file coverage; the acquisition is incomplete"
        )
    return {
        "dataset": spec.dataset,
        "schema": spec.schema,
        "requested_symbols": sorted(spec.symbols),
        "stype_in": spec.stype_in,
        "stype_out": spec.stype_out,
        "resolved_contracts": contract_map.to_record(),
        "start_utc": spec.start_utc.astimezone(dt.UTC).isoformat().replace("+00:00", "Z"),
        "end_utc": spec.end_utc.astimezone(dt.UTC).isoformat().replace("+00:00", "Z"),
        "request_cost_usd": request_cost_usd,
        "record_count": sum(entry.record_count for entry in attested),
        "billable_size_bytes": billable_size_bytes,
        "client_version": client_version,
        "files": [entry.to_dict() for entry in attested],
        "server_manifest": [
            {"filename": name, "size_bytes": int(entry["size_bytes"])}
            for name, entry in sorted(manifest_by_name.items())
        ],
        "dataset_conditions": dataset_conditions,
        "derivation_code_commit": derivation_code_commit,
        "split": split,
    }

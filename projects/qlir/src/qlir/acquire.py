"""Acquisition integration: ONE spec bound across every boundary
(round 6: independently valid but mutually contradictory objects must be
unrepresentable as a single acquisition).

    spec = AcquisitionSpec(dataset="GLBX.MDP3", schema="trades",
                           symbols=("ES.v.0",), start_utc=…, end_utc=…)
    step_one = client.symbology.resolve(...)   # continuous -> instrument_id
    step_two = client.symbology.resolve(...)   # instrument_id -> raw_symbol
    contract_map = compose_contract_map(spec, step_one, step_two)
    frame = load_acquired_file(path, spec, contract_map)
    files = attest_files(data_root, [(relpath, record_count), ...])
    record = build_acquisition_record(spec=spec, contract_map=contract_map,
                                      files=files, ...)
    append_acquisition(ledger_path, record, data_root=data_root)

Every arrow validates against the SAME spec: the symbology envelopes
(dataset/stypes/symbols/dates when present; bare payloads need an
explicit allow_unverified), the DBN metadata (dataset/schema/stypes/
symbols/interval), the per-record identity (raw_symbol AND requested
symbol by instrument_id + event date), and the ledger receipt (symbol
sets equal, coverage complete, immutable per-file hash list verified on
disk before the append).
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
    """Spec-validated composition of the two symbology.resolve responses."""
    step_one = validate_envelope(
        step_one_response,
        spec,
        EnvelopeCheck(stype_in=spec.stype_in, stype_out=spec.stype_out, symbols=spec.symbols),
        "step one (continuous→instrument_id)",
        allow_unverified=allow_unverified,
    )
    step_two = validate_envelope(
        step_two_response,
        spec,
        # Step two's input symbols are instrument ids — not spec.symbols.
        EnvelopeCheck(stype_in="instrument_id", stype_out="raw_symbol", symbols=None),
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
    metadata vs spec, per-record raw_symbol AND requested symbol by
    (instrument_id, event_date)."""
    path = Path(path)
    if set(contract_map.symbols()) != set(spec.symbols):
        raise QlirError(
            f"contract map symbols {sorted(contract_map.symbols())} do not equal "
            f"the spec symbols {sorted(spec.symbols)}"
        )
    probe = load_events(path, spec=spec, id_to_raw=None, allow_unresolved=True)
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
    # Per-record identity binding — raw contract AND requested symbol.
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


def attest_files(data_root: str | Path, entries: list[tuple[str, int]]) -> list[AcquiredFile]:
    """Hash each acquired file NOW and freeze the attestation — the
    receipt carries {relative_path, sha256, size, record_count}, never a
    pointer to a mutable cumulative manifest (round 6, finding 1)."""
    data_root = Path(data_root)
    if not entries:
        raise QlirError("an acquisition must attest at least one file")
    attested: list[AcquiredFile] = []
    for relative_path, record_count in entries:
        full = data_root / relative_path
        if not full.exists():
            raise QlirError(f"acquired file does not exist: {full}")
        attested.append(
            AcquiredFile(
                relative_path=str(Path(relative_path).as_posix()),
                sha256=sha256_file(full),
                size_bytes=full.stat().st_size,
                record_count=int(record_count),
            )
        )
    return attested


def build_acquisition_record(
    *,
    spec: AcquisitionSpec,
    contract_map: ContractMap,
    files: list[AcquiredFile],
    request_cost_usd: float,
    billable_size_bytes: int,
    client_version: str,
    dataset_conditions: dict[str, Any],
    derivation_code_commit: str,
    split: str,
) -> dict[str, Any]:
    """The ledger receipt: every identity field DERIVES from the spec and
    the composed map — callers cannot supply contradictory values."""
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
        "record_count": sum(entry.record_count for entry in files),
        "billable_size_bytes": billable_size_bytes,
        "client_version": client_version,
        "files": [entry.to_dict() for entry in files],
        "dataset_conditions": dataset_conditions,
        "derivation_code_commit": derivation_code_commit,
        "split": split,
    }

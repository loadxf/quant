"""Acquisition integration: exact API responses → ContractMap → DBN
records → ledger record (round 5: "unit-tested components with
incompatible interfaces are not an acquisition system").

The pipeline this module makes real:

    step_one = client.symbology.resolve(stype_in="continuous",
                                        stype_out="instrument_id", ...)
    step_two = client.symbology.resolve(stype_in="instrument_id",
                                        stype_out="raw_symbol", ...)
    contract_map = compose_contract_map(step_one, step_two)
    frame = load_acquired_file(path, schema, contract_map)   # per-record
                                                             # date-aware raw
    record = build_acquisition_record(..., contract_map=contract_map, ...)
    append_acquisition(ledger_path, record)

`compose_contract_map` accepts the exact response envelopes (with or
without the "result" wrapper) and refuses partial/not-found leftovers.
`load_acquired_file` derives each RECORD's event date from ts_event
(UTC) and resolves raw identity by (instrument_id, event_date) through
the composed map — for a per-date raw file this collapses to the
validated single-date map, and a file whose records span multiple dates
is refused, matching the one-file-one-date store layout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from qlir import QlirError
from qlir.loader import load_events
from qlir.mapping import ContractMap


def _unwrap_result(response: object, step: str) -> dict[str, list[dict]]:
    """Accept the raw HTTP-API envelope or the bare mapping dict."""
    payload = response
    if isinstance(payload, dict) and "result" in payload:
        payload = payload["result"]
    if not isinstance(payload, dict) or not payload:
        raise QlirError(f"{step} response has no usable mapping payload: {type(response)}")
    for key in ("partial", "not_found"):
        leftovers = response.get(key) if isinstance(response, dict) else None
        if leftovers:
            raise QlirError(
                f"{step} response reports {key}={leftovers!r} — refusing to "
                "compose an incomplete symbology resolution"
            )
    return payload


def compose_contract_map(step_one_response: object, step_two_response: object) -> ContractMap:
    """Exact-shape composition of the two symbology.resolve responses."""
    step_one = _unwrap_result(step_one_response, "step one (continuous→instrument_id)")
    step_two = _unwrap_result(step_two_response, "step two (instrument_id→raw_symbol)")
    return ContractMap.compose_many(step_one, step_two)


def load_acquired_file(path: str | Path, schema: str, contract_map: ContractMap) -> pd.DataFrame:
    """Load one per-date raw file with date-aware raw-identity binding."""
    path = Path(path)
    probe = load_events(path, schema, id_to_raw=None, allow_unresolved=True)
    event_dates = sorted({ts.date() for ts in probe["ts_event"]})
    if len(event_dates) != 1:
        raise QlirError(
            f"{path}: records span {len(event_dates)} event dates {event_dates[:4]} — "
            "the store layout is one file per date; split the file or fix the request"
        )
    flat = contract_map.flat_map_for_date(event_dates[0])
    frame = load_events(path, schema, id_to_raw=flat)
    # Defense in depth: re-resolve each record through the date-aware
    # lookup so a wrong flat map can never slip through silently.
    for instrument_id in frame["instrument_id"].unique():
        expected = contract_map.raw_for(int(instrument_id), event_dates[0])
        got = frame.loc[frame["instrument_id"] == instrument_id, "raw_symbol"].unique()
        if list(got) != [expected]:
            raise QlirError(
                f"{path}: raw identity mismatch for instrument_id {instrument_id}: "
                f"{list(got)} != {expected}"
            )
    return frame


def build_acquisition_record(
    *,
    dataset: str,
    schema: str,
    requested_symbols: list[str],
    contract_map: ContractMap,
    start_utc: str,
    end_utc: str,
    request_cost_usd: float,
    record_count: int,
    billable_size_bytes: int,
    client_version: str,
    dataset_conditions: dict[str, Any],
    derivation_code_commit: str,
    split: str,
    file_hashes: str = "manifests/files.sha256",
) -> dict[str, Any]:
    """The ledger record, with `resolved_contracts` as the TYPED
    ContractMap serialization (validated again at append and read)."""
    return {
        "dataset": dataset,
        "schema": schema,
        "requested_symbols": requested_symbols,
        "stype_in": "continuous",
        "stype_out": "instrument_id",
        "resolved_contracts": contract_map.to_record(),
        "start_utc": start_utc,
        "end_utc": end_utc,
        "request_cost_usd": request_cost_usd,
        "record_count": record_count,
        "billable_size_bytes": billable_size_bytes,
        "client_version": client_version,
        "file_hashes": file_hashes,
        "dataset_conditions": dataset_conditions,
        "derivation_code_commit": derivation_code_commit,
        "split": split,
    }
